"""Load and aggregate cost/token metrics from per-target metrics.json files."""

import json
import statistics
from datetime import datetime
from pathlib import Path

from loguru import logger

_NUMERIC_FIELDS = [
    "total_cost",
    "input_cost",
    "output_cost",
    "input_tokens",
    "output_tokens",
    "total_tokens",
    "duration_seconds",
    "cost_per_hour",
]


def load_run_metrics(run_dir: Path) -> dict | None:
    """Load metrics from per-target subdirectories in a run directory.

    Each target subdirectory (``run_dir/<target_id>/metrics.json``) may contain
    a flat JSON with cost, token, and duration fields.

    Returns:
        Dict with aggregated totals and a ``per_target`` breakdown,
        or ``None`` if no per-target metrics files are found.
    """
    per_target: dict[str, dict] = {}
    for child in sorted(run_dir.iterdir()):
        if not child.is_dir():
            continue
        metrics_file = child / "metrics.json"
        if not metrics_file.exists():
            continue
        with open(metrics_file) as f:
            data = json.load(f)
        per_target[child.name] = _normalise(data)

    if not per_target:
        return None

    result = _sum_per_target(per_target)
    result["per_target"] = per_target
    return result


def _normalise(data: dict) -> dict:
    """Normalise a per-target metrics dict into a standard flat form."""
    result = {
        "total_cost": data.get("total_cost", 0),
        "input_cost": data.get("input_cost", 0),
        "output_cost": data.get("output_cost", 0),
        "input_tokens": int(data.get("input_tokens", 0)),
        "output_tokens": int(data.get("output_tokens", 0)),
        "total_tokens": int(
            data.get(
                "total_tokens",
                data.get("input_tokens", 0) + data.get("output_tokens", 0),
            )
        ),
    }

    # Duration
    if "duration_seconds" in data:
        result["duration_seconds"] = data["duration_seconds"]
    elif "start_time" in data and "end_time" in data:
        result["duration_seconds"] = _parse_duration(data["start_time"], data["end_time"])

    for key in ("start_time", "end_time"):
        if key in data:
            result[key] = data[key]

    dur = result.get("duration_seconds", 0)
    if dur > 0:
        result["cost_per_hour"] = result["total_cost"] / (dur / 3600)

    return result


def _parse_duration(start: str, end: str) -> float:
    """Parse duration in seconds from start/end time strings."""
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f"):
        try:
            t0 = datetime.strptime(start, fmt)
            t1 = datetime.strptime(end, fmt)
            return (t1 - t0).total_seconds()
        except ValueError:
            continue
    return 0


def _sum_per_target(per_target: dict[str, dict]) -> dict:
    """Compute aggregate totals by summing per-target metrics."""
    sum_fields = [
        "total_cost",
        "input_cost",
        "output_cost",
        "input_tokens",
        "output_tokens",
        "total_tokens",
        "duration_seconds",
    ]
    summed: dict[str, float] = {}
    for field in sum_fields:
        total = sum(m.get(field, 0) for m in per_target.values())
        if total:
            summed[field] = total

    n = len(per_target)
    if n > 0 and summed.get("total_cost", 0) > 0:
        summed["cost_per_target"] = summed["total_cost"] / n
    dur = summed.get("duration_seconds", 0)
    if dur > 0:
        summed["cost_per_hour"] = summed["total_cost"] / (dur / 3600)

    return summed


def aggregate_run_metrics(
    run_dirs: list[Path],
    evaluation_results: dict | None = None,
) -> dict | None:
    """Aggregate metrics across multiple runs (mean ± stdev).

    Args:
        run_dirs: Run directories, each containing target subdirectories.
        evaluation_results: Optional unweighted evaluation results for cost/TP.

    Returns:
        Aggregated metrics with per_target breakdown, or None if no metrics found.
    """
    all_metrics: list[dict] = []
    for rd in run_dirs:
        m = load_run_metrics(rd)
        if m is not None:
            all_metrics.append(m)

    if not all_metrics:
        return None

    result: dict = {}
    for field in _NUMERIC_FIELDS:
        values = [m[field] for m in all_metrics if field in m]
        if values:
            result[field] = statistics.mean(values)
            result[f"{field}_std"] = statistics.stdev(values) if len(values) >= 2 else 0.0

    # Per-target aggregation
    all_target_ids: set[str] = set()
    for m in all_metrics:
        if "per_target" in m:
            all_target_ids.update(m["per_target"].keys())

    if all_target_ids:
        per_target_avg: dict[str, dict] = {}
        for tid in sorted(all_target_ids):
            target_runs = [
                m["per_target"][tid]
                for m in all_metrics
                if "per_target" in m and tid in m["per_target"]
            ]
            avg: dict = {}
            for field in _NUMERIC_FIELDS:
                values = [tm[field] for tm in target_runs if field in tm]
                if values:
                    avg[field] = statistics.mean(values)
                    avg[f"{field}_std"] = statistics.stdev(values) if len(values) >= 2 else 0.0
            per_target_avg[tid] = avg
        result["per_target"] = per_target_avg

        n_targets = len(all_target_ids)
        if n_targets > 0 and "total_cost" in result:
            result["cost_per_target"] = result["total_cost"] / n_targets

    # Cost per TP
    if evaluation_results and evaluation_results.get("true_positives", 0) > 0:
        tp = evaluation_results["true_positives"]
        result["cost_per_tp"] = result["total_cost"] / tp

    result["n_runs"] = len(all_metrics)
    return result


def save_metrics_summary(metrics: dict, output_path: Path) -> None:
    """Save aggregated metrics to a JSON file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(metrics, f, indent=2)
    logger.info(f"Metrics summary → {output_path}")
