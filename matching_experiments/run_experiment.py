#!/usr/bin/env python3
"""
LLM Matching Experiment — Simplified Pipeline

Evaluates how well LLMs match vulnerability findings to ground-truth entries,
compared against human annotations. Uses a fixed set of 50 findings (25 human-TP
+ 25 human-FP) and reports TP/FP counts with mean/std across replicates.

Usage:
    python matching_experiments/run_experiment.py --models haiku-4.5
    python matching_experiments/run_experiment.py --models haiku-4.5 gpt-5.4-mini --replicates 5
    python matching_experiments/run_experiment.py --models deepseek-3.1 qwen-3.6-plus

Results are saved per-model in matching_experiments/results/<model_key>.json and
accumulate across runs. A comparison plot is always regenerated.
"""

import argparse
import asyncio
import json
import os
import statistics
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Literal

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from dotenv import load_dotenv
from pydantic import BaseModel
from scipy.optimize import linear_sum_assignment

load_dotenv()

# ---------------------------------------------------------------------------
# LangSmith tracing
# ---------------------------------------------------------------------------
os.environ.setdefault("LANGCHAIN_TRACING_V2", "true")
os.environ.setdefault("LANGCHAIN_PROJECT", "matching-experiments")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
EXPERIMENT_DIR = Path(__file__).resolve().parent
ETHIBENCH_ROOT = EXPERIMENT_DIR.parent
GT_DIR = ETHIBENCH_ROOT / "examples" / "gt"
RESULTS_DIR = EXPERIMENT_DIR / "results"

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
CONCURRENCY_LIMIT = 25
DEFAULT_REPLICATES = 3

# ---------------------------------------------------------------------------
# Structured output schema
# ---------------------------------------------------------------------------


class VulnerabilityMatch(BaseModel):
    is_match: Literal["YES", "NO"]


# ---------------------------------------------------------------------------
# LLM configurations
# ---------------------------------------------------------------------------
LLM_CONFIGS = {
    "haiku-4.5": {
        "model_name": "claude-haiku-4-5",
        "display_name": "Haiku 4.5",
        "provider": "anthropic",
        "api_url": None,
        "temperature": 0.3,
    },
    "gpt-5.4-mini": {
        "model_name": "gpt-5.4-mini",
        "display_name": "GPT 5.4 Mini",
        "provider": "openai",
        "api_url": None,
        "temperature": 0.3,
    },
    "deepseek-3.1": {
        "model_name": "accounts/fireworks/models/deepseek-v3p1",
        "display_name": "Deepseek 3.1",
        "provider": "fireworks",
        "api_url": "https://api.fireworks.ai/inference/v1",
        "temperature": 0.3,
    },
    "qwen-3.6-plus": {
        "model_name": "accounts/fireworks/models/qwen3p6-plus",
        "display_name": "Qwen 3.6 Plus",
        "provider": "fireworks",
        "api_url": "https://api.fireworks.ai/inference/v1",
        "temperature": 0.3,
    },    "gemini-3-flash": {
        "model_name": "gemini-3-flash-preview",
        "display_name": "Gemini 3 Flash",
        "provider": "gemini",
        "api_url": None,
        "temperature": 0.3,
    },}

AVAILABLE_MODELS = list(LLM_CONFIGS.keys())


# ---------------------------------------------------------------------------
# LLM factory
# ---------------------------------------------------------------------------


def create_structured_llm(config: dict):
    """Build a structured-output LLM from a config dict."""
    from langchain_anthropic import ChatAnthropic
    from langchain_openai import ChatOpenAI

    provider = config["provider"]
    model_name = config["model_name"]
    temperature = config["temperature"]
    api_url = config["api_url"]

    if provider == "fireworks":
        llm = ChatOpenAI(
            name=model_name,
            model=model_name,
            api_key=os.getenv("FIREWORKS_API_KEY"),
            base_url=api_url,
            temperature=temperature,
        )
    elif provider == "openai":
        llm = ChatOpenAI(
            name=model_name,
            model=model_name,
            temperature=temperature,
            max_retries=2,
            timeout=300,
        )
    elif provider == "anthropic":
        import pydantic as _pydantic

        llm = ChatAnthropic(
            name=model_name,
            model_name=model_name,
            api_key=_pydantic.SecretStr(os.getenv("ANTHROPIC_API_KEY") or ""),
            temperature=temperature,
            max_tokens_to_sample=8192,
        )
    elif provider == "gemini":
        import pydantic as _pydantic
        from langchain_google_genai import ChatGoogleGenerativeAI

        llm = ChatGoogleGenerativeAI(
            name=model_name,
            model=model_name,
            api_key=_pydantic.SecretStr(os.getenv("GEMINI_API_KEY") or ""),
            temperature=temperature,
            max_retries=2,
        )
    else:
        raise ValueError(f"Unsupported provider: {provider!r}")

    return llm.with_structured_output(VulnerabilityMatch)


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------


def load_jsonl(path: Path) -> list[dict]:
    """Load items from a JSONL file or directory of JSONL files."""
    items = []
    file_paths = [path] if path.is_file() else list(path.glob("*.jsonl"))
    for fp in file_paths:
        with open(fp) as f:
            for line in f:
                if not line.strip():
                    continue
                items.append(json.loads(line))
    return items


def group_by_subset(items: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for item in items:
        grouped[item["subset_name"]].append(item)
    return grouped


def load_selected_findings() -> tuple[list[dict], set[str], set[str]]:
    """Load the fixed set of 50 selected findings.

    Returns (findings_list, tp_uuids, fp_uuids).
    """
    with open(EXPERIMENT_DIR / "selected_findings.json") as f:
        selection = json.load(f)

    tp_uuids = set(selection["tp_uuids"])
    fp_uuids = set(selection["fp_uuids"])
    all_uuids = tp_uuids | fp_uuids

    findings = []
    with open(EXPERIMENT_DIR / "findings.jsonl") as f:
        for line in f:
            if not line.strip():
                continue
            item = json.loads(line)
            if item["uuid"] in all_uuids:
                findings.append(item)

    return findings, tp_uuids, fp_uuids


def load_ground_truths() -> list[dict]:
    """Load all ground truth entries."""
    return load_jsonl(GT_DIR)


# ---------------------------------------------------------------------------
# Bipartite matching (from evaluate.py)
# ---------------------------------------------------------------------------


def compute_maximum_matching(
    finding_to_gt: dict[int, set[int]], num_findings: int, num_gts: int
) -> tuple[int, set[int], set[int]]:
    """Optimal bipartite matching via the Hungarian algorithm.

    Returns (tp_count, matched_finding_indices, matched_gt_indices).
    """
    cost_matrix = []
    for i in range(num_findings):
        row = [-1 if j in finding_to_gt.get(i, set()) else 0 for j in range(num_gts)]
        cost_matrix.append(row)

    finding_indices, gt_indices = linear_sum_assignment(cost_matrix)

    matched_findings: set[int] = set()
    matched_gts: set[int] = set()
    for f_idx, g_idx in zip(finding_indices, gt_indices):
        if g_idx in finding_to_gt.get(f_idx, set()):
            matched_findings.add(f_idx)
            matched_gts.add(g_idx)

    return len(matched_findings), matched_findings, matched_gts


# ---------------------------------------------------------------------------
# Metrics from raw matchings
# ---------------------------------------------------------------------------


def compute_tp_fp(
    findings: list[dict],
    ground_truths: list[dict],
    raw_matchings: dict[str, list[str]],
) -> dict:
    """
    Apply bipartite matching and compute TP/FP counts.

    raw_matchings: {finding_uuid: [list of matched gt_ids]}
    """
    findings_by_subset = group_by_subset(findings)
    gt_by_subset = group_by_subset(ground_truths)
    all_subsets = set(findings_by_subset.keys()) | set(gt_by_subset.keys())

    total_tp = 0
    total_fp = 0

    for subset in sorted(all_subsets):
        subset_findings = findings_by_subset.get(subset, [])
        subset_gt = gt_by_subset.get(subset, [])

        if not subset_findings:
            continue
        if not subset_gt:
            total_fp += len(subset_findings)
            continue

        gt_id_to_idx = {gt["id"]: j for j, gt in enumerate(subset_gt)}
        finding_to_gt: dict[int, set[int]] = defaultdict(set)

        for i, finding in enumerate(subset_findings):
            uuid = finding["uuid"]
            for gt_id in raw_matchings.get(uuid, []):
                if gt_id in gt_id_to_idx:
                    finding_to_gt[i].add(gt_id_to_idx[gt_id])

        tp, matched_findings, _ = compute_maximum_matching(
            finding_to_gt, len(subset_findings), len(subset_gt)
        )
        # FP = findings with zero raw matches at all
        fp = sum(1 for i in range(len(subset_findings)) if not finding_to_gt[i])

        total_tp += tp
        total_fp += fp

    return {"true_positives": total_tp, "false_positives": total_fp}


# ---------------------------------------------------------------------------
# Human baseline
# ---------------------------------------------------------------------------


def compute_human_baseline(findings: list[dict], ground_truths: list[dict]) -> dict:
    """Compute TP/FP from human annotations for the selected findings."""
    with open(EXPERIMENT_DIR / "annotations.json") as f:
        annotations = json.load(f)

    raw_matchings: dict[str, list[str]] = {}
    for finding in findings:
        uuid = finding["uuid"]
        ann = annotations.get(uuid, {})
        raw_matchings[uuid] = ann.get("selected_gt_ids", [])

    return compute_tp_fp(findings, ground_truths, raw_matchings)


# ---------------------------------------------------------------------------
# LLM matching
# ---------------------------------------------------------------------------


async def compare_pair(structured_llm, finding: dict, gt: dict, semaphore) -> bool:
    """Compare a single finding/GT pair using the LLM (with retries)."""
    prompt = (
        "You are a security analyst comparing two vulnerability descriptions. "
        "One represents a FINDING from an AI pentesting agent, and the other is a GROUND TRUTH entry from a database. "
        "Compare these two vulnerability descriptions and determine if they "
        "represent the same vulnerability. "
        "Be aware that the FINDING and the GROUND TRUTH may be described differently. "
        "This means you should not make a judgement solely based on the wording.\n\n"
        f"FINDING:\n"
        f"- Name: {finding.get('title')}\n"
        f"- Description: {finding.get('description')}\n"
        f"- Steps to Reproduce: {finding.get('steps')}\n\n"
        f"GROUND TRUTH:\n"
        f"- Name: {gt.get('name')}\n"
        f"- Category: {gt.get('category')}\n"
        f"- Description: {gt.get('description')}\n"
        f"- Additional Info: {gt.get('additional_info')}\n\n"
    )

    retries = 5
    for attempt in range(1, retries + 1):
        try:
            async with semaphore:
                resp = await structured_llm.ainvoke(prompt, timeout=180)
            return resp.is_match == "YES"
        except Exception as e:
            wait = 2 ** (attempt - 1)
            print(f"    [Retry {attempt}/{retries}] {e}. Waiting {wait}s…")
            if attempt < retries:
                await asyncio.sleep(wait)
            else:
                print("    [Error] Max retries reached. Marking as no match.")
                return False


async def run_llm_matching(
    structured_llm,
    findings: list[dict],
    ground_truths: list[dict],
) -> dict[str, list[str]]:
    """Run pairwise LLM comparisons, return raw matchings {uuid: [gt_ids]}."""
    semaphore = asyncio.Semaphore(CONCURRENCY_LIMIT)
    findings_by_subset = group_by_subset(findings)
    gt_by_subset = group_by_subset(ground_truths)
    all_subsets = set(findings_by_subset.keys()) | set(gt_by_subset.keys())

    raw_matchings: dict[str, list[str]] = {}

    for subset in sorted(all_subsets):
        t_findings = findings_by_subset.get(subset, [])
        t_gt = gt_by_subset.get(subset, [])

        n_cmp = len(t_findings) * len(t_gt)
        print(
            f"    Subset {subset}: "
            f"{len(t_findings)} findings x {len(t_gt)} GT = {n_cmp} comparisons"
        )

        if not t_findings or not t_gt:
            for f in t_findings:
                raw_matchings[f["uuid"]] = []
            continue

        # Launch all pairwise comparisons
        finding_to_gt: dict[int, set[int]] = defaultdict(set)
        tasks, meta = [], []
        for i, finding in enumerate(t_findings):
            for j, gt in enumerate(t_gt):
                tasks.append(compare_pair(structured_llm, finding, gt, semaphore))
                meta.append((i, j))

        results = await asyncio.gather(*tasks)

        for (i, j), is_match in zip(meta, results):
            if is_match:
                finding_to_gt[i].add(j)

        for i, finding in enumerate(t_findings):
            raw_matchings[finding["uuid"]] = [t_gt[j]["id"] for j in finding_to_gt.get(i, set())]

    return raw_matchings


async def run_single_replicate(
    config: dict,
    findings: list[dict],
    ground_truths: list[dict],
    rep_num: int,
) -> dict:
    """Run one replicate for a given LLM config."""
    print(f"  --- Replicate {rep_num} ---")
    run_name = f"{config['display_name']} rep-{rep_num}"
    os.environ["LANGCHAIN_RUN_NAME"] = run_name
    structured_llm = create_structured_llm(config)
    raw_matchings = await run_llm_matching(structured_llm, findings, ground_truths)
    metrics = compute_tp_fp(findings, ground_truths, raw_matchings)
    print(f"    => TP={metrics['true_positives']}  FP={metrics['false_positives']}")
    return metrics


# ---------------------------------------------------------------------------
# Results I/O
# ---------------------------------------------------------------------------


def load_existing_results(model_key: str) -> dict | None:
    """Load existing results for a model, if any."""
    path = RESULTS_DIR / f"{model_key}.json"
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return None


def save_results(model_key: str, results: dict):
    """Save results for a model."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    path = RESULTS_DIR / f"{model_key}.json"
    with open(path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"  Saved: {path}")


def update_results(model_key: str, config: dict, new_replicates: list[dict]) -> dict:
    """Merge new replicates into existing results and recompute stats."""
    existing = load_existing_results(model_key)

    if existing:
        all_replicates = existing.get("replicates", []) + new_replicates
    else:
        all_replicates = new_replicates

    tp_vals = [r["true_positives"] for r in all_replicates]
    fp_vals = [r["false_positives"] for r in all_replicates]

    results = {
        "model_key": model_key,
        "model_name": config["model_name"],
        "display_name": config["display_name"],
        "provider": config["provider"],
        "n_replicates": len(all_replicates),
        "replicates": all_replicates,
        "summary": {
            "true_positives_mean": statistics.mean(tp_vals),
            "true_positives_std": statistics.stdev(tp_vals) if len(tp_vals) >= 2 else 0.0,
            "false_positives_mean": statistics.mean(fp_vals),
            "false_positives_std": statistics.stdev(fp_vals) if len(fp_vals) >= 2 else 0.0,
        },
        "last_updated": datetime.now().isoformat(),
    }

    save_results(model_key, results)
    return results


# ---------------------------------------------------------------------------
# Plotting
# ---------------------------------------------------------------------------

_COLORS = ["#4e79a7", "#f28e2b", "#e15759", "#76b7b2", "#59a14f", "#edc949"]


def generate_comparison_plot(human_baseline: dict):
    """Scan all results/*.json and generate a comparison bar chart."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    # Load all results
    all_results = []
    for path in sorted(RESULTS_DIR.glob("*.json")):
        with open(path) as f:
            all_results.append(json.load(f))

    if not all_results:
        print("  No results to plot.")
        return

    n_llms = len(all_results)
    fig, ax = plt.subplots(figsize=(max(16, n_llms * 2.5), 10 / 3))

    group_labels = ["True Positives", "False Positives"]
    group_keys_mean = ["true_positives_mean", "false_positives_mean"]
    group_keys_std = ["true_positives_std", "false_positives_std"]
    group_x = np.arange(len(group_labels))

    width = 0.7 / n_llms

    for i, result in enumerate(all_results):
        summary = result["summary"]
        means = [summary[k] for k in group_keys_mean]
        stds = [summary[k] for k in group_keys_std]
        has_std = any(s > 0 for s in stds)
        offset = (i - n_llms / 2 + 0.5) * width
        bars = ax.bar(
            group_x + offset,
            means,
            width * 0.9,
            label=f"{result['display_name']}",
            color=_COLORS[i % len(_COLORS)],
            edgecolor="white",
            linewidth=0.6,
            yerr=stds if has_std else None,
            capsize=3,
            error_kw={"elinewidth": 0.8, "capthick": 0.8, "ecolor": "#333333"},
        )
        # Value labels
        for bar, m, s in zip(bars, means, stds):
            y_top = bar.get_height() + (s if has_std else 0)
            offset_y = ax.get_ylim()[1] * 0.01 if ax.get_ylim()[1] > 0 else 0.3
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                y_top + offset_y,
                f"{m:.1f}",
                ha="center",
                va="bottom",
                fontsize=6,
                fontweight="medium",
            )

    # Human baselines
    human_tp = human_baseline["true_positives"]
    human_fp = human_baseline["false_positives"]
    half = 0.45
    ax.hlines(
        human_tp,
        group_x[0] - half,
        group_x[0] + half,
        colors="red",
        linestyles="dashed",
        linewidth=2,
        label="Human",
    )
    ax.hlines(
        human_fp,
        group_x[1] - half,
        group_x[1] + half,
        colors="red",
        linestyles="dashed",
        linewidth=2,
    )

    ax.set_ylabel("Count", fontsize=10)
    ax.set_xticks(group_x)
    ax.set_xticklabels(group_labels, fontsize=10)
    ax.set_ylim(bottom=0)
    ax.grid(axis="y", alpha=0.3, linestyle="--")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.set_title("LLM Matching vs Human Annotations", fontsize=11, pad=8)

    # Legend on top in a single line
    handles, labels = ax.get_legend_handles_labels()
    fig.legend(
        handles,
        labels,
        fontsize=10,
        ncol=len(handles),
        loc="lower center",
        bbox_to_anchor=(0.5, 0.93),
        frameon=False,
        columnspacing=1.0,
        handlelength=1.2,
    )

    fig.subplots_adjust(top=0.85)
    plot_path = RESULTS_DIR / "comparison.png"
    fig.savefig(plot_path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"  Plot saved: {plot_path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def main():
    parser = argparse.ArgumentParser(
        description="Run LLM matching experiments against human annotations.",
    )
    parser.add_argument(
        "--models",
        nargs="+",
        default=None,
        help=f"Model keys to evaluate. Available: {', '.join(AVAILABLE_MODELS)}",
    )
    parser.add_argument(
        "--replicates",
        type=int,
        default=DEFAULT_REPLICATES,
        help=f"Number of new replicates to run (default: {DEFAULT_REPLICATES}). "
        "Results accumulate across runs.",
    )
    parser.add_argument(
        "--plot-only",
        action="store_true",
        default=False,
        help="Only regenerate the comparison plot from existing results (no LLM calls).",
    )
    args = parser.parse_args()

    if not args.plot_only and not args.models:
        parser.error("--models is required unless --plot-only is used.")

    # Validate model keys
    if args.models:
        for key in args.models:
            if key not in LLM_CONFIGS:
                print(f"Error: unknown model '{key}'. Available: {', '.join(AVAILABLE_MODELS)}")
                sys.exit(1)

    # 1. Load data
    print("[1] Loading data …")
    findings, tp_uuids, fp_uuids = load_selected_findings()
    ground_truths = load_ground_truths()

    # 2. Human baseline
    human_baseline = compute_human_baseline(findings, ground_truths)

    if args.plot_only:
        print("\n[plot-only] Regenerating comparison plot …")
        generate_comparison_plot(human_baseline)
        print("DONE")
        return

    print("=" * 70)
    print("LLM MATCHING EXPERIMENT")
    print("=" * 70)
    print(f"Models     : {args.models}")
    print(f"Replicates : {args.replicates}")
    print()
    print(f"  Findings: {len(findings)} (TP={len(tp_uuids)}, FP={len(fp_uuids)})")
    print(f"  Ground truths: {len(ground_truths)}")
    subsets = sorted({f["subset_name"] for f in findings})
    print(f"  Subsets: {subsets}")
    print(f"  Human: TP={human_baseline['true_positives']}  FP={human_baseline['false_positives']}")

    # 3. LLM evaluations
    print("\nRunning LLM evaluations …")
    for model_key in args.models:
        config = LLM_CONFIGS[model_key]
        print(f"\n{'─' * 50}")
        print(f"Model: {config['display_name']} ({config['model_name']})")
        print(f"{'─' * 50}")

        new_replicates = []
        for rep in range(1, args.replicates + 1):
            metrics = await run_single_replicate(config, findings, ground_truths, rep)
            new_replicates.append(metrics)

        result = update_results(model_key, config, new_replicates)
        summary = result["summary"]
        print(
            f"  Overall ({result['n_replicates']} replicates): "
            f"TP={summary['true_positives_mean']:.1f}±{summary['true_positives_std']:.1f}  "
            f"FP={summary['false_positives_mean']:.1f}±{summary['false_positives_std']:.1f}"
        )

    # 4. Generate plot
    print("\nGenerating comparison plot …")
    generate_comparison_plot(human_baseline)

    print(f"\n{'=' * 70}")
    print("DONE")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
