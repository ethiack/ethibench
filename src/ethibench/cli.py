"""CLI entry points for ethibench."""

import asyncio
import json
import sys
from importlib.metadata import PackageNotFoundError, version as _pkg_version
from pathlib import Path

import click
from loguru import logger
from rich.console import Console

from ethibench.datasets import DatasetCollection


# Directory names that are never experiments (infrastructure/output dirs).
_NON_EXPERIMENT_DIRS = {"aggregated_analysis", "compare_all"}

_BANNER = r"""        __  __    _ __                    __
  ___  / /_/ /_  (_) /_  ___  ____  _____/ /_
 / _ \/ __/ __ \/ / __ \/ _ \/ __ \/ ___/ __ \
/  __/ /_/ / / / / /_/ /  __/ / / / /__/ / / /
\___/\__/_/ /_/_/_.___/\___/_/ /_/\___/_/ /_/"""

_BANNER_WIDTH = 46


def _print_banner() -> None:
    """Print the EthiBench banner to stderr, only when stderr is a TTY."""
    if not sys.stderr.isatty():
        return
    try:
        v = _pkg_version("ethibench")
    except PackageNotFoundError:
        v = "dev"
    console = Console(file=sys.stderr, highlight=False, soft_wrap=True)
    console.print()
    console.print(_BANNER, style="bold #5EFF88")
    console.print()
    console.print(f"{'ethiack.com'.center(_BANNER_WIDTH)}", style="dim")
    console.print(f"{f'v{v}'.center(_BANNER_WIDTH)}\n", style="dim")


def _discover_experiment_dirs(parent_dir: Path) -> list[Path]:
    """Discover experiment directories inside a parent folder.

    A directory qualifies if it contains an ``evaluation_outputs/`` subfolder
    and is not a known infrastructure directory.
    Results are sorted alphabetically by directory name.
    """
    found = sorted(
        [
            d
            for d in parent_dir.iterdir()
            if d.is_dir()
            and d.name not in _NON_EXPERIMENT_DIRS
            and (d / "evaluation_outputs").is_dir()
        ],
        key=lambda p: p.name,
    )
    return found


def _detect_run_dirs(experiment_dir: Path) -> list[Path]:
    """Detect run directories inside an experiment directory.

    If subdirectories starting with 'run' exist, treat each as a separate run.
    Otherwise assume the experiment_dir itself is a single run.
    """
    candidates = sorted(
        [d for d in experiment_dir.iterdir() if d.is_dir() and d.name.startswith("run")],
        key=lambda p: p.name,
    )
    if candidates:
        return candidates
    return [experiment_dir]


@click.group(invoke_without_command=True)
@click.pass_context
def cli(ctx: click.Context) -> None:
    """EthiBench — an evaluation framework for AI pentesting agents."""
    _print_banner()
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


def _run_single_evaluate(
    experiment_dir: Path,
    dc: "DatasetCollection",
    gt_dir: Path,
    output_dir: Path | None,
    replicates: int,
    force: bool = False,
) -> None:
    """Run the full evaluation pipeline on a single experiment directory."""
    from ethibench.config import get_max_parallel_runs
    from ethibench.cumulative_analysis import run_cumulative_analysis
    from ethibench.evaluate import run_evaluation
    from ethibench.metrics import aggregate_run_metrics, save_metrics_summary
    from ethibench.plots import generate_plots
    from ethibench.report import generate_summary
    from ethibench.results import average_all_results

    if output_dir is None:
        output_dir = experiment_dir / "evaluation_outputs"

    run_dirs = _detect_run_dirs(experiment_dir)
    logger.info(f"Found {len(run_dirs)} run(s) in {experiment_dir}")

    known_targets = dc.get_all_target_ids()
    for rd in run_dirs:
        target_dirs = [d for d in rd.iterdir() if d.is_dir() and d.name in known_targets]
        if not target_dirs:
            logger.error(
                f"No target directories found in {rd}. "
                f"Expected subdirectories named: {sorted(known_targets)}"
            )
            sys.exit(1)

    async def _evaluate_all_runs() -> None:
        sem = asyncio.Semaphore(get_max_parallel_runs())

        async def _eval_one(rd: Path, run_output: Path) -> None:
            async with sem:
                logger.info(f"Evaluating {rd.name}…")
                await run_evaluation(
                    rd, dc, gt_dir, run_output, n_replicates=replicates, force=force
                )

        tasks = []
        for rd in run_dirs:
            run_output = output_dir if len(run_dirs) == 1 else output_dir / rd.name
            tasks.append(_eval_one(rd, run_output))
        await asyncio.gather(*tasks)

    asyncio.run(_evaluate_all_runs())

    weights = dc.extract_weights_dict()
    eval_run_dirs = (
        [output_dir]
        if len(run_dirs) == 1
        else [output_dir / rd.name for rd in run_dirs if (output_dir / rd.name).is_dir()]
    )

    average_all_results(output_dir, eval_run_dirs, weights)

    if len(run_dirs) > 1:
        logger.info("Running cumulative analysis...")
        run_cumulative_analysis(output_dir, dc, gt_dir)
        logger.success("Cumulative analysis complete.")

    results_folder = (
        output_dir / "results_avg_all" if len(run_dirs) > 1 else output_dir / "results_avg"
    )
    if not results_folder.is_dir():
        results_folder = output_dir / "results_avg"
    if not results_folder.is_dir():
        results_folder = eval_run_dirs[0] / "results" if eval_run_dirs else output_dir / "results"

    cost_metrics = None
    overall_eval = None
    unw_file = results_folder / "evaluation_results_unweighted.json"
    if unw_file.exists():
        with open(unw_file) as f:
            overall_eval = json.load(f)
    cost_metrics = aggregate_run_metrics(run_dirs, evaluation_results=overall_eval)
    if cost_metrics:
        save_metrics_summary(cost_metrics, output_dir / "metrics_summary.json")

    plots_dir = output_dir / "plots"
    generate_plots(results_folder, plots_dir, cost_metrics=cost_metrics)

    generate_summary(
        results_folder, plots_dir, output_dir / "summary.md", cost_metrics=cost_metrics
    )

    logger.info(f"Evaluation complete. Results in {output_dir}")


@cli.command()
@click.argument(
    "experiment_dir",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    required=False,
    default=None,
)
@click.option(
    "--dataset",
    "-d",
    required=True,
    type=click.Path(exists=True, path_type=Path),
    help="Dataset YAML file.",
)
@click.option(
    "--gt-dir",
    "-g",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=None,
    help="Ground truth directory. Defaults to gt/ next to dataset YAML.",
)
@click.option(
    "--output-dir",
    "-o",
    type=click.Path(path_type=Path),
    default=None,
    help="Output directory. Defaults to evaluation_outputs/ inside experiment dir. "
    "Ignored when --parent-dir is used (each experiment gets its own evaluation_outputs/).",
)
@click.option("--replicates", "-n", type=int, default=1, help="Number of LLM matching replicates.")
@click.option("--force", "-f", is_flag=True, default=False, help="Re-run all steps, ignoring cached artifacts.")
@click.option(
    "--parent-dir",
    "-p",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=None,
    help="Parent folder containing multiple experiment directories to evaluate in batch. "
    "All immediate subdirectories are treated as experiments.",
)
def evaluate(
    experiment_dir: Path | None,
    dataset: Path,
    gt_dir: Path | None,
    output_dir: Path | None,
    replicates: int,
    force: bool,
    parent_dir: Path | None,
):
    """Run the full evaluation pipeline on EXPERIMENT_DIR.

    EXPERIMENT_DIR should contain run_* subdirectories (or be a single run),
    each with target subdirectories named after target_ids from the dataset
    YAML.  Each target directory must contain a findings.jsonl file.

    Use --parent-dir to evaluate all experiment subdirectories inside a folder
    in one go (e.g. ethibench evaluate --parent-dir final_experiments/ -d dataset.yaml).
    """
    # Load dataset
    dc = DatasetCollection()
    dc.init_from_yaml(dataset)

    # Resolve GT dir
    if gt_dir is None:
        gt_dir = dataset.parent / "gt"
        if not gt_dir.is_dir():
            logger.error(f"No gt/ directory found next to {dataset}. Pass --gt-dir explicitly.")
            sys.exit(1)

    # Build list of experiment dirs to evaluate
    dirs_to_evaluate: list[Path] = []

    if parent_dir is not None:
        discovered = sorted(
            [
                d
                for d in parent_dir.iterdir()
                if d.is_dir() and d.name not in _NON_EXPERIMENT_DIRS
            ],
            key=lambda p: p.name,
        )
        if not discovered:
            logger.error(f"No subdirectories found in {parent_dir}.")
            sys.exit(1)
        dirs_to_evaluate.extend(discovered)

    if experiment_dir is not None:
        dirs_to_evaluate.append(experiment_dir)

    if not dirs_to_evaluate:
        logger.error("Provide EXPERIMENT_DIR or --parent-dir (or both).")
        sys.exit(1)

    if len(dirs_to_evaluate) == 1:
        _run_single_evaluate(dirs_to_evaluate[0], dc, gt_dir, output_dir, replicates, force=force)
    else:
        if output_dir is not None:
            logger.warning(
                "--output-dir is ignored in batch mode; "
                "each experiment writes to its own evaluation_outputs/."
            )
        for exp_dir in dirs_to_evaluate:
            logger.info(f"=== Evaluating experiment: {exp_dir.name} ===")
            _run_single_evaluate(exp_dir, dc, gt_dir, None, replicates, force=force)


@cli.command("convert-report")
@click.argument("report_path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option(
    "--output",
    "-o",
    type=click.Path(path_type=Path),
    default=None,
    help="Output findings.jsonl path.",
)
def convert_report(report_path: Path, output: Path | None):
    """Convert a Markdown report to findings.jsonl."""
    from ethibench.convert_report import convert_report_to_findings

    out = convert_report_to_findings(report_path, output)
    click.echo(f"Findings written to {out}")


def _write_aggregated_analysis(
    parent_dir: Path,
    all_dups: dict[str, dict],
    all_unmatched: dict[str, dict],
    all_stats: dict[str, dict],
) -> None:
    """Write aggregated analysis files across all experiments to the parent directory."""
    agg_dir = parent_dir / "aggregated_analysis"
    agg_dir.mkdir(parents=True, exist_ok=True)

    # --- Aggregated duplicates: JSONL with full finding objects ---
    dup_count = 0
    with open(agg_dir / "all_duplicates.jsonl", "w") as f:
        for label, dups_by_subset in sorted(all_dups.items()):
            for subset, data in sorted(dups_by_subset.items()):
                for finding in data.get("findings", []):
                    entry = dict(finding)
                    entry["experiment"] = label
                    f.write(json.dumps(entry) + "\n")
                    dup_count += 1
    logger.info(f"Aggregated duplicates: {dup_count} total across all experiments")

    # --- Aggregated false positives: JSONL with full finding objects ---
    fp_count = 0
    with open(agg_dir / "all_false_positives.jsonl", "w") as f:
        for label, unmatched_by_subset in sorted(all_unmatched.items()):
            for subset, data in sorted(unmatched_by_subset.items()):
                for finding in data.get("findings", []):
                    entry = dict(finding)
                    entry["experiment"] = label
                    f.write(json.dumps(entry) + "\n")
                    fp_count += 1
    logger.info(f"Aggregated false positives: {fp_count} total across all experiments")

    # --- Average GT statistics across all experiments ---
    # Collect per-subset stats from each experiment and average them
    subset_stats_agg: dict[str, list[dict]] = {}
    for label, stats in all_stats.items():
        per_subset = stats.get("per_subset", {})
        for subset, sdata in per_subset.items():
            subset_stats_agg.setdefault(subset, []).append(sdata)

    avg_per_subset: dict[str, dict] = {}
    for subset, stats_list in sorted(subset_stats_agg.items()):
        n = len(stats_list)
        avg_per_subset[subset] = {
            "total_gt": stats_list[0].get("total_gt", 0),
            "num_experiments": n,
            "matched_gt_avg": round(sum(s.get("matched_gt", 0) for s in stats_list) / n, 2),
            "unmatched_gt_avg": round(sum(s.get("unmatched_gt", 0) for s in stats_list) / n, 2),
            "findings_per_gt_avg": round(
                sum(s.get("findings_per_gt_avg", 0) for s in stats_list) / n, 2
            ),
            "matched_gt_min": min(s.get("matched_gt", 0) for s in stats_list),
            "matched_gt_max": max(s.get("matched_gt", 0) for s in stats_list),
        }

    # Per-experiment summary
    per_experiment: dict[str, dict] = {}
    for label, stats in all_stats.items():
        per_subset = stats.get("per_subset", {})
        total_matched = sum(s.get("matched_gt", 0) for s in per_subset.values())
        total_gt = sum(s.get("total_gt", 0) for s in per_subset.values())
        per_experiment[label] = {
            "total_gt": total_gt,
            "total_matched": total_matched,
            "total_unmatched": total_gt - total_matched,
            "coverage_pct": round(100 * total_matched / total_gt, 1) if total_gt else 0,
        }

    total_gt = max((s.get("total_gt", 0) for s in all_stats.values()), default=0)
    with open(agg_dir / "gt_statistics_avg.json", "w") as f:
        json.dump(
            {
                "total_gt": total_gt,
                "num_experiments": len(all_stats),
                "per_subset_avg": avg_per_subset,
                "per_experiment": per_experiment,
            },
            f,
            indent=2,
        )
    logger.info(f"Aggregated GT statistics written to {agg_dir}")
    logger.info(f"Aggregated analysis complete. Results in {agg_dir}")


def _run_single_analyze(
    experiment_dir: Path,
    dc: "DatasetCollection",
    gt_dir: Path,
    output_dir: Path | None,
) -> tuple[dict, dict, dict]:
    """Run analysis on a single experiment. Returns (duplicates, unmatched, statistics)."""
    from ethibench.analysis.duplicates import extract_duplicates
    from ethibench.analysis.statistics import compute_statistics
    from ethibench.analysis.unmatched import extract_unmatched

    if output_dir is None:
        output_dir = experiment_dir / "evaluation_outputs"

    analysis_dir = output_dir / "analysis"
    analysis_dir.mkdir(parents=True, exist_ok=True)

    # Detect run subdirs inside evaluation_outputs — matchings live there
    run_output_dirs = sorted(
        [d for d in output_dir.iterdir() if d.is_dir() and d.name.startswith("run")],
        key=lambda p: p.name,
    )

    # If no run_* subdirs, the output_dir itself holds the matchings
    if not run_output_dirs:
        run_output_dirs = [output_dir]

    # Merge results across all run output dirs
    merged_dups: dict[str, dict] = {}
    merged_unmatched: dict[str, dict] = {}
    merged_stats: dict = {}

    for rod in run_output_dirs:
        # Find findings_parsed.jsonl for this run
        findings_file = None
        for parsed in rod.rglob("findings_parsed.jsonl"):
            findings_file = parsed
            break

        # Duplicates
        dups = extract_duplicates(rod, findings_file)
        for subset, data in dups.items():
            if subset not in merged_dups:
                merged_dups[subset] = {"count": 0, "uuids": [], "findings": []}
            merged_dups[subset]["count"] += data.get("count", 0)
            merged_dups[subset]["uuids"].extend(data.get("uuids", []))
            merged_dups[subset]["findings"].extend(data.get("findings", []))

        # Unmatched
        unmatched = extract_unmatched(rod, findings_file)
        for subset, data in unmatched.items():
            if subset not in merged_unmatched:
                merged_unmatched[subset] = {"uuids": [], "findings": []}
            merged_unmatched[subset]["uuids"].extend(data.get("uuids", []))
            merged_unmatched[subset]["findings"].extend(data.get("findings", []))

        # Statistics — use cumulative-analysis if available, otherwise last run
        stats = compute_statistics(rod, gt_dir)
        if stats:
            merged_stats = stats

    # Deduplicate UUIDs
    for subset in merged_dups:
        merged_dups[subset]["uuids"] = list(set(merged_dups[subset]["uuids"]))
    for subset in merged_unmatched:
        merged_unmatched[subset]["uuids"] = list(set(merged_unmatched[subset]["uuids"]))

    # Write per-experiment analysis
    logger.info("Writing analysis results…")
    with open(analysis_dir / "duplicates.json", "w") as f:
        serializable = {
            k: {"count": v["count"], "uuids": v["uuids"]} for k, v in merged_dups.items()
        }
        json.dump(serializable, f, indent=2)

    with open(analysis_dir / "unmatched.json", "w") as f:
        serializable = {
            k: {"count": len(v["uuids"]), "uuids": v["uuids"]}
            for k, v in merged_unmatched.items()
        }
        json.dump(serializable, f, indent=2)

    with open(analysis_dir / "statistics.json", "w") as f:
        stats_out = {k: v for k, v in merged_stats.items() if k != "unmatched_gts"}
        stats_out["unmatched_gt_ids"] = [
            gt["id"] for gt in merged_stats.get("unmatched_gts", [])
        ]
        json.dump(stats_out, f, indent=2)

    logger.info(f"Analysis complete. Results in {analysis_dir}")
    return merged_dups, merged_unmatched, merged_stats


@cli.command()
@click.argument(
    "experiment_dir",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    required=False,
    default=None,
)
@click.option(
    "--dataset",
    "-d",
    required=True,
    type=click.Path(exists=True, path_type=Path),
    help="Dataset YAML file.",
)
@click.option(
    "--gt-dir",
    "-g",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=None,
    help="Ground truth directory.",
)
@click.option(
    "--output-dir",
    "-o",
    type=click.Path(path_type=Path),
    default=None,
    help="Evaluation outputs directory.",
)
@click.option(
    "--parent-dir",
    "-p",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=None,
    help="Parent folder containing multiple experiment directories to analyze in batch. "
    "Produces per-experiment analysis plus aggregated results in the parent directory.",
)
def analyze(
    experiment_dir: Path | None,
    dataset: Path,
    gt_dir: Path | None,
    output_dir: Path | None,
    parent_dir: Path | None,
):
    """Run analysis tools (duplicates, unmatched, statistics) on existing evaluation outputs.

    Use --parent-dir to analyze all experiments in a folder and produce aggregated
    duplicates, false positives, and GT statistics across all experiments.
    """
    dc = DatasetCollection()
    dc.init_from_yaml(dataset)

    if gt_dir is None:
        gt_dir = dataset.parent / "gt"

    # Build list of experiment dirs
    dirs_to_analyze: list[Path] = []

    if parent_dir is not None:
        # Only include subdirs that have evaluation_outputs/ (i.e. actual experiments)
        discovered = sorted(
            [
                d
                for d in parent_dir.iterdir()
                if d.is_dir()
                and d.name not in _NON_EXPERIMENT_DIRS
                and (d / "evaluation_outputs").is_dir()
            ],
            key=lambda p: p.name,
        )
        if not discovered:
            logger.error(
                f"No experiment directories found in {parent_dir}. "
                "Subdirectories must contain an evaluation_outputs/ folder."
            )
            sys.exit(1)
        dirs_to_analyze.extend(discovered)

    if experiment_dir is not None:
        dirs_to_analyze.append(experiment_dir)

    if not dirs_to_analyze:
        logger.error("Provide EXPERIMENT_DIR or --parent-dir (or both).")
        sys.exit(1)

    # Run analysis on each experiment, collecting results
    all_dups: dict[str, dict] = {}
    all_unmatched: dict[str, dict] = {}
    all_stats: dict[str, dict] = {}

    for exp_dir in dirs_to_analyze:
        label = exp_dir.name
        exp_output = output_dir if (len(dirs_to_analyze) == 1 and output_dir) else None
        logger.info(f"=== Analyzing experiment: {label} ===")
        dups, unmatched, stats = _run_single_analyze(exp_dir, dc, gt_dir, exp_output)
        all_dups[label] = dups
        all_unmatched[label] = unmatched
        all_stats[label] = stats

    # Aggregated analysis across all experiments (only with --parent-dir)
    if parent_dir is not None and len(dirs_to_analyze) > 1:
        _write_aggregated_analysis(parent_dir, all_dups, all_unmatched, all_stats)


@cli.command()
@click.argument(
    "experiment_dirs", nargs=-1, type=click.Path(exists=True, file_okay=False, path_type=Path)
)
@click.option(
    "--output-dir",
    "-o",
    required=True,
    type=click.Path(path_type=Path),
    help="Output directory for comparison results.",
)
@click.option(
    "--parent-dir",
    "-p",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=None,
    help="Parent folder to auto-discover experiments from (subdirs with evaluation_outputs/).",
)
def compare(experiment_dirs: tuple[Path, ...], output_dir: Path, parent_dir: Path | None):
    """Compare evaluation results across multiple experiments.

    Accepts explicit EXPERIMENT_DIRS, a --parent-dir whose subdirectories are
    auto-discovered, or both.  Each experiment must already have evaluation
    outputs (run ``ethibench evaluate`` first).  Labels are always the
    directory names.
    """
    from ethibench.plots import generate_comparison_plots, generate_cumulative_comparison_plots
    from ethibench.report import generate_comparison_summary
    from ethibench.results import load_cumulative_results, load_experiment_results

    # Build the full list of experiment dirs
    all_dirs: list[Path] = list(experiment_dirs)

    if parent_dir is not None:
        discovered = _discover_experiment_dirs(parent_dir)
        if not discovered:
            logger.error(
                f"No experiments found in {parent_dir}. "
                "Subdirectories must contain an evaluation_outputs/ folder."
            )
            sys.exit(1)
        # Merge: explicit dirs first, then discovered (deduplicated by resolved path)
        seen = {d.resolve() for d in all_dirs}
        for d in discovered:
            if d.resolve() not in seen:
                all_dirs.append(d)
                seen.add(d.resolve())

    if len(all_dirs) < 2:
        logger.error("At least two experiment directories are required for comparison.")
        sys.exit(1)

    exp_labels = [d.name for d in all_dirs]

    # Load results for each experiment; validate all have been evaluated
    all_results: dict[str, list[dict]] = {}
    all_overall: dict[str, dict] = {}
    all_cost: dict[str, dict] = {}
    missing = []

    for exp_dir, label in zip(all_dirs, exp_labels):
        loaded = load_experiment_results(exp_dir)
        if loaded is None:
            missing.append(str(exp_dir))
            continue
        _results_folder, subset_results, overall, cost_metrics = loaded
        all_results[label] = subset_results
        if "unweighted" in overall:
            all_overall[label] = overall["unweighted"]
        if cost_metrics:
            all_cost[label] = cost_metrics

    if missing:
        logger.error(
            "The following experiments have not been evaluated yet. "
            "Run `ethibench evaluate` on them first:\n" + "\n".join(f"  - {m}" for m in missing)
        )
        sys.exit(1)

    # Generate outputs
    output_dir.mkdir(parents=True, exist_ok=True)

    # Save comparison data as JSON
    comparison_data = {
        "experiments": exp_labels,
        "results": {label: results for label, results in all_results.items()},
        "overall": all_overall,
        "cost": all_cost if all_cost else None,
    }
    with open(output_dir / "comparison.json", "w") as f:
        json.dump(comparison_data, f, indent=2)

    # Generate plots
    plots_dir = output_dir / "plots"
    generate_comparison_plots(
        all_results, all_overall, plots_dir, all_cost=all_cost if all_cost else None
    )

    # Generate summary
    generate_comparison_summary(
        all_results,
        all_overall,
        plots_dir,
        output_dir / "comparison.md",
        all_cost=all_cost if all_cost else None,
    )

    # --- Cumulative comparison (if cumulative data exists) ---
    all_cumul_results: dict[str, list[dict]] = {}
    all_cumul_overall: dict[str, dict] = {}
    all_overlap: dict[str, dict] = {}

    for exp_dir, label in zip(all_dirs, exp_labels):
        loaded = load_cumulative_results(exp_dir)
        if loaded is None:
            logger.warning(f"No cumulative analysis found for {label}, skipping.")
            continue
        subset_results, overall, overlap_data = loaded
        all_cumul_results[label] = subset_results
        if "unweighted" in overall:
            all_cumul_overall[label] = overall["unweighted"]
        if overlap_data:
            all_overlap[label] = overlap_data

    if len(all_cumul_overall) >= 2:
        cumul_dir = output_dir / "cumulative-analysis"
        cumul_dir.mkdir(parents=True, exist_ok=True)

        # Compute delta analysis
        delta_analysis = {}
        for exp in all_cumul_overall:
            avg_f1 = all_overall.get(exp, {}).get("f1_score", 0)
            cum_f1 = all_cumul_overall[exp].get("f1_score", 0)
            delta_analysis[exp] = {
                "avg_f1": avg_f1,
                "cumulative_f1": cum_f1,
                "delta": abs(avg_f1 - cum_f1),
            }

        min_exp = min(delta_analysis, key=lambda e: delta_analysis[e]["delta"])
        max_exp = max(delta_analysis, key=lambda e: delta_analysis[e]["delta"])

        cumul_comparison_data = {
            "experiments": list(all_cumul_overall.keys()),
            "cumulative_overall": all_cumul_overall,
            "cumulative_results": all_cumul_results,
            "delta_analysis": {
                "per_experiment": delta_analysis,
                "min_delta": {"experiment": min_exp, **delta_analysis[min_exp]},
                "max_delta": {"experiment": max_exp, **delta_analysis[max_exp]},
            },
        }
        with open(cumul_dir / "comparison.json", "w") as f:
            json.dump(cumul_comparison_data, f, indent=2)

        # Generate cumulative comparison plots
        cumul_plots_dir = cumul_dir / "plots"
        generate_cumulative_comparison_plots(
            all_cumul_results,
            all_cumul_overall,
            all_overlap,
            all_overall,
            cumul_plots_dir,
            all_avg_results=all_results,
            all_cost=all_cost if all_cost else None,
        )
        logger.info(f"Cumulative comparison complete. Results in {cumul_dir}")
    elif all_cumul_overall:
        logger.warning(
            "Only 1 experiment has cumulative data — need at least 2 for comparison."
        )

    # --- Pairwise A/B statistical comparison (top 4 by F1) ---
    from ethibench.pairwise import generate_pairwise_comparison, render_latex_table, render_markdown_table

    pairwise_data = generate_pairwise_comparison(all_dirs, exp_labels, all_overall)
    if pairwise_data is not None:
        md_table = render_markdown_table(pairwise_data)
        with open(output_dir / "pairwise_comparison.md", "w") as f:
            f.write(md_table)

        latex_table = render_latex_table(pairwise_data)
        with open(output_dir / "pairwise_comparison.tex", "w") as f:
            f.write(latex_table)

        logger.info(f"Pairwise comparison written to {output_dir / 'pairwise_comparison.md'}")

    logger.info(f"Comparison complete. Results in {output_dir}")
