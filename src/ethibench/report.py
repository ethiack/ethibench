"""Generate a Markdown summary report from evaluation results."""

import json
from pathlib import Path

from loguru import logger


def _fmt_pct(val: float) -> str:
    return f"{val:.2%}"


def _fmt_num(val: float) -> str:
    if isinstance(val, int) or val == int(val):
        return str(int(val))
    return f"{val:.2f}"


def generate_summary(
    results_folder: Path,
    plots_dir: Path | None,
    output_path: Path,
    cost_metrics: dict | None = None,
) -> None:
    """Write a summary.md with a metrics table, per-subset breakdown, and plot links.

    Args:
        results_folder: Folder containing results_avg (or results_avg_all) JSON files.
        plots_dir: Folder with generated PNG plots (relative paths used in MD).
        output_path: Where to write summary.md.
        cost_metrics: Optional aggregated cost/token metrics dict.
    """
    lines: list[str] = ["# Evaluation Summary\n"]

    # --- Overall results ---
    for kind in ("unweighted", "weighted"):
        overall_file = results_folder / f"evaluation_results_{kind}.json"
        if overall_file.exists():
            with open(overall_file) as f:
                ov = json.load(f)
            lines.append(f"\n## Overall ({kind})\n")
            lines.append("| Metric | Value |")
            lines.append("|--------|-------|")
            for key, label in [
                ("precision", "Precision"),
                ("recall", "Recall"),
                ("f1_score", "F1"),
                ("f05_score", "F0.5"),
                ("severity_score", "Severity Score"),
            ]:
                if key in ov:
                    if key == "severity_score":
                        lines.append(f"| {label} | {_fmt_num(ov[key])} |")
                    else:
                        lines.append(f"| {label} | {_fmt_pct(ov[key])} |")
            lines.append("")

    # --- Per-subset breakdown ---
    subset_results = []
    for json_file in sorted(results_folder.glob("evaluation_results_*.json")):
        name = json_file.stem.replace("evaluation_results_", "")
        if name in ("unweighted", "weighted"):
            continue
        with open(json_file) as f:
            data = json.load(f)
        if isinstance(data, dict):
            subset_results.append(data)

    if subset_results:
        lines.append("\n## Per-Subset Results\n")
        lines.append("| Subset | TP | FP | FN | DUP | Precision | Recall | F1 | F0.5 | Severity |")
        lines.append("|--------|----|----|----|----|-----------|--------|----|----|------|")
        for r in subset_results:
            name = r.get("subset_name", "?")
            tp = _fmt_num(r.get("true_positives", 0))
            fp = _fmt_num(r.get("false_positives", 0))
            fn = _fmt_num(r.get("false_negatives", 0))
            dup = _fmt_num(r.get("duplicates", 0))
            p = _fmt_pct(r.get("precision", 0))
            rec = _fmt_pct(r.get("recall", 0))
            f1 = _fmt_pct(r.get("f1_score", 0))
            f05 = _fmt_pct(r.get("f05_score", 0))
            sev = _fmt_num(r.get("severity_score", 0))
            lines.append(f"| {name} | {tp} | {fp} | {fn} | {dup} | {p} | {rec} | {f1} | {f05} | {sev} |")
        lines.append("")

    # --- Cost metrics ---
    if cost_metrics:
        lines.append("\n## Cost & Token Metrics\n")
        lines.append("| Metric | Value |")
        lines.append("|--------|-------|")
        if "total_cost" in cost_metrics:
            lines.append(f"| Total Cost | ${cost_metrics['total_cost']:.2f} |")
        if "input_cost" in cost_metrics:
            lines.append(f"| Input Cost | ${cost_metrics['input_cost']:.2f} |")
        if "output_cost" in cost_metrics:
            lines.append(f"| Output Cost | ${cost_metrics['output_cost']:.2f} |")
        if "input_tokens" in cost_metrics:
            lines.append(f"| Input Tokens | {cost_metrics['input_tokens']:,.0f} |")
        if "output_tokens" in cost_metrics:
            lines.append(f"| Output Tokens | {cost_metrics['output_tokens']:,.0f} |")
        if "total_tokens" in cost_metrics:
            lines.append(f"| Total Tokens | {cost_metrics['total_tokens']:,.0f} |")
        if "duration_seconds" in cost_metrics:
            dur_h = cost_metrics["duration_seconds"] / 3600
            lines.append(f"| Duration | {dur_h:.1f}h |")
        if "cost_per_hour" in cost_metrics:
            lines.append(f"| Cost / Hour | ${cost_metrics['cost_per_hour']:.2f} |")
        if "cost_per_target" in cost_metrics:
            lines.append(f"| Cost / Target | ${cost_metrics['cost_per_target']:.2f} |")
        if "cost_per_tp" in cost_metrics:
            lines.append(f"| Cost / TP | ${cost_metrics['cost_per_tp']:.2f} |")
        if "n_runs" in cost_metrics:
            lines.append(f"| Runs | {cost_metrics['n_runs']} |")
        lines.append("")

        # Per-target breakdown
        per_target = cost_metrics.get("per_target")
        if per_target:
            lines.append("\n## Per-Target Metrics\n")
            lines.append("| Target | Cost | Tokens | Duration |")
            lines.append("|--------|------|--------|----------|")
            for tid, tm in sorted(per_target.items()):
                cost = f"${tm.get('total_cost', 0):.2f}"
                tokens = f"{tm.get('total_tokens', 0):,.0f}"
                dur_h = tm.get("duration_seconds", 0) / 3600
                duration = f"{dur_h:.1f}h"
                lines.append(f"| {tid} | {cost} | {tokens} | {duration} |")
            lines.append("")

    # --- Plot references ---
    if plots_dir and plots_dir.is_dir():
        pngs = sorted(plots_dir.glob("*.png"))
        if pngs:
            lines.append("\n## Plots\n")
            for png in pngs:
                rel = png.name
                lines.append(f"![{png.stem}](plots/{rel})\n")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines))
    logger.info(f"Summary report → {output_path}")


def generate_comparison_summary(
    all_results: dict[str, list[dict]],
    all_overall: dict[str, dict],
    plots_dir: Path | None,
    output_path: Path,
    all_cost: dict[str, dict] | None = None,
) -> None:
    """Write a comparison.md comparing multiple experiments.

    Args:
        all_results: {label → list of per-subset result dicts}
        all_overall: {label → overall (unweighted) result dict}
        plots_dir: Folder with comparison PNGs.
        output_path: Where to write comparison.md.
        all_cost: Optional {label → cost metrics dict}.
    """
    experiments = list(all_results.keys())
    lines: list[str] = ["# Experiment Comparison\n"]

    # --- Overall comparison table ---
    if all_overall:
        lines.append("\n## Overall Results (unweighted)\n")
        header = "| Metric | " + " | ".join(experiments) + " |"
        sep = "|--------" + "|-------" * len(experiments) + "|"
        lines.append(header)
        lines.append(sep)
        for key, label in [
            ("precision", "Precision"),
            ("recall", "Recall"),
            ("f1_score", "F1"),
            ("f05_score", "F0.5"),
        ]:
            row = f"| {label}"
            for exp in experiments:
                ov = all_overall.get(exp, {})
                val = ov.get(key)
                row += f" | {_fmt_pct(val)}" if val is not None else " | —"
            row += " |"
            lines.append(row)
        lines.append("")

    # --- Per-subset comparison ---
    subsets = sorted(
        {r.get("subset_name", "?") for results in all_results.values() for r in results}
    )
    if subsets:
        lines.append("\n## Per-Subset Comparison\n")
        for subset in subsets:
            lines.append(f"\n### {subset}\n")
            header = "| Metric | " + " | ".join(experiments) + " |"
            sep = "|--------" + "|-------" * len(experiments) + "|"
            lines.append(header)
            lines.append(sep)

            for key, label in [
                ("true_positives", "TP"),
                ("false_positives", "FP"),
                ("false_negatives", "FN"),
                ("duplicates", "Duplicates"),
                ("precision", "Precision"),
                ("recall", "Recall"),
                ("f1_score", "F1"),
                ("f05_score", "F0.5"),
                ("severity_score", "Severity"),
            ]:
                row = f"| {label}"
                for exp in experiments:
                    exp_results = {r.get("subset_name", "?"): r for r in all_results[exp]}
                    r = exp_results.get(subset, {})
                    val = r.get(key)
                    if val is None:
                        row += " | —"
                    elif key in ("precision", "recall", "f1_score", "f05_score"):
                        row += f" | {_fmt_pct(val)}"
                    else:
                        row += f" | {_fmt_num(val)}"
                row += " |"
            lines.append("")

    # --- Cost comparison ---
    if all_cost:
        lines.append("\n## Cost Comparison\n")
        header = "| Metric | " + " | ".join(experiments) + " |"
        sep = "|--------" + "|-------" * len(experiments) + "|"
        lines.append(header)
        lines.append(sep)
        for key, label, fmt in [
            ("total_cost", "Total Cost", "${:.2f}"),
            ("duration_seconds", "Duration (h)", None),
            ("cost_per_hour", "Cost / Hour", "${:.2f}"),
            ("cost_per_target", "Cost / Target", "${:.2f}"),
            ("cost_per_tp", "Cost / TP", "${:.2f}"),
            ("total_tokens", "Total Tokens", "{:,.0f}"),
        ]:
            row = f"| {label}"
            for exp in experiments:
                cm = all_cost.get(exp, {})
                val = cm.get(key)
                if val is None:
                    row += " | —"
                elif key == "duration_seconds":
                    row += f" | {val / 3600:.1f}h"
                elif fmt:
                    row += f" | {fmt.format(val)}"
                else:
                    row += f" | {val}"
            row += " |"
            lines.append(row)
        lines.append("")

    # --- Plot references ---
    if plots_dir and plots_dir.is_dir():
        pngs = sorted(plots_dir.glob("*.png"))
        if pngs:
            lines.append("\n## Plots\n")
            for png in pngs:
                rel = png.name
                lines.append(f"![{png.stem}](plots/{rel})\n")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines))
    logger.info(f"Comparison report → {output_path}")
