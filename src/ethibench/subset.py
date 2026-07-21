"""Subset selection — find the target subset that best correlates with the full benchmark."""

import itertools
import json
from pathlib import Path

import numpy as np
from loguru import logger
from scipy.stats import spearmanr

from ethibench.datasets import DatasetCollection


def _f1_from_counts(tp: float, fp: float, fn: float) -> float:
    denom = 2 * tp + fp + fn
    return 0.0 if denom == 0 else 2 * tp / denom


def load_experiment_data(
    experiment_dir: Path,
    dc: DatasetCollection,
) -> tuple[dict[str, dict], dict[str, float]] | None:
    """Load per-target evaluation results and costs for a single experiment.

    Returns:
        Tuple of (target_results, target_costs) or None if data is unavailable.
        - target_results: ``{target_id: {"tp": ..., "fp": ..., "fn": ...}}``
        - target_costs: ``{target_id: total_cost}``
    """
    eval_dir = experiment_dir / "evaluation_outputs"

    # Find results folder (multi-run first, then single-run)
    results_folder = None
    for candidate in ("results_avg_all", "results_avg"):
        path = eval_dir / candidate
        if path.is_dir() and any(path.glob("evaluation_results_*.json")):
            results_folder = path
            break

    if results_folder is None:
        logger.warning(f"No evaluation results found in {eval_dir}")
        return None

    # Load per-subset results and map back to target_ids
    target_results: dict[str, dict] = {}
    for json_file in results_folder.glob("evaluation_results_*.json"):
        name = json_file.stem.replace("evaluation_results_", "")
        if name in ("unweighted", "weighted"):
            continue
        with open(json_file) as f:
            data = json.load(f)
        if not isinstance(data, dict):
            continue
        subset_name = data.get("subset_name", name)
        # Map subset_name back to target_ids
        target_ids = dc.get_target_ids_for_subset(subset_name)
        if len(target_ids) == 1:
            tid = next(iter(target_ids))
            target_results[tid] = {
                "tp": data["true_positives"],
                "fp": data["false_positives"],
                "fn": data["false_negatives"],
            }
        else:
            # Multiple targets per subset — attribute equally (best effort)
            for tid in target_ids:
                n = len(target_ids)
                target_results[tid] = {
                    "tp": data["true_positives"] / n,
                    "fp": data["false_positives"] / n,
                    "fn": data["false_negatives"] / n,
                }

    # Load cost from metrics_summary.json
    target_costs: dict[str, float] = {}
    metrics_file = eval_dir / "metrics_summary.json"
    if metrics_file.exists():
        with open(metrics_file) as f:
            metrics = json.load(f)
        per_target = metrics.get("per_target", {})
        for tid in target_results:
            if tid in per_target:
                target_costs[tid] = per_target[tid].get("total_cost", 0.0)

    return target_results, target_costs


def load_all_experiments(
    experiment_dirs: list[Path],
    dc: DatasetCollection,
) -> tuple[dict[str, list[dict]], dict[str, float], list[str]]:
    """Load data from all experiments.

    Returns:
        - per_target_data: ``{target_id: [{"tp", "fp", "fn"}, ...]}`` one entry per experiment
        - avg_costs: ``{target_id: average_cost}`` averaged across experiments
        - experiment_labels: list of experiment names that were successfully loaded
    """
    per_target_data: dict[str, list[dict]] = {}
    cost_accum: dict[str, list[float]] = {}
    experiment_labels: list[str] = []
    missing_cost_experiments: list[str] = []

    for exp_dir in experiment_dirs:
        result = load_experiment_data(exp_dir, dc)
        if result is None:
            continue

        target_results, target_costs = result
        if not target_results:
            continue

        experiment_labels.append(exp_dir.name)

        for tid, counts in target_results.items():
            per_target_data.setdefault(tid, []).append(counts)

        if target_costs:
            for tid, cost in target_costs.items():
                cost_accum.setdefault(tid, []).append(cost)
        else:
            missing_cost_experiments.append(exp_dir.name)

    if missing_cost_experiments:
        logger.warning(
            f"No cost data (metrics_summary.json with per_target costs) for: "
            f"{', '.join(missing_cost_experiments)}. "
            f"Cost ratio filtering will use data from the remaining experiments only."
        )

    # Average costs across experiments
    avg_costs = {tid: np.mean(costs) for tid, costs in cost_accum.items()}

    return per_target_data, avg_costs, experiment_labels


def _compute_f1_vector(
    per_target_data: dict[str, list[dict]],
    subset: tuple[str, ...],
    n_experiments: int,
) -> np.ndarray:
    """Compute F1 for a subset of targets, one value per experiment."""
    f1s = []
    for i in range(n_experiments):
        tp = sum(per_target_data[t][i]["tp"] for t in subset)
        fp = sum(per_target_data[t][i]["fp"] for t in subset)
        fn = sum(per_target_data[t][i]["fn"] for t in subset)
        f1s.append(_f1_from_counts(tp, fp, fn))
    return np.array(f1s)


def _pearson(x: np.ndarray, y: np.ndarray) -> float:
    if np.std(x) == 0 or np.std(y) == 0:
        return 0.0
    return float(np.corrcoef(x, y)[0, 1])


def _spearman(x: np.ndarray, y: np.ndarray) -> float:
    if np.std(x) == 0 or np.std(y) == 0:
        return 0.0
    result = spearmanr(x, y)
    return float(result.correlation)


def find_best_subset(
    per_target_data: dict[str, list[dict]],
    avg_costs: dict[str, float],
    max_ratio: float,
    metric: str = "pearson",
) -> dict | None:
    """Find the target subset with highest correlation to the full benchmark F1.

    Args:
        per_target_data: ``{target_id: [{"tp", "fp", "fn"}, ...]}``
        avg_costs: ``{target_id: average_cost}``
        max_ratio: Maximum allowed cost ratio (0–1).
        metric: ``"pearson"`` or ``"spearman"``.

    Returns:
        Dict with ``subset``, ``correlation``, ``cost_ratio``, ``subset_cost``,
        ``full_cost``, ``metric`` — or ``None`` if no valid subset is found.
    """
    targets = sorted(per_target_data.keys())
    n_experiments = len(next(iter(per_target_data.values())))

    corr_fn = _pearson if metric == "pearson" else _spearman

    full_f1 = _compute_f1_vector(per_target_data, tuple(targets), n_experiments)
    full_cost = sum(avg_costs.get(t, 0.0) for t in targets)

    if full_cost <= 0:
        logger.warning("Total cost is zero — cost ratio filtering is disabled.")
        max_allowed_cost = float("inf")
    else:
        max_allowed_cost = max_ratio * full_cost

    n_targets = len(targets)
    if n_targets > 15:
        total_combos = 2**n_targets - 1
        logger.warning(
            f"{n_targets} targets → {total_combos} subsets to evaluate. "
            f"This may take a while."
        )

    best: dict | None = None

    for k in range(1, n_targets + 1):
        for subset in itertools.combinations(targets, k):
            subset_cost = sum(avg_costs.get(t, 0.0) for t in subset)
            if subset_cost > max_allowed_cost:
                continue

            subset_f1 = _compute_f1_vector(per_target_data, subset, n_experiments)
            corr = corr_fn(full_f1, subset_f1)

            if best is None or corr > best["correlation"]:
                best = {
                    "subset": list(subset),
                    "correlation": corr,
                    "cost_ratio": subset_cost / full_cost if full_cost > 0 else 0.0,
                    "subset_cost": subset_cost,
                    "full_cost": full_cost,
                    "metric": metric,
                }

    return best
