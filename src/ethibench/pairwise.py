"""Pairwise A/B statistical comparison between top experiments."""

import json
import math
from itertools import combinations
from pathlib import Path

from loguru import logger
from scipy.stats import ttest_ind


METRICS = ["f1_score", "f05_score", "recall", "precision"]
METRIC_LABELS = {"f1_score": "F1", "f05_score": "F0.5", "recall": "Recall", "precision": "Precision"}


def load_per_run_overall(experiment_dir: Path) -> list[dict]:
    """Load per-run overall unweighted results for an experiment.

    Returns a list of dicts (one per run) with metric values.
    """
    eval_dir = experiment_dir / "evaluation_outputs"
    run_dirs = sorted(
        [d for d in eval_dir.iterdir() if d.is_dir() and d.name.startswith("run")],
        key=lambda p: p.name,
    )

    # If no run_* dirs, treat eval_dir as single run
    if not run_dirs:
        run_dirs = [eval_dir]

    results = []
    for rd in run_dirs:
        results_avg = rd / "results_avg"
        unw_file = results_avg / "evaluation_results_unweighted.json"
        if unw_file.exists():
            with open(unw_file) as f:
                results.append(json.load(f))

    return results


def select_top_k(all_overall: dict[str, dict], k: int = 4) -> list[str]:
    """Select top-k experiment labels by overall unweighted F1 score (descending)."""
    ranked = sorted(all_overall.items(), key=lambda x: x[1].get("f1_score", 0), reverse=True)
    return [label for label, _ in ranked[:k]]


def _cohens_d(scores_a: list[float], scores_b: list[float]) -> float:
    """Compute Cohen's d using pooled standard deviation (equal-n formula)."""
    mean_a = sum(scores_a) / len(scores_a)
    mean_b = sum(scores_b) / len(scores_b)
    var_a = sum((x - mean_a) ** 2 for x in scores_a) / (len(scores_a) - 1)
    var_b = sum((x - mean_b) ** 2 for x in scores_b) / (len(scores_b) - 1)
    pooled_sd = math.sqrt((var_a + var_b) / 2)
    if pooled_sd == 0:
        return 0.0
    return (mean_a - mean_b) / pooled_sd


def compute_pairwise_stats(scores_a: list[float], scores_b: list[float]) -> dict:
    """Compute comparison statistics between two score lists.

    Returns dict with difference (mean_A - mean_B), p_value, cohens_d.
    """
    mean_a = sum(scores_a) / len(scores_a)
    mean_b = sum(scores_b) / len(scores_b)
    difference = mean_a - mean_b

    # Welch's t-test
    if len(scores_a) >= 2 and len(scores_b) >= 2:
        _, p_value = ttest_ind(scores_a, scores_b, equal_var=False)
    else:
        p_value = float("nan")

    d = _cohens_d(scores_a, scores_b)

    return {"difference": difference, "p_value": p_value, "cohens_d": d}


def generate_pairwise_comparison(
    experiment_dirs: list[Path],
    labels: list[str],
    all_overall: dict[str, dict],
) -> dict | None:
    """Generate pairwise A/B comparison data for the top 4 experiments.

    Returns a dict with pair comparison results, or None if < 4 experiments.
    """
    if len(labels) < 4:
        logger.warning("Need at least 4 experiments for pairwise comparison, skipping.")
        return None

    top4 = select_top_k(all_overall, k=4)
    logger.info(f"Top 4 experiments by F1: {top4}")

    # Map labels to dirs
    label_to_dir = dict(zip(labels, experiment_dirs))

    # Load per-run data for top 4
    per_run_data: dict[str, list[dict]] = {}
    for label in top4:
        exp_dir = label_to_dir[label]
        runs = load_per_run_overall(exp_dir)
        if not runs:
            logger.warning(f"No per-run data for {label}, skipping pairwise.")
            return None
        per_run_data[label] = runs

    # All pairs, ordered so A has better F1
    pairs = []
    for a, b in combinations(top4, 2):
        f1_a = all_overall[a].get("f1_score", 0)
        f1_b = all_overall[b].get("f1_score", 0)
        if f1_a >= f1_b:
            pairs.append((a, b))
        else:
            pairs.append((b, a))

    # Sort pairs by descending F1 difference
    pairs.sort(key=lambda p: all_overall[p[0]].get("f1_score", 0) - all_overall[p[1]].get("f1_score", 0), reverse=True)

    # Compute stats for each pair × each metric
    comparison_results = []
    for label_a, label_b in pairs:
        pair_data = {"a": label_a, "b": label_b, "metrics": {}}
        for metric in METRICS:
            scores_a = [r[metric] for r in per_run_data[label_a] if metric in r]
            scores_b = [r[metric] for r in per_run_data[label_b] if metric in r]
            stats = compute_pairwise_stats(scores_a, scores_b)
            # Also store mean scores for display
            stats["mean_a"] = sum(scores_a) / len(scores_a) if scores_a else 0
            stats["mean_b"] = sum(scores_b) / len(scores_b) if scores_b else 0
            pair_data["metrics"][metric] = stats
        comparison_results.append(pair_data)

    return {"top4": top4, "pairs": comparison_results}


def render_markdown_table(pairwise_data: dict) -> str:
    """Render the pairwise comparison as a Markdown table."""
    lines = []
    lines.append("# Pairwise A/B Statistical Comparison (Top 4 by F1)\n")
    lines.append(f"Top 4 experiments: {', '.join(pairwise_data['top4'])}\n")
    lines.append("Statistical tests use per-run overall (unweighted) scores (n=3 per experiment).\n")
    lines.append("")

    # Table header
    header = "| | F1 | F0.5 | Recall | Precision |"
    sep = "|---|---|---|---|---|"
    lines.append(header)
    lines.append(sep)

    for pair in pairwise_data["pairs"]:
        label_a = pair["a"]
        label_b = pair["b"]

        # Title row — centered spanning description
        lines.append(f"| **{label_a} vs {label_b}** | | | | |")

        # Difference row
        diffs = []
        for metric in METRICS:
            d = pair["metrics"][metric]["difference"]
            diffs.append(f"{d*100:+.2f}%")
        lines.append(f"| Difference | {' | '.join(diffs)} |")

        # p-value row
        pvals = []
        for metric in METRICS:
            p = pair["metrics"][metric]["p_value"]
            if math.isnan(p):
                pvals.append("—")
            else:
                pvals.append(f"{p:.4f}")
        lines.append(f"| p-value | {' | '.join(pvals)} |")

        # Cohen's d row
        ds = []
        for metric in METRICS:
            cd = pair["metrics"][metric]["cohens_d"]
            ds.append(f"{cd:.3f}")
        lines.append(f"| Cohen's d | {' | '.join(ds)} |")

    lines.append("")
    lines.append("*Note: With n=3 per experiment, statistical power is limited. "
                 "Interpret p-values cautiously.*\n")

    return "\n".join(lines)


def render_latex_table(pairwise_data: dict) -> str:
    """Render the pairwise comparison as a LaTeX booktabs table."""
    lines = []
    lines.append(r"\begin{table}[ht]")
    lines.append(r"\centering")
    lines.append(r"\caption{Pairwise A/B statistical comparison (top 4 experiments by F1).}")
    lines.append(r"\label{tab:pairwise}")
    lines.append(r"\begin{tabular}{lcccc}")
    lines.append(r"\toprule")
    lines.append(r" & F1 & F0.5 & Recall & Precision \\")
    lines.append(r"\midrule")

    for i, pair in enumerate(pairwise_data["pairs"]):
        label_a = pair["a"].replace("_", r"\_").replace("-", r"-")
        label_b = pair["b"].replace("_", r"\_").replace("-", r"-")

        # Title row — multicolumn centered
        lines.append(rf"\multicolumn{{5}}{{c}}{{\textbf{{{label_a} vs {label_b}}}}} \\")

        # Difference row
        diffs = []
        for metric in METRICS:
            d = pair["metrics"][metric]["difference"]
            diffs.append(f"{d*100:+.2f}\\%")
        lines.append(f"Difference & {' & '.join(diffs)} \\\\")

        # p-value row
        pvals = []
        for metric in METRICS:
            p = pair["metrics"][metric]["p_value"]
            if math.isnan(p):
                pvals.append("---")
            else:
                pvals.append(f"{p:.4f}")
        lines.append(f"p-value & {' & '.join(pvals)} \\\\")

        # Cohen's d row
        ds = []
        for metric in METRICS:
            cd = pair["metrics"][metric]["cohens_d"]
            ds.append(f"{cd:.3f}")
        lines.append(f"Cohen's d & {' & '.join(ds)} \\\\")

        # Separator between pairs (except last)
        if i < len(pairwise_data["pairs"]) - 1:
            lines.append(r"\midrule")

    lines.append(r"\bottomrule")
    lines.append(r"\end{tabular}")
    lines.append(r"\end{table}")

    return "\n".join(lines)
