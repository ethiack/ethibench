"""Cumulative analysis — merge findings from all runs and re-evaluate.

Creates a ``cumulative-analysis`` folder inside the evaluation outputs directory
that treats all ``run_*`` findings as one combined run. Reuses existing raw
matchings (no LLM re-matching), then runs bipartite matching → metrics → averaging.

Directory structure created::

    {output_dir}/cumulative-analysis/
    ├── findings_parsed.jsonl   (merged from all run_* dirs)
    ├── raw_matchings/          (merged from all run_* dirs)
    ├── matchings/              (bipartite matching on merged data)
    ├── results/                (per-subset metrics)
    ├── results_avg/            (averaged + weighted/unweighted overall)
    ├── run_overlap.json        (GT-level overlap between runs)
    └── plots/                  (standard + overlap charts)
"""

import json
import os
from collections import defaultdict
from itertools import combinations
from pathlib import Path

from loguru import logger

from ethibench.datasets import DatasetCollection
from ethibench.evaluate import (
    calculate_bipartite_matchings_for_subset,
    calculate_metrics_for_subset,
)
from ethibench.results import add_overall_results, average_results_folder

CUMULATIVE_DIR_NAME = "cumulative-analysis"


def _get_run_dirs(output_dir: Path) -> list[Path]:
    """Return sorted list of run_* directories inside output_dir."""
    return sorted(
        d for d in output_dir.iterdir() if d.is_dir() and d.name.startswith("run_")
    )


def merge_findings(output_dir: Path, cumulative_dir: Path) -> Path:
    """Merge findings_parsed.jsonl from all run_* dirs into cumulative_dir.

    All findings are kept — no deduplication.

    Returns the path to the merged findings_parsed.jsonl file.
    """
    output_file = cumulative_dir / "findings_parsed.jsonl"
    cumulative_dir.mkdir(parents=True, exist_ok=True)

    run_dirs = _get_run_dirs(output_dir)
    total_lines = 0

    with open(output_file, "w") as out_f:
        for run_dir in run_dirs:
            parsed_file = run_dir / "findings_parsed.jsonl"
            if not parsed_file.exists():
                logger.warning(f"No findings_parsed.jsonl in {run_dir}, skipping.")
                continue
            with open(parsed_file) as in_f:
                for line in in_f:
                    if line.strip():
                        out_f.write(line if line.endswith("\n") else line + "\n")
                        total_lines += 1

    logger.info(f"Merged {total_lines} findings from {len(run_dirs)} runs → {output_file}")
    return output_file


def merge_raw_matchings(output_dir: Path, cumulative_dir: Path) -> None:
    """Merge raw_matchings from all run_* dirs into cumulative_dir/raw_matchings/.

    For each subset file (matchings_{subset}.json), merges each replicate index
    independently across runs into a combined list of replicate dicts. UUIDs are
    unique per run so there are no key collisions.
    """
    out_raw_dir = cumulative_dir / "raw_matchings"
    if out_raw_dir.exists():
        logger.info(f"Rebuilding cumulative raw_matchings at {out_raw_dir}.")
        for child in out_raw_dir.iterdir():
            if child.is_file() or child.is_symlink():
                child.unlink()
            elif child.is_dir():
                for root, dirs, files in os.walk(child, topdown=False):
                    root_path = Path(root)
                    for file_name in files:
                        (root_path / file_name).unlink()
                    for dir_name in dirs:
                        (root_path / dir_name).rmdir()
                child.rmdir()
    else:
        out_raw_dir.mkdir(parents=True, exist_ok=True)

    run_dirs = _get_run_dirs(output_dir)

    subset_files: dict[str, list[Path]] = defaultdict(list)
    for run_dir in run_dirs:
        rm_dir = run_dir / "raw_matchings"
        if not rm_dir.exists():
            continue
        for f in rm_dir.glob("matchings_*.json"):
            subset_name = f.stem.removeprefix("matchings_")
            subset_files[subset_name].append(f)

    for subset_name, files in subset_files.items():
        combined_replicates: list[dict] = []
        for raw_file in files:
            with open(raw_file) as f:
                data = json.load(f)
            if not isinstance(data, list) or len(data) == 0:
                logger.warning(
                    f"Unexpected raw_matchings format in {raw_file}; "
                    "expected a non-empty list of replicate dicts. Skipping."
                )
                continue
            for replicate_idx, replicate in enumerate(data):
                if not isinstance(replicate, dict):
                    logger.warning(
                        f"Unexpected replicate at index {replicate_idx} in {raw_file}; "
                        "expected a dict. Skipping."
                    )
                    continue
                while len(combined_replicates) <= replicate_idx:
                    combined_replicates.append({})
                combined_replicates[replicate_idx].update(replicate)

        if not combined_replicates:
            combined_replicates = [{}]

        output_file = out_raw_dir / f"matchings_{subset_name}.json"
        with open(output_file, "w") as f:
            json.dump(combined_replicates, f, indent=2)

        logger.info(
            f"Merged raw_matchings for '{subset_name}': "
            f"{sum(len(r) for r in combined_replicates)} findings across "
            f"{len(combined_replicates)} replicates from {len(files)} runs → {output_file}"
        )


def _jaccard(set_a: set, set_b: set) -> float:
    """Jaccard similarity between two sets."""
    if not set_a and not set_b:
        return 1.0
    union = set_a | set_b
    return len(set_a & set_b) / len(union) if union else 0.0


def _compute_overlap_for_gt_sets(
    run_names: list[str],
    gt_sets: dict[str, set[str]],
    all_gt_ids: set[str],
) -> dict:
    """Compute overlap statistics given per-run GT ID sets and the full GT ID universe.

    Args:
        run_names: Ordered list of run names.
        gt_sets: {run_name → set of matched GT IDs}.
        all_gt_ids: Complete set of GT IDs (matched and unmatched).

    Returns:
        Dict with gt_coverage, pairwise_jaccard, mean_jaccard,
        found_by_all, found_by_some, found_by_one, found_by_none,
        and frequency_distribution.
    """
    n_runs = len(run_names)

    # GT coverage: gt_id → list of run names that found it
    gt_coverage: dict[str, list[str]] = {}
    for gt_id in sorted(all_gt_ids):
        gt_coverage[gt_id] = [r for r in run_names if gt_id in gt_sets.get(r, set())]

    # Pairwise Jaccard
    pairwise: dict[str, float] = {}
    for r_a, r_b in combinations(run_names, 2):
        key = f"{r_a} vs {r_b}"
        pairwise[key] = _jaccard(gt_sets.get(r_a, set()), gt_sets.get(r_b, set()))
    mean_jaccard = sum(pairwise.values()) / len(pairwise) if pairwise else 0.0

    # Partition by how many runs found each GT
    found_by_all: list[str] = []
    found_by_some: list[str] = []
    found_by_one: list[str] = []
    found_by_none: list[str] = []
    freq: dict[int, int] = defaultdict(int)

    for gt_id in sorted(all_gt_ids):
        count = len(gt_coverage[gt_id])
        freq[count] += 1
        if count == n_runs:
            found_by_all.append(gt_id)
        elif count == 1:
            found_by_one.append(gt_id)
        elif count == 0:
            found_by_none.append(gt_id)
        else:
            found_by_some.append(gt_id)

    # Ensure frequency_distribution has entries for 0..n_runs
    frequency_distribution = {str(i): freq.get(i, 0) for i in range(n_runs + 1)}

    return {
        "gt_coverage": gt_coverage,
        "pairwise_jaccard": pairwise,
        "mean_jaccard": round(mean_jaccard, 4),
        "found_by_all": found_by_all,
        "found_by_some": found_by_some,
        "found_by_one": found_by_one,
        "found_by_none": found_by_none,
        "frequency_distribution": frequency_distribution,
    }


def compute_run_overlap(output_dir: Path, gt_dir: Path) -> dict:
    """Analyze GT-level overlap across run_* directories.

    For each run's bipartite matchings, extracts the set of GT IDs that were
    matched (TPs). Computes per-subset and global overlap statistics.

    Args:
        output_dir: Evaluation outputs directory containing run_* subdirectories.
        gt_dir: Path to the ground truth JSONL files directory.

    Returns:
        Overlap data dict with keys: runs, per_subset, overall.
    """
    run_dirs = _get_run_dirs(output_dir)
    run_names = [d.name for d in run_dirs]

    # Collect all GT IDs from GT files
    all_gt_ids_by_subset: dict[str, set[str]] = defaultdict(set)
    for gt_file in gt_dir.glob("*_gt.jsonl"):
        with open(gt_file) as f:
            for line in f:
                if not line.strip():
                    continue
                gt = json.loads(line)
                subset = gt.get("subset_name")
                gt_id = gt.get("id")
                if subset and gt_id:
                    all_gt_ids_by_subset[subset].add(gt_id)

    # Per-run, per-subset: extract matched GT IDs from bipartite matchings
    # Structure: {subset → {run_name → set of matched GT IDs}}
    subset_run_gt: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))

    for run_dir in run_dirs:
        match_dir = run_dir / "matchings"
        if not match_dir.is_dir():
            continue
        for match_file in match_dir.glob("matchings_*.json"):
            subset = match_file.stem.removeprefix("matchings_")
            with open(match_file) as f:
                matchings_list = json.load(f)
            # matchings_list is a list of replicate dicts
            for replicate in matchings_list:
                if not isinstance(replicate, dict):
                    continue
                for _uuid, mdata in replicate.items():
                    for gt_id in mdata.get("selected_gt_ids", []):
                        subset_run_gt[subset][run_dir.name].add(gt_id)

    # Compute per-subset overlap
    per_subset: dict[str, dict] = {}
    global_gt_sets: dict[str, set[str]] = defaultdict(set)
    global_all_gt: set[str] = set()

    for subset in sorted(subset_run_gt.keys()):
        gt_sets = {r: subset_run_gt[subset].get(r, set()) for r in run_names}
        all_gt = all_gt_ids_by_subset.get(subset, set())
        # Also include any GT IDs that appeared in matchings but not in files
        for s in gt_sets.values():
            all_gt |= s

        per_subset[subset] = _compute_overlap_for_gt_sets(run_names, gt_sets, all_gt)

        # Accumulate for global
        for r in run_names:
            global_gt_sets[r] |= gt_sets.get(r, set())
        global_all_gt |= all_gt

    # Global overall
    overall = _compute_overlap_for_gt_sets(run_names, global_gt_sets, global_all_gt)

    result = {
        "runs": run_names,
        "per_subset": per_subset,
        "overall": overall,
    }

    logger.info(
        f"Run overlap: {len(run_names)} runs, "
        f"mean Jaccard = {overall['mean_jaccard']:.4f}, "
        f"found by all = {len(overall['found_by_all'])}, "
        f"found by none = {len(overall['found_by_none'])}"
    )
    return result


def run_cumulative_analysis(
    output_dir: Path,
    dataset_collection: DatasetCollection,
    gt_dir: Path,
) -> None:
    """Create a cumulative-analysis folder treating all run_* findings as one combined run.

    Reuses existing raw_matchings (no LLM re-matching), then runs bipartite
    matching → metrics → averaging.

    Args:
        output_dir: Evaluation outputs directory containing run_* subdirectories.
        dataset_collection: Loaded DatasetCollection.
        gt_dir: Path to the ground truth JSONL files directory.
    """
    if not output_dir.exists() or not output_dir.is_dir():
        logger.warning(f"{output_dir} does not exist, skipping cumulative analysis.")
        return

    run_dirs = _get_run_dirs(output_dir)
    if not run_dirs:
        logger.warning(
            f"No run_* directories found in {output_dir}, skipping cumulative analysis."
        )
        return

    cumulative_dir = output_dir / CUMULATIVE_DIR_NAME
    cumulative_dir.mkdir(parents=True, exist_ok=True)
    logger.info(f"Running cumulative analysis for {len(run_dirs)} runs in {output_dir}")

    # Step A: Merge findings from all runs
    merge_findings(output_dir, cumulative_dir)

    # Step B: Merge raw matchings from all runs
    merge_raw_matchings(output_dir, cumulative_dir)

    findings_parsed = cumulative_dir / "findings_parsed.jsonl"
    raw_matchings_dir = cumulative_dir / "raw_matchings"
    matchings_dir = cumulative_dir / "matchings"
    results_dir = cumulative_dir / "results"
    matchings_dir.mkdir(parents=True, exist_ok=True)
    results_dir.mkdir(parents=True, exist_ok=True)

    for dataset in dataset_collection.datasets:
        subset = dataset.subset
        raw_file = raw_matchings_dir / f"matchings_{subset}.json"
        match_file = matchings_dir / f"matchings_{subset}.json"
        results_file = results_dir / f"evaluation_results_{subset}.json"

        if not raw_file.exists():
            logger.warning(f"No merged raw_matchings for subset '{subset}', skipping.")
            continue

        with open(raw_file) as f:
            raw_matchings_list = json.load(f)

        # Resolve GT dir for this subset
        subset_gt_dir = gt_dir
        if dataset.gt_file:
            gt_path = Path(dataset.gt_file)
            if not gt_path.is_absolute():
                gt_path = gt_dir / dataset.gt_file
            if gt_path.is_file():
                subset_gt_dir = gt_path.parent

        # Step C: Bipartite matchings (always rebuild for cumulative)
        logger.info(f"CUMULATIVE STEP 2: Bipartite matching for {subset}")
        matchings_list = []
        for raw_m in raw_matchings_list:
            bipartite_m = calculate_bipartite_matchings_for_subset(
                findings_parsed, subset_gt_dir, subset, raw_m, dataset_collection
            )
            matchings_list.append(bipartite_m)
        with open(match_file, "w") as f:
            json.dump(matchings_list, f, indent=2)

        # Step D: Metrics
        logger.info(f"CUMULATIVE STEP 3: Metrics for {subset}")
        results_list = []
        for raw_m, final_m in zip(raw_matchings_list, matchings_list):
            res = calculate_metrics_for_subset(
                final_m, raw_m, subset_gt_dir, subset, dataset_collection
            )
            results_list.append(res)
        with open(results_file, "w") as f:
            json.dump(results_list, f, indent=2)

    # Step E: Average results and compute overall scores
    results_avg_dir = cumulative_dir / "results_avg"
    if results_dir.exists() and any(results_dir.glob("*.json")):
        average_results_folder(results_dir, results_avg_dir)
        weights = dataset_collection.extract_weights_dict()
        add_overall_results(results_avg_dir, weights)

    # Step F: Run overlap analysis
    overlap_data = compute_run_overlap(output_dir, gt_dir)
    overlap_file = cumulative_dir / "run_overlap.json"
    with open(overlap_file, "w") as f:
        json.dump(overlap_data, f, indent=2)
    logger.info(f"Saved run overlap analysis → {overlap_file}")

    # Step G: Generate plots (standard + overlap)
    from ethibench.plots import generate_cumulative_plots

    plots_dir = cumulative_dir / "plots"
    generate_cumulative_plots(results_avg_dir, plots_dir, overlap_data)

    logger.info(f"Cumulative analysis complete: {cumulative_dir}")
