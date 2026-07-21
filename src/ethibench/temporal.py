"""Temporal evaluation — cumulative metrics over elapsed time.

Produces a 4×N subplot figure showing cumulative TP, FP, severity score, and
CWE coverage over elapsed time for each target across runs.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

import matplotlib.pyplot as plt
from loguru import logger

from ethibench.datasets import DatasetCollection
from ethibench.evaluate import cvss_to_severity_points, extract_cwe_id, load_jsonl

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_RUN_COLORS = [
    "#2E6E3E",
    "#D35400",
    "#2C3E80",
    "#8E44AD",
    "#C0392B",
    "#16A085",
    "#F39C12",
    "#2980B9",
]

_METRICS_CONFIG = [
    {"key": "tp", "label": "True Positives"},
    {"key": "fp", "label": "False Positives"},
    {"key": "severity", "label": "Severity Score"},
    {"key": "cwe_coverage", "label": "CWE Coverage"},
]


def _parse_timestamp(ts: str) -> datetime:
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


def _load_gt_mappings(
    gt_dir: Path, subset_name: str
) -> tuple[dict[str, float | None], dict[str, str | None]]:
    """Load ground truth entries for a subset, return (id→cvss, id→cwe) mappings."""
    entries = load_jsonl(gt_dir, subset_filter=subset_name)
    gt_id_to_cvss: dict[str, float | None] = {}
    gt_id_to_cwe: dict[str, str | None] = {}
    for entry in entries:
        gid = entry["id"]
        gt_id_to_cvss[gid] = entry.get("cvss")
        gt_id_to_cwe[gid] = extract_cwe_id(entry.get("additional_info", ""))
    return gt_id_to_cvss, gt_id_to_cwe


def _load_findings_for_target(
    eval_output_dir: Path, target_id: str
) -> tuple[list[dict], int]:
    """Load findings from findings_parsed.jsonl filtered by target_id.

    Returns (findings_with_timestamp, count_without_timestamp).
    """
    parsed_file = eval_output_dir / "findings_parsed.jsonl"
    if not parsed_file.exists():
        return [], 0

    with_ts: list[dict] = []
    without_ts = 0
    with open(parsed_file) as f:
        for line in f:
            if not line.strip():
                continue
            entry = json.loads(line)
            if entry.get("target_id") != target_id:
                continue
            if "timestamp" in entry and entry["timestamp"]:
                with_ts.append(entry)
            else:
                without_ts += 1
    return with_ts, without_ts


def _load_matchings(eval_output_dir: Path, subset: str) -> dict[str, list[str]]:
    """Load bipartite matchings for a subset. Returns uuid → list of matched GT IDs."""
    matchings_file = eval_output_dir / "matchings" / f"matchings_{subset}.json"
    if not matchings_file.exists():
        return {}
    with open(matchings_file) as f:
        data = json.load(f)
    matchings_dict = data[0] if isinstance(data, list) else data
    return {
        uuid: mdata.get("selected_gt_ids", [])
        for uuid, mdata in matchings_dict.items()
    }


def _load_start_time(
    experiment_dir: Path,
    run_dir_name: str | None,
    target_id: str,
    findings: list[dict],
) -> datetime | None:
    """Load start_time from metrics.json, falling back to earliest finding timestamp.

    For multi-run experiments: experiment_dir/run_dir_name/target_id/metrics.json
    For single-run experiments: experiment_dir/target_id/metrics.json
    """
    if run_dir_name is not None:
        metrics_file = experiment_dir / run_dir_name / target_id / "metrics.json"
    else:
        metrics_file = experiment_dir / target_id / "metrics.json"

    if metrics_file.exists():
        with open(metrics_file) as f:
            data = json.load(f)
        if "start_time" in data:
            return _parse_timestamp(data["start_time"])

    # Fallback to earliest finding timestamp
    if findings:
        logger.warning(
            f"No metrics.json start_time for {target_id}"
            + (f" in {run_dir_name}" if run_dir_name else "")
            + "; using earliest finding timestamp as t=0."
        )
        return min(_parse_timestamp(f["timestamp"]) for f in findings)

    return None


# ---------------------------------------------------------------------------
# Temporal metric computation
# ---------------------------------------------------------------------------


def _compute_temporal_metrics(
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
    findings_sorted = sorted(findings, key=lambda f: _parse_timestamp(f["timestamp"]))

    elapsed_min: list[float] = [0.0]
    tp: list[int] = [0]
    fp: list[int] = [0]
    severity: list[int] = [0]
    cwe_coverage: list[int] = [0]

    cum_tp = 0
    cum_fp = 0
    cum_severity = 0
    seen_cwes: set[str] = set()

    for finding in findings_sorted:
        ts = _parse_timestamp(finding["timestamp"])
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
# Main entry point
# ---------------------------------------------------------------------------


def run_temporal_evaluation(
    experiment_dir: Path,
    dc: DatasetCollection,
    gt_dir: Path,
    output_path: Path | None = None,
) -> None:
    """Generate a temporal evaluation plot for an experiment.

    Args:
        experiment_dir: Root experiment directory (contains run_* subdirs or
            target subdirs directly).
        dc: Loaded DatasetCollection.
        gt_dir: Path to ground truth JSONL files directory.
        output_path: Where to save the PNG. Defaults to
            ``experiment_dir/evaluation_outputs/plots/temporal_evaluation.png``.
    """
    eval_outputs_dir = experiment_dir / "evaluation_outputs"
    if not eval_outputs_dir.is_dir():
        logger.error(
            f"No evaluation_outputs/ directory found in {experiment_dir}. "
            "Run `ethibench evaluate` first."
        )
        raise SystemExit(1)

    # Detect runs
    run_candidates = sorted(
        [d for d in experiment_dir.iterdir() if d.is_dir() and d.name.startswith("run")],
        key=lambda p: p.name,
    )
    multi_run = bool(run_candidates)

    if multi_run:
        run_names = [d.name for d in run_candidates]
    else:
        run_names = [None]  # type: ignore[list-item]

    # Build target list from the dataset
    targets: list[dict[str, str]] = []
    for dataset in dc.datasets:
        for target in dataset.targets:
            targets.append(
                {"target_id": target.target_id, "subset": dataset.subset}
            )

    if not targets:
        logger.error("No targets found in the dataset.")
        raise SystemExit(1)

    # --- Phase 1: check timestamp availability per run ---
    # run_name → total findings with timestamp across all targets
    run_ts_counts: dict[str | None, int] = {}
    run_no_ts_counts: dict[str | None, int] = {}
    # (run_name, target_id) → count without timestamp
    per_run_target_no_ts: dict[tuple[str | None, str], int] = {}

    for run_name in run_names:
        if multi_run:
            eval_dir = eval_outputs_dir / run_name
        else:
            eval_dir = eval_outputs_dir

        total_with = 0
        total_without = 0
        for t in targets:
            with_ts, without_ts = _load_findings_for_target(eval_dir, t["target_id"])
            total_with += len(with_ts)
            total_without += without_ts
            if without_ts > 0:
                per_run_target_no_ts[(run_name, t["target_id"])] = without_ts

        run_ts_counts[run_name] = total_with
        run_no_ts_counts[run_name] = total_without

    # Determine which runs are usable
    runs_without_ts = [r for r in run_names if run_ts_counts[r] == 0]
    runs_with_ts = [r for r in run_names if run_ts_counts[r] > 0]

    if not runs_with_ts:
        logger.error("No findings have timestamp in this experiment.")
        raise SystemExit(1)

    # Print warnings for missing timestamps
    if multi_run:
        if runs_without_ts:
            labels = ", ".join(r for r in runs_without_ts)
            logger.warning(f"No timestamps available for {labels}.")
        for run_name in runs_with_ts:
            no_ts = run_no_ts_counts[run_name]
            if no_ts > 0:
                affected = [
                    f"{cnt} in {tid}"
                    for (rn, tid), cnt in per_run_target_no_ts.items()
                    if rn == run_name
                ]
                logger.warning(
                    f"{no_ts} findings in {run_name} do not have timestamp "
                    f"({', '.join(affected)})."
                )
    else:
        no_ts = run_no_ts_counts[None]
        if no_ts > 0:
            affected = [
                f"{cnt} in {tid}"
                for (rn, tid), cnt in per_run_target_no_ts.items()
            ]
            logger.warning(
                f"{no_ts} findings do not have timestamp "
                f"({', '.join(affected)})."
            )

    # --- Phase 2: compute metrics and plot ---
    n_targets = len(targets)
    n_runs = len(runs_with_ts)

    fig, axes = plt.subplots(
        len(_METRICS_CONFIG), n_targets, figsize=(5 * n_targets, 12), squeeze=False
    )

    run_colors = _RUN_COLORS
    run_labels = (
        [r.replace("_", " ").title() for r in runs_with_ts]
        if multi_run
        else [""]
    )

    for col_idx, target_cfg in enumerate(targets):
        target_id = target_cfg["target_id"]
        subset = target_cfg["subset"]

        gt_id_to_cvss, gt_id_to_cwe = _load_gt_mappings(gt_dir, subset)

        for run_idx, run_name in enumerate(runs_with_ts):
            if multi_run:
                eval_dir = eval_outputs_dir / run_name
            else:
                eval_dir = eval_outputs_dir

            findings, _ = _load_findings_for_target(eval_dir, target_id)
            if not findings:
                continue

            matchings = _load_matchings(eval_dir, subset)
            start_time = _load_start_time(
                experiment_dir, run_name, target_id, findings
            )
            if start_time is None:
                continue

            metrics = _compute_temporal_metrics(
                findings, matchings, start_time, gt_id_to_cvss, gt_id_to_cwe
            )

            color = run_colors[run_idx % len(run_colors)]
            for row_idx, metric_cfg in enumerate(_METRICS_CONFIG):
                ax = axes[row_idx, col_idx]
                ax.plot(
                    metrics["elapsed_min"],
                    metrics[metric_cfg["key"]],
                    color=color,
                    label=run_labels[run_idx] if run_labels[run_idx] else None,
                    linewidth=1.4,
                    alpha=0.8,
                    marker="o",
                    markersize=3,
                )

        # Configure axes
        for row_idx, metric_cfg in enumerate(_METRICS_CONFIG):
            ax = axes[row_idx, col_idx]
            if row_idx == 0:
                ax.set_title(target_id, fontsize=11, fontweight="bold")
            if col_idx == 0:
                ax.set_ylabel(metric_cfg["label"], fontsize=10)
            if row_idx == len(_METRICS_CONFIG) - 1:
                ax.set_xlabel("Elapsed Time (min)", fontsize=9)
            ax.grid(True, alpha=0.3)
            ax.set_xlim(left=0)
            ax.set_ylim(bottom=0)
            if row_idx == 0 and col_idx == n_targets - 1 and multi_run:
                ax.legend(loc="lower right", fontsize=8)

    experiment_name = experiment_dir.name
    fig.suptitle(
        f"Temporal Evaluation \u2014 {experiment_name}",
        fontsize=13,
        fontweight="bold",
        y=0.98,
    )
    plt.tight_layout(rect=[0, 0, 1, 0.96])

    if output_path is None:
        output_path = eval_outputs_dir / "plots" / "temporal_evaluation.png"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close()
    logger.info(f"Temporal evaluation figure saved to {output_path}")
