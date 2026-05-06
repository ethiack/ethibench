"""Temporal evaluation of claude-code-sonnet findings.

Produces a 4×3 subplot figure showing cumulative TP, FP, severity score, and
CWE coverage over elapsed time for each target (paygoat, vuln-bank, xben-090)
across 3 replicates (run_1, run_2, run_3).
"""

import json
import re
from datetime import datetime, timezone
from pathlib import Path

import matplotlib.pyplot as plt

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[1]

RUNS = ["run_1", "run_2", "run_3"]
TARGETS = [
    {"target_id": "paygoat", "subset": "PAYGoat", "gt_file": "paygoat_gt.jsonl"},
    {"target_id": "vuln-bank", "subset": "Vulnbank", "gt_file": "vulnbank_gt.jsonl"},
    {"target_id": "xben-090", "subset": "XBEN", "gt_file": "xben_gt.jsonl"},
]

GT_DIR = PROJECT_ROOT / "examples" / "gt"
EXPERIMENT_DIR = SCRIPT_DIR
EVAL_OUTPUTS_DIR = SCRIPT_DIR / "evaluation_outputs"
OUTPUT_PNG = SCRIPT_DIR / "temporal_evaluation.png"

RUN_COLORS = ["#2E6E3E", "#D35400", "#2C3E80"]
RUN_LABELS = ["Run 1", "Run 2", "Run 3"]

# ---------------------------------------------------------------------------
# Helpers (replicated from evaluate.py to keep standalone)
# ---------------------------------------------------------------------------


def cvss_to_severity_points(cvss: float | str | None) -> int:
    if cvss is None:
        return 0
    cvss = float(cvss)
    if cvss == 0.0:
        return 0
    elif cvss <= 3.9:
        return 3
    elif cvss <= 6.9:
        return 15
    elif cvss <= 8.9:
        return 30
    else:
        return 50


def extract_cwe_id(additional_info: str) -> str | None:
    m = re.search(r"CWE-(\d+)", additional_info)
    return m.group(1) if m else None


def parse_timestamp(ts: str) -> datetime:
    """Parse ISO 8601 timestamps (supports both Z suffix and +00:00 offset).

    Always returns a timezone-aware datetime in UTC.
    """
    ts = ts.replace("Z", "+00:00")
    dt = datetime.fromisoformat(ts)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------


def load_gt(gt_file: Path) -> tuple[dict[str, float | None], dict[str, str | None]]:
    """Load ground truth file, return (id→cvss, id→cwe) mappings."""
    gt_id_to_cvss: dict[str, float | None] = {}
    gt_id_to_cwe: dict[str, str | None] = {}
    with open(gt_file) as f:
        for line in f:
            if not line.strip():
                continue
            entry = json.loads(line)
            gid = entry["id"]
            gt_id_to_cvss[gid] = entry.get("cvss")
            gt_id_to_cwe[gid] = extract_cwe_id(entry.get("additional_info", ""))
    return gt_id_to_cvss, gt_id_to_cwe


def load_findings_for_target(run_name: str, target_id: str) -> list[dict]:
    """Load findings from findings_parsed.jsonl filtered by target_id."""
    parsed_file = EVAL_OUTPUTS_DIR / run_name / "findings_parsed.jsonl"
    findings = []
    with open(parsed_file) as f:
        for line in f:
            if not line.strip():
                continue
            entry = json.loads(line)
            if entry.get("target_id") == target_id:
                findings.append(entry)
    return findings


def load_matchings(run_name: str, subset: str) -> dict[str, list[str]]:
    """Load bipartite matchings for a subset. Returns uuid → list of matched GT IDs."""
    matchings_file = EVAL_OUTPUTS_DIR / run_name / "matchings" / f"matchings_{subset}.json"
    with open(matchings_file) as f:
        data = json.load(f)
    # Format is a JSON array with one dict element
    matchings_dict = data[0] if isinstance(data, list) else data
    return {
        uuid: mdata.get("selected_gt_ids", [])
        for uuid, mdata in matchings_dict.items()
    }


def load_start_time(run_name: str, target_id: str) -> datetime:
    """Load start_time from metrics.json for a given run/target."""
    metrics_file = EXPERIMENT_DIR / run_name / target_id / "metrics.json"
    with open(metrics_file) as f:
        data = json.load(f)
    return parse_timestamp(data["start_time"])


# ---------------------------------------------------------------------------
# Temporal metric computation
# ---------------------------------------------------------------------------


def compute_temporal_metrics(
    findings: list[dict],
    matchings: dict[str, list[str]],
    start_time: datetime,
    gt_id_to_cvss: dict[str, float | None],
    gt_id_to_cwe: dict[str, str | None],
) -> dict[str, list[float]]:
    """Compute cumulative TP, FP, severity, CWE coverage over time.

    Returns dict with keys: elapsed_min, tp, fp, severity, cwe_coverage.
    Each value is a list aligned by finding index (sorted by timestamp).
    Includes a t=0 origin point.
    """
    # Sort findings by timestamp
    findings_sorted = sorted(findings, key=lambda f: parse_timestamp(f["timestamp"]))

    elapsed_min = [0.0]
    tp = [0]
    fp = [0]
    severity = [0]
    cwe_coverage = [0]

    cum_tp = 0
    cum_fp = 0
    cum_severity = 0
    seen_cwes: set[str] = set()

    for finding in findings_sorted:
        ts = parse_timestamp(finding["timestamp"])
        minutes = (ts - start_time).total_seconds() / 60.0

        uuid = finding["uuid"]
        matched_gt_ids = matchings.get(uuid, [])

        if matched_gt_ids:
            cum_tp += 1
            for gt_id in matched_gt_ids:
                cum_severity += cvss_to_severity_points(gt_id_to_cvss.get(gt_id))
                cwe = gt_id_to_cwe.get(gt_id)
                if cwe:
                    seen_cwes.add(cwe)
        else:
            cum_fp += 1

        elapsed_min.append(minutes)
        tp.append(cum_tp)
        fp.append(cum_fp)
        severity.append(cum_severity)
        cwe_coverage.append(len(seen_cwes))

    return {
        "elapsed_min": elapsed_min,
        "tp": tp,
        "fp": fp,
        "severity": severity,
        "cwe_coverage": cwe_coverage,
    }


# ---------------------------------------------------------------------------
# Plotting
# ---------------------------------------------------------------------------

METRICS_CONFIG = [
    {"key": "tp", "label": "True Positives"},
    {"key": "fp", "label": "False Positives"},
    {"key": "severity", "label": "Severity Score"},
    {"key": "cwe_coverage", "label": "CWE Coverage"},
]


def plot_temporal_evaluation():
    """Generate the 4×3 temporal evaluation figure."""
    fig, axes = plt.subplots(4, 3, figsize=(15, 12))

    for col_idx, target_cfg in enumerate(TARGETS):
        target_id = target_cfg["target_id"]
        subset = target_cfg["subset"]
        gt_file = GT_DIR / target_cfg["gt_file"]

        gt_id_to_cvss, gt_id_to_cwe = load_gt(gt_file)

        for run_idx, run_name in enumerate(RUNS):
            start_time = load_start_time(run_name, target_id)
            findings = load_findings_for_target(run_name, target_id)
            matchings = load_matchings(run_name, subset)

            metrics = compute_temporal_metrics(
                findings, matchings, start_time, gt_id_to_cvss, gt_id_to_cwe
            )

            for row_idx, metric_cfg in enumerate(METRICS_CONFIG):
                ax = axes[row_idx, col_idx]
                ax.plot(
                    metrics["elapsed_min"],
                    metrics[metric_cfg["key"]],
                    color=RUN_COLORS[run_idx],
                    label=RUN_LABELS[run_idx],
                    linewidth=1.4,
                    alpha=0.8,
                    marker="o",
                    markersize=3,
                )

        # Configure axes
        for row_idx, metric_cfg in enumerate(METRICS_CONFIG):
            ax = axes[row_idx, col_idx]
            if row_idx == 0:
                ax.set_title(target_id, fontsize=11, fontweight="bold")
            if col_idx == 0:
                ax.set_ylabel(metric_cfg["label"], fontsize=10)
            if row_idx == len(METRICS_CONFIG) - 1:
                ax.set_xlabel("Elapsed Time (min)", fontsize=9)
            ax.grid(True, alpha=0.3)
            ax.set_xlim(left=0)
            ax.set_ylim(bottom=0)
            if row_idx == 0 and col_idx == 2:
                ax.legend(loc="lower right", fontsize=8)

    fig.suptitle(
        "Temporal Evaluation \u2014 claude-code-sonnet",
        fontsize=13,
        fontweight="bold",
        y=0.98,
    )
    plt.tight_layout(rect=[0, 0, 1, 0.96])
    plt.savefig(OUTPUT_PNG, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"Figure saved to: {OUTPUT_PNG}")


if __name__ == "__main__":
    plot_temporal_evaluation()
