"""Results aggregation — averaging across replicates and runs."""

import json
import statistics
from pathlib import Path

from loguru import logger

from ethibench.evaluate import calculate_metrics

NUMERIC_FIELDS = [
    "true_positives",
    "false_positives",
    "false_negatives",
    "duplicates",
    "precision",
    "recall",
    "f1_score",
    "f05_score",
    "severity_score",
    "cwe_coverage",
]


def calculate_statistics(data: list[dict]) -> dict:
    """Calculate mean and stdev for each numeric metric across a list of result dicts."""
    result = {}
    for field in NUMERIC_FIELDS:
        values = [entry[field] for entry in data if field in entry]
        if values:
            result[field] = statistics.mean(values)
            result[f"{field}_std"] = statistics.stdev(values) if len(values) >= 2 else 0.0
    if data and "subset_name" in data[0]:
        result["subset_name"] = data[0]["subset_name"]
    return result


def calculate_unweighted_overall(results: list[dict]) -> dict:
    """Aggregate raw counts across subsets and recompute metrics."""
    total_tp = sum(r["true_positives"] for r in results)
    total_fp = sum(r["false_positives"] for r in results)
    total_fn = sum(r["false_negatives"] for r in results)
    total_dup = sum(r.get("duplicates", 0) for r in results)
    total_severity = sum(r.get("severity_score", 0) for r in results)
    total_cwe = sum(r.get("cwe_coverage", 0) for r in results)
    precision, recall, f1, f05 = calculate_metrics(total_tp, total_fp, total_fn)
    return {
        "true_positives": total_tp,
        "false_positives": total_fp,
        "false_negatives": total_fn,
        "duplicates": total_dup,
        "precision": precision,
        "recall": recall,
        "f1_score": f1,
        "f05_score": f05,
        "severity_score": total_severity,
        "cwe_coverage": total_cwe,
    }


def calculate_weighted_overall(results: list[dict], weights: dict[str, float]) -> dict:
    """Weighted aggregation across subsets."""
    total_weight = sum(weights.get(r.get("subset_name", ""), 0) for r in results)
    if total_weight == 0:
        return {"precision": 0, "recall": 0, "f1_score": 0, "f05_score": 0, "severity_score": 0}
    norm = {name: w / total_weight for name, w in weights.items()}
    wtp = wfp = wfn = 0.0
    weighted_severity = 0.0
    weighted_cwe = 0.0
    for r in results:
        w = norm.get(r.get("subset_name", ""), 0)
        wtp += r["true_positives"] * w
        wfp += r["false_positives"] * w
        wfn += r["false_negatives"] * w
        weighted_severity += r.get("severity_score", 0) * w
        weighted_cwe += r.get("cwe_coverage", 0) * w
    precision, recall, f1, f05 = calculate_metrics(wtp, wfp, wfn)
    return {
        "precision": precision,
        "recall": recall,
        "f1_score": f1,
        "f05_score": f05,
        "severity_score": round(weighted_severity),
        "cwe_coverage": round(weighted_cwe),
    }


def average_results_folder(input_folder: Path, output_folder: Path) -> None:
    """Average replicate results in input_folder → output_folder."""
    output_folder.mkdir(parents=True, exist_ok=True)
    for json_file in input_folder.glob("*.json"):
        with open(json_file) as f:
            data = json.load(f)
        if not isinstance(data, list) or not data:
            continue
        avg = calculate_statistics(data)
        with open(output_folder / json_file.name, "w") as f:
            json.dump(avg, f, indent=2)
        logger.info(f"Averaged: {json_file.name}")


def add_overall_results(results_avg_folder: Path, weights: dict[str, float]) -> None:
    """Add unweighted and weighted overall result files to a results_avg folder."""
    subset_order = sorted(weights.keys(), key=lambda x: weights[x], reverse=True)
    results = []
    for json_file in results_avg_folder.glob("evaluation_results_*.json"):
        name = json_file.stem.replace("evaluation_results_", "")
        if name in ("unweighted", "weighted"):
            continue
        with open(json_file) as f:
            data = json.load(f)
        if isinstance(data, dict) and data.get("subset_name") in subset_order:
            results.append(data)

    if not results:
        return

    unw = calculate_unweighted_overall(results)
    with open(results_avg_folder / "evaluation_results_unweighted.json", "w") as f:
        json.dump(unw, f, indent=2)

    wt = calculate_weighted_overall(results, weights)
    with open(results_avg_folder / "evaluation_results_weighted.json", "w") as f:
        json.dump(wt, f, indent=2)


def aggregate_across_runs(run_dirs: list[Path], output_folder: Path) -> None:
    """Aggregate results_avg from multiple run directories into a single results_avg_all."""
    output_folder.mkdir(parents=True, exist_ok=True)

    # Collect all results_avg folders
    results_avg_folders = []
    for rd in run_dirs:
        ravg = rd / "results_avg"
        if ravg.is_dir():
            results_avg_folders.append(ravg)

    if not results_avg_folders:
        return

    # Get all JSON filenames from the first folder
    json_files = [f.name for f in results_avg_folders[0].iterdir() if f.suffix == ".json"]

    for json_filename in json_files:
        data = []
        for ravg in results_avg_folders:
            path = ravg / json_filename
            if path.exists():
                with open(path) as f:
                    data.append(json.load(f))
        if data:
            avg = calculate_statistics(data)
            with open(output_folder / json_filename, "w") as f:
                json.dump(avg, f, indent=2)


def average_all_results(
    output_dir: Path,
    run_dirs: list[Path],
    weights: dict[str, float],
) -> None:
    """Full aggregation pipeline: per-run averaging → overall → cross-run aggregation."""
    for rd in run_dirs:
        results_folder = rd / "results"
        if not results_folder.is_dir():
            continue
        results_avg = rd / "results_avg"
        average_results_folder(results_folder, results_avg)
        add_overall_results(results_avg, weights)

    if len(run_dirs) > 1:
        aggregate_across_runs(run_dirs, output_dir / "results_avg_all")


def load_experiment_results(experiment_dir: Path) -> tuple[Path, list[dict], dict | None] | None:
    """Load evaluation results for an experiment directory.

    Looks for results in:
      1. <experiment_dir>/evaluation_outputs/results_avg_all/  (multi-run)
      2. <experiment_dir>/evaluation_outputs/results_avg/      (single-run fallback)

    Returns:
        Tuple of (results_folder, subset_results, cost_metrics) or None if no results found.
    """
    eval_dir = experiment_dir / "evaluation_outputs"
    results_folder = None

    for candidate in ("results_avg_all", "results_avg"):
        path = eval_dir / candidate
        if path.is_dir() and any(path.glob("evaluation_results_*.json")):
            results_folder = path
            break

    if results_folder is None:
        return None

    # Load per-subset results
    subset_results = []
    for json_file in sorted(results_folder.glob("evaluation_results_*.json")):
        name = json_file.stem.replace("evaluation_results_", "")
        if name in ("unweighted", "weighted"):
            continue
        with open(json_file) as f:
            data = json.load(f)
        if isinstance(data, dict):
            subset_results.append(data)

    # Load overall results
    overall = {}
    for kind in ("unweighted", "weighted"):
        overall_file = results_folder / f"evaluation_results_{kind}.json"
        if overall_file.exists():
            with open(overall_file) as f:
                overall[kind] = json.load(f)

    # Load cost metrics if available
    cost_metrics = None
    metrics_file = eval_dir / "metrics_summary.json"
    if metrics_file.exists():
        with open(metrics_file) as f:
            cost_metrics = json.load(f)

    return results_folder, subset_results, overall, cost_metrics


def load_cumulative_results(
    experiment_dir: Path,
) -> tuple[list[dict], dict, dict] | None:
    """Load cumulative analysis results for an experiment directory.

    Looks for results in:
      <experiment_dir>/evaluation_outputs/cumulative-analysis/results_avg/

    Returns:
        Tuple of (subset_results, overall_dict, overlap_data) or None if not found.
    """
    cumul_dir = experiment_dir / "evaluation_outputs" / "cumulative-analysis"
    results_folder = cumul_dir / "results_avg"

    if not results_folder.is_dir() or not any(results_folder.glob("evaluation_results_*.json")):
        return None

    # Load per-subset results
    subset_results = []
    for json_file in sorted(results_folder.glob("evaluation_results_*.json")):
        name = json_file.stem.replace("evaluation_results_", "")
        if name in ("unweighted", "weighted"):
            continue
        with open(json_file) as f:
            data = json.load(f)
        if isinstance(data, dict):
            subset_results.append(data)

    # Load overall (unweighted)
    overall = {}
    for kind in ("unweighted", "weighted"):
        overall_file = results_folder / f"evaluation_results_{kind}.json"
        if overall_file.exists():
            with open(overall_file) as f:
                overall[kind] = json.load(f)

    # Load run overlap data
    overlap_data = {}
    overlap_file = cumul_dir / "run_overlap.json"
    if overlap_file.exists():
        with open(overlap_file) as f:
            overlap_data = json.load(f)

    return subset_results, overall, overlap_data
