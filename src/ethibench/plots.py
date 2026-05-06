"""Generate PNG charts from evaluation results."""

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from loguru import logger


def _load_results(results_folder: Path) -> list[dict]:
    """Load all evaluation result JSON files from a folder."""
    results = []
    for json_file in sorted(results_folder.glob("evaluation_results_*.json")):
        name = json_file.stem.replace("evaluation_results_", "")
        if name in ("unweighted", "weighted"):
            continue
        with open(json_file) as f:
            data = json.load(f)
        if isinstance(data, dict):
            results.append(data)
    return results


def plot_metrics(results: list[dict], output_path: Path, title: str = "Evaluation Metrics") -> None:
    """Bar chart of F1, F0.5, Recall, Precision per subset."""
    if not results:
        return

    subsets = [r.get("subset_name", "?") for r in results]
    metrics = ["f1_score", "f05_score", "recall", "precision"]
    labels = ["F1", "F0.5", "Recall", "Precision"]
    colors = ["#2E6E3E", "#4C9A5E", "#78B67D", "#A8D5A2"]

    x = np.arange(len(subsets))
    width = 0.18

    fig, ax = plt.subplots(figsize=(max(8, len(subsets) * 2), 5))
    for i, (metric, label, color) in enumerate(zip(metrics, labels, colors)):
        values = [r.get(metric, 0) for r in results]
        stds = [r.get(f"{metric}_std", 0) for r in results]
        has_std = any(s > 0 for s in stds)
        ax.bar(
            x + i * width,
            values,
            width,
            label=label,
            color=color,
            edgecolor="#2C3E50",
            linewidth=0.8,
            yerr=stds if has_std else None,
            capsize=3,
        )

    ax.set_ylabel("Score")
    ax.set_title(title)
    ax.set_xticks(x + width * 1.5)
    ax.set_xticklabels(subsets)
    ax.set_ylim(0, 1.1)
    ax.legend()
    ax.grid(axis="y", alpha=0.3, linestyle="--")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)
    logger.info(f"Saved metrics plot → {output_path}")


def plot_counts(results: list[dict], output_path: Path, title: str = "Finding Counts") -> None:
    """Bar chart of TP, FP, FN, Duplicates per subset."""
    if not results:
        return

    subsets = [r.get("subset_name", "?") for r in results]
    categories = ["true_positives", "false_positives", "false_negatives", "duplicates"]
    labels = ["TP", "FP", "FN", "Duplicates"]
    colors = ["#3A9085", "#7A6FAF", "#A996CC", "#C5B887"]

    x = np.arange(len(subsets))
    width = 0.18

    fig, ax = plt.subplots(figsize=(max(8, len(subsets) * 2), 5))
    for i, (cat, label, color) in enumerate(zip(categories, labels, colors)):
        values = [r.get(cat, 0) for r in results]
        stds = [r.get(f"{cat}_std", 0) for r in results]
        has_std = any(s > 0 for s in stds)
        ax.bar(
            x + i * width,
            values,
            width,
            label=label,
            color=color,
            edgecolor="#2C3E50",
            linewidth=0.8,
            yerr=stds if has_std else None,
            capsize=3,
        )

    ax.set_ylabel("Count")
    ax.set_title(title)
    ax.set_xticks(x + width * 1.5)
    ax.set_xticklabels(subsets)
    ax.legend()
    ax.grid(axis="y", alpha=0.3, linestyle="--")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)
    logger.info(f"Saved counts plot → {output_path}")


def plot_overall(overall: dict, output_path: Path, title: str = "Overall Results") -> None:
    """Single bar chart for overall metrics."""
    metrics = ["f1_score", "f05_score", "recall", "precision"]
    labels = ["F1", "F0.5", "Recall", "Precision"]
    colors = ["#2E6E3E", "#4C9A5E", "#78B67D", "#A8D5A2"]
    values = [overall.get(m, 0) for m in metrics]

    fig, ax = plt.subplots(figsize=(6, 4))
    bars = ax.bar(labels, values, color=colors, edgecolor="#2C3E50", linewidth=0.8)
    for bar, val in zip(bars, values):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + 0.01,
            f"{val:.2%}",
            ha="center",
            va="bottom",
            fontsize=9,
        )

    ax.set_ylim(0, 1.1)
    ax.set_title(title)
    ax.grid(axis="y", alpha=0.3, linestyle="--")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)
    logger.info(f"Saved overall plot → {output_path}")


def plot_cost_breakdown(metrics: dict, output_path: Path, title: str = "Cost Breakdown") -> None:
    """Bar chart of total, input, and output costs."""
    labels = ["Total Cost", "Input Cost", "Output Cost"]
    keys = ["total_cost", "input_cost", "output_cost"]
    std_keys = [f"{k}_std" for k in keys]
    colors = ["#E74C3C", "#F1948A", "#CD6155"]

    values = [metrics.get(k, 0) for k in keys]
    stds = [metrics.get(sk, 0) for sk in std_keys]
    has_std = any(s > 0 for s in stds)

    fig, ax = plt.subplots(figsize=(6, 4))
    bars = ax.bar(
        labels,
        values,
        color=colors,
        edgecolor="#2C3E50",
        linewidth=0.8,
        yerr=stds if has_std else None,
        capsize=4,
    )
    for bar, val in zip(bars, values):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + 0.01,
            f"${val:.2f}",
            ha="center",
            va="bottom",
            fontsize=9,
        )

    ax.set_ylabel("Cost ($)")
    ax.set_title(title)
    ax.grid(axis="y", alpha=0.3, linestyle="--")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)
    logger.info(f"Saved cost plot → {output_path}")


def plot_tokens(metrics: dict, output_path: Path, title: str = "Token Usage") -> None:
    """Bar chart of total, input, and output token counts."""
    labels = ["Total Tokens", "Input Tokens", "Output Tokens"]
    keys = ["total_tokens", "input_tokens", "output_tokens"]
    std_keys = [f"{k}_std" for k in keys]
    colors = ["#3498DB", "#85C1E9", "#5DADE2"]

    values = [metrics.get(k, 0) for k in keys]
    stds = [metrics.get(sk, 0) for sk in std_keys]
    has_std = any(s > 0 for s in stds)

    fig, ax = plt.subplots(figsize=(6, 4))
    bars = ax.bar(
        labels,
        values,
        color=colors,
        edgecolor="#2C3E50",
        linewidth=0.8,
        yerr=stds if has_std else None,
        capsize=4,
    )
    for bar, val in zip(bars, values):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height(),
            f"{val:,.0f}",
            ha="center",
            va="bottom",
            fontsize=8,
        )

    ax.set_ylabel("Tokens")
    ax.set_title(title)
    ax.grid(axis="y", alpha=0.3, linestyle="--")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)
    logger.info(f"Saved tokens plot → {output_path}")


def plot_efficiency(metrics: dict, output_path: Path, title: str = "Efficiency Metrics") -> None:
    """Bar chart of cost/hour, cost/target, cost/TP, and duration."""
    items: list[tuple[str, str, str]] = []
    if "cost_per_hour" in metrics:
        items.append(("Cost / Hour", f"${metrics['cost_per_hour']:.2f}", "cost_per_hour"))
    if "cost_per_target" in metrics:
        items.append(("Cost / Target", f"${metrics['cost_per_target']:.2f}", "cost_per_target"))
    if "cost_per_tp" in metrics:
        items.append(("Cost / TP", f"${metrics['cost_per_tp']:.2f}", "cost_per_tp"))
    if "duration_seconds" in metrics:
        dur_h = metrics["duration_seconds"] / 3600
        items.append(("Duration (h)", f"{dur_h:.1f}", "duration_seconds"))

    if not items:
        return

    labels = [i[0] for i in items]
    display_values = [i[1] for i in items]
    values = [metrics.get(i[2], 0) for i in items]
    # Normalise duration to hours for display
    for idx, item in enumerate(items):
        if item[2] == "duration_seconds":
            values[idx] = metrics["duration_seconds"] / 3600

    colors = ["#8E44AD", "#AF7AC5", "#D2B4DE", "#F0E68C"]

    fig, ax = plt.subplots(figsize=(max(6, len(items) * 1.8), 4))
    bars = ax.bar(
        labels,
        values,
        color=colors[: len(items)],
        edgecolor="#2C3E50",
        linewidth=0.8,
    )
    for bar, dv in zip(bars, display_values):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + 0.01,
            dv,
            ha="center",
            va="bottom",
            fontsize=9,
        )

    ax.set_title(title)
    ax.grid(axis="y", alpha=0.3, linestyle="--")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)
    logger.info(f"Saved efficiency plot → {output_path}")


def plot_per_target_costs(
    per_target: dict[str, dict],
    output_path: Path,
    title: str = "Cost per Target",
) -> None:
    """Bar chart of total cost for each target."""
    if not per_target:
        return

    targets = list(per_target.keys())
    costs = [per_target[t].get("total_cost", 0) for t in targets]
    stds = [per_target[t].get("total_cost_std", 0) for t in targets]
    has_std = any(s > 0 for s in stds)

    fig, ax = plt.subplots(figsize=(max(6, len(targets) * 1.5), 4))
    bars = ax.bar(
        targets,
        costs,
        color="#E74C3C",
        edgecolor="#2C3E50",
        linewidth=0.8,
        yerr=stds if has_std else None,
        capsize=4,
    )
    for bar, val in zip(bars, costs):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + 0.01,
            f"${val:.2f}",
            ha="center",
            va="bottom",
            fontsize=8,
        )

    ax.set_ylabel("Cost ($)")
    ax.set_title(title)
    ax.grid(axis="y", alpha=0.3, linestyle="--")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    if len(targets) > 4:
        plt.xticks(rotation=30, ha="right")
    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)
    logger.info(f"Saved per-target cost plot → {output_path}")


def plot_per_target_duration(
    per_target: dict[str, dict],
    output_path: Path,
    title: str = "Duration per Target",
) -> None:
    """Bar chart of duration (hours) for each target."""
    if not per_target:
        return

    targets = list(per_target.keys())
    durations = [per_target[t].get("duration_seconds", 0) / 3600 for t in targets]
    stds = [per_target[t].get("duration_seconds_std", 0) / 3600 for t in targets]
    has_std = any(s > 0 for s in stds)

    fig, ax = plt.subplots(figsize=(max(6, len(targets) * 1.5), 4))
    bars = ax.bar(
        targets,
        durations,
        color="#9B59B6",
        edgecolor="#2C3E50",
        linewidth=0.8,
        yerr=stds if has_std else None,
        capsize=4,
    )
    for bar, val in zip(bars, durations):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + 0.01,
            f"{val:.1f}h",
            ha="center",
            va="bottom",
            fontsize=8,
        )

    ax.set_ylabel("Duration (hours)")
    ax.set_title(title)
    ax.grid(axis="y", alpha=0.3, linestyle="--")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    if len(targets) > 4:
        plt.xticks(rotation=30, ha="right")
    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)
    logger.info(f"Saved per-target duration plot → {output_path}")


def generate_plots(results_folder: Path, plots_dir: Path, cost_metrics: dict | None = None) -> None:
    """Generate all plots from a results folder (results_avg or results_avg_all).

    Produces:
      - plots/metrics_per_subset.png
      - plots/counts_per_subset.png
      - plots/overall_unweighted.png  (if available)
      - plots/overall_weighted.png    (if available)
      - plots/cost_breakdown.png      (if cost_metrics provided)
      - plots/token_usage.png         (if cost_metrics provided)
      - plots/efficiency.png          (if cost_metrics provided)
      - plots/per_target_costs.png    (if per_target data available)
      - plots/per_target_duration.png (if per_target data available)
    """
    plots_dir.mkdir(parents=True, exist_ok=True)

    subset_results = _load_results(results_folder)
    if subset_results:
        plot_metrics(subset_results, plots_dir / "metrics_per_subset.png")
        plot_counts(subset_results, plots_dir / "counts_per_subset.png")

    for kind in ("unweighted", "weighted"):
        overall_file = results_folder / f"evaluation_results_{kind}.json"
        if overall_file.exists():
            with open(overall_file) as f:
                overall = json.load(f)
            plot_overall(overall, plots_dir / f"overall_{kind}.png", title=f"Overall ({kind})")

    if cost_metrics:
        plot_cost_breakdown(cost_metrics, plots_dir / "cost_breakdown.png")
        plot_tokens(cost_metrics, plots_dir / "token_usage.png")
        plot_efficiency(cost_metrics, plots_dir / "efficiency.png")

        per_target = cost_metrics.get("per_target")
        if per_target:
            plot_per_target_costs(per_target, plots_dir / "per_target_costs.png")
            plot_per_target_duration(per_target, plots_dir / "per_target_duration.png")


# ---------------------------------------------------------------------------
# Cumulative analysis / overlap plots
# ---------------------------------------------------------------------------


def plot_jaccard_similarity(
    overlap_data: dict,
    output_path: Path,
    title: str = "Pairwise Jaccard Similarity Between Runs",
) -> None:
    """Bar plot of pairwise Jaccard similarity with a dashed mean line."""
    pairwise = overlap_data.get("overall", {}).get("pairwise_jaccard", {})
    mean_jaccard = overlap_data.get("overall", {}).get("mean_jaccard", 0)
    if not pairwise:
        return

    pairs = list(pairwise.keys())
    values = [pairwise[p] for p in pairs]

    fig, ax = plt.subplots(figsize=(max(6, len(pairs) * 1.5), 5))
    bars = ax.bar(
        pairs,
        values,
        color="#3498DB",
        edgecolor="#2C3E50",
        linewidth=0.8,
    )
    for bar, val in zip(bars, values):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + 0.01,
            f"{val:.3f}",
            ha="center",
            va="bottom",
            fontsize=9,
        )

    ax.axhline(y=mean_jaccard, color="#E74C3C", linestyle="--", linewidth=1.2, label=f"Mean = {mean_jaccard:.3f}")

    ax.set_ylabel("Jaccard Index")
    ax.set_title(title)
    ax.set_ylim(0, 1.15)
    ax.legend(fontsize=9)
    ax.grid(axis="y", alpha=0.3, linestyle="--")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    if len(pairs) > 4:
        plt.xticks(rotation=30, ha="right")
    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)
    logger.info(f"Saved Jaccard similarity plot → {output_path}")


def plot_vulnerability_frequency(
    overlap_data: dict,
    output_path: Path,
    title: str = "GT Vulnerability Discovery Frequency",
) -> None:
    """Bar plot showing how many GT entries were found by exactly N runs."""
    freq = overlap_data.get("overall", {}).get("frequency_distribution", {})
    if not freq:
        return

    # Sort by N (number of runs)
    keys = sorted(freq.keys(), key=int)
    counts = [freq[k] for k in keys]
    labels = [f"{k} run{'s' if int(k) != 1 else ''}" for k in keys]

    # Color gradient: red (0 runs) → yellow (some) → green (all runs)
    n_bars = len(keys)
    cmap = plt.cm.RdYlGn
    colors = [cmap(i / max(n_bars - 1, 1)) for i in range(n_bars)]

    fig, ax = plt.subplots(figsize=(max(6, n_bars * 1.2), 5))
    bars = ax.bar(
        labels,
        counts,
        color=colors,
        edgecolor="#2C3E50",
        linewidth=0.8,
    )
    for bar, val in zip(bars, counts):
        if val > 0:
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + 0.3,
                str(val),
                ha="center",
                va="bottom",
                fontsize=9,
                fontweight="bold",
            )

    ax.set_xlabel("Found by N runs")
    ax.set_ylabel("Number of GT Vulnerabilities")
    ax.set_title(title)
    ax.grid(axis="y", alpha=0.3, linestyle="--")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)
    logger.info(f"Saved vulnerability frequency plot → {output_path}")


def generate_cumulative_plots(
    results_avg_dir: Path,
    plots_dir: Path,
    overlap_data: dict,
) -> None:
    """Generate standard evaluation plots plus overlap-specific plots for cumulative analysis.

    Args:
        results_avg_dir: Cumulative results_avg folder (for standard metric plots).
        plots_dir: Output directory for PNGs (cumulative-analysis/plots/).
        overlap_data: Overlap data dict from compute_run_overlap().
    """
    # Standard evaluation plots (metrics, counts, overall)
    generate_plots(results_avg_dir, plots_dir)

    # Overlap-specific plots
    plot_jaccard_similarity(overlap_data, plots_dir / "jaccard_similarity.png")
    plot_vulnerability_frequency(overlap_data, plots_dir / "vulnerability_frequency.png")


# ---------------------------------------------------------------------------
# Comparison plots — side-by-side charts across multiple experiments
# ---------------------------------------------------------------------------

_COMPARE_COLORS = [
    "#4878D0",  # muted blue
    "#EE854A",  # muted orange
    "#6ACC64",  # muted green
    "#D65F5F",  # muted red
    "#956CB4",  # muted purple
    "#8C613C",  # muted brown
    "#DC7EC0",  # muted pink
    "#797979",  # muted gray
    "#D5BB67",  # muted gold
    "#82C6E2",  # muted cyan
]


def _style_ax(ax: plt.Axes) -> None:
    """Apply common styling to an axes."""
    ax.grid(axis="y", alpha=0.3, linestyle="--")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)


def plot_compare_metrics(
    all_results: dict[str, list[dict]],
    output_path: Path,
    title: str = "Metrics Comparison",
) -> None:
    """Grouped bar chart comparing F1, F0.5, Recall, Precision across experiments per subset."""
    labels_order = sorted(
        {r.get("subset_name", "?") for results in all_results.values() for r in results}
    )
    if not labels_order:
        return

    metrics = ["f1_score", "f05_score", "recall", "precision"]
    metric_labels = ["F1", "F0.5", "Recall", "Precision"]
    experiments = list(all_results.keys())
    n_exp = len(experiments)
    n_metrics = len(metrics)
    n_groups = len(labels_order)

    group_width = 0.8
    bar_width = group_width / (n_exp * n_metrics)

    fig, ax = plt.subplots(figsize=(max(10, n_groups * n_exp * 0.8), 6))
    x = np.arange(n_groups)

    for exp_i, exp_name in enumerate(experiments):
        exp_results = {r.get("subset_name", "?"): r for r in all_results[exp_name]}
        color = _COMPARE_COLORS[exp_i % len(_COMPARE_COLORS)]
        for m_i, (metric, m_label) in enumerate(zip(metrics, metric_labels)):
            offset = (exp_i * n_metrics + m_i - (n_exp * n_metrics) / 2 + 0.5) * bar_width
            values = [exp_results.get(s, {}).get(metric, 0) for s in labels_order]
            stds = [exp_results.get(s, {}).get(f"{metric}_std", 0) for s in labels_order]
            has_std = any(s > 0 for s in stds)
            label = f"{exp_name} — {m_label}" if m_i == 0 or n_exp <= 2 else None
            ax.bar(
                x + offset,
                values,
                bar_width * 0.9,
                label=f"{exp_name} — {m_label}",
                color=color,
                alpha=1.0 - m_i * 0.15,
                edgecolor="#2C3E50",
                linewidth=0.5,
                yerr=stds if has_std else None,
                capsize=2,
            )

    ax.set_ylabel("Score")
    ax.set_title(title)
    ax.set_xticks(x)
    ax.set_xticklabels(labels_order)
    ax.set_ylim(0, 1.15)
    ax.legend(fontsize=7, ncol=min(4, n_exp), loc="upper right")
    _style_ax(ax)
    fig.tight_layout()
    fig.savefig(output_path, dpi=300)
    plt.close(fig)
    logger.info(f"Saved comparison metrics plot → {output_path}")


def plot_compare_counts(
    all_overall: dict[str, dict],
    output_path: Path,
    title: str = "Overall Counts Comparison",
) -> None:
    """Side-by-side bar chart of overall TP, FP, FN, Duplicates across experiments."""
    if not all_overall:
        return

    categories = ["true_positives", "false_positives", "false_negatives", "duplicates"]
    cat_labels = ["TP", "FP", "FN", "DUP"]
    experiments = list(all_overall.keys())
    n_exp = len(experiments)

    x = np.arange(len(categories))
    width = 0.7 / n_exp

    fig, ax = plt.subplots(figsize=(max(8, n_exp * 2), 5))
    fig.subplots_adjust(top=0.82)

    for i, exp_name in enumerate(experiments):
        ov = all_overall[exp_name]
        values = [ov.get(c, 0) for c in categories]
        stds = [ov.get(f"{c}_std", 0) for c in categories]
        has_std = any(s > 0 for s in stds)
        color = _COMPARE_COLORS[i % len(_COMPARE_COLORS)]
        bars = ax.bar(
            x + (i - n_exp / 2 + 0.5) * width,
            values,
            width * 0.9,
            label=exp_name,
            color=color,
            edgecolor="white",
            linewidth=0.6,
            yerr=stds if has_std else None,
            capsize=3,
            error_kw={"elinewidth": 0.8, "capthick": 0.8, "ecolor": "#333333"},
        )
        for bar, val, std in zip(bars, values, stds):
            y_top = bar.get_height() + (std if has_std else 0) + 0.8
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                y_top,
                f"{val:.1f}",
                ha="center",
                va="bottom",
                fontsize=6,
                fontweight="medium",
            )

    ax.set_ylabel("Count", fontsize=10)
    ax.set_xticks(x)
    ax.set_xticklabels(cat_labels, fontsize=10)
    ax.set_ylim(bottom=0)
    ax.set_yticks([t for t in ax.get_yticks() if t <= 100])
    ax.set_title(title, fontsize=11, pad=12)
    ax.legend(
        fontsize=10,
        ncol=n_exp,
        loc="lower center",
        bbox_to_anchor=(0.5, 1.15),
        frameon=False,
        columnspacing=1.0,
        handlelength=1.2,
    )
    _style_ax(ax)
    fig.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    logger.info(f"Saved comparison counts plot → {output_path}")


def plot_compare_overall(
    all_overall: dict[str, dict],
    output_path: Path,
    title: str = "Overall Comparison",
) -> None:
    """Side-by-side bar chart of overall metrics across experiments."""
    if not all_overall:
        return

    metrics = ["f1_score", "f05_score", "recall", "precision"]
    metric_labels = ["F1", "F0.5", "Recall", "Precision"]
    experiments = list(all_overall.keys())
    n_exp = len(experiments)

    x = np.arange(len(metrics))
    width = 0.7 / n_exp

    fig, ax = plt.subplots(figsize=(max(8, n_exp * 2), 5))
    fig.subplots_adjust(top=0.82)

    for i, exp_name in enumerate(experiments):
        ov = all_overall[exp_name]
        values = [ov.get(m, 0) for m in metrics]
        stds = [ov.get(f"{m}_std", 0) for m in metrics]
        has_std = any(s > 0 for s in stds)
        color = _COMPARE_COLORS[i % len(_COMPARE_COLORS)]
        bars = ax.bar(
            x + (i - n_exp / 2 + 0.5) * width,
            values,
            width * 0.9,
            label=exp_name,
            color=color,
            edgecolor="white",
            linewidth=0.6,
            yerr=stds if has_std else None,
            capsize=3,
            error_kw={"elinewidth": 0.8, "capthick": 0.8, "ecolor": "#333333"},
        )
        for bar, val, std in zip(bars, values, stds):
            y_top = bar.get_height() + (std if has_std else 0) + 0.015
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                y_top,
                f"{val:.2%}",
                ha="center",
                va="bottom",
                fontsize=6,
                fontweight="medium",
            )

    ax.set_ylabel("Score", fontsize=10)
    ax.set_xticks(x)
    ax.set_xticklabels(metric_labels, fontsize=10)
    ax.set_ylim(0, 1.25)
    ax.set_yticks([t for t in ax.get_yticks() if t <= 1.0])
    ax.set_title(title, fontsize=11, pad=12)
    ax.legend(
        fontsize=10,
        ncol=n_exp,
        loc="lower center",
        bbox_to_anchor=(0.5, 1.15),
        frameon=False,
        columnspacing=1.0,
        handlelength=1.2,
    )
    _style_ax(ax)
    fig.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    logger.info(f"Saved comparison overall plot → {output_path}")


def plot_compare_cost(
    all_cost: dict[str, dict],
    output_path: Path,
    title: str = "Cost Comparison",
) -> None:
    """Side-by-side bar chart comparing total cost across experiments."""
    if not all_cost:
        return

    experiments = list(all_cost.keys())
    costs = [all_cost[e].get("total_cost", 0) for e in experiments]
    stds = [all_cost[e].get("total_cost_std", 0) for e in experiments]
    has_std = any(s > 0 for s in stds)
    colors = [_COMPARE_COLORS[i % len(_COMPARE_COLORS)] for i in range(len(experiments))]

    fig, ax = plt.subplots(figsize=(max(6, len(experiments) * 1.5), 5))
    bars = ax.bar(
        experiments,
        costs,
        color=colors,
        edgecolor="#2C3E50",
        linewidth=0.8,
        yerr=stds if has_std else None,
        capsize=4,
    )
    for bar, val in zip(bars, costs):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + 0.01,
            f"${val:.2f}",
            ha="center",
            va="bottom",
            fontsize=9,
        )

    ax.set_ylabel("Cost ($)")
    ax.set_title(title)
    _style_ax(ax)
    if len(experiments) > 4:
        plt.xticks(rotation=30, ha="right")
    fig.tight_layout()
    fig.savefig(output_path, dpi=300)
    plt.close(fig)
    logger.info(f"Saved comparison cost plot → {output_path}")


def _plot_grouped_bars(
    ax: plt.Axes,
    experiments: list[str],
    values_per_exp: list[list[float]],
    stds_per_exp: list[list[float]],
    x_labels: list[str],
    ylabel: str,
    value_fmt: str = "{:.1f}",
    label_fontsize: float = 6,
) -> None:
    """Draw grouped bars on *ax* for the combined figure."""
    n_exp = len(experiments)
    x = np.arange(len(x_labels))
    width = 0.7 / n_exp

    for i, exp_name in enumerate(experiments):
        vals = values_per_exp[i]
        sds = stds_per_exp[i]
        has_std = any(s > 0 for s in sds)
        color = _COMPARE_COLORS[i % len(_COMPARE_COLORS)]
        bars = ax.bar(
            x + (i - n_exp / 2 + 0.5) * width,
            vals,
            width * 0.9,
            label=exp_name,
            color=color,
            edgecolor="white",
            linewidth=0.6,
            yerr=sds if has_std else None,
            capsize=3,
            error_kw={"elinewidth": 0.8, "capthick": 0.8, "ecolor": "#333333"},
        )
        for bar, val, std in zip(bars, vals, sds):
            y_top = bar.get_height() + (std if has_std else 0)
            offset = ax.get_ylim()[1] * 0.01
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                y_top + offset,
                value_fmt.format(val),
                ha="center",
                va="bottom",
                fontsize=label_fontsize,
                fontweight="medium",
            )

    ax.set_ylabel(ylabel, fontsize=10)
    ax.set_xticks(x)
    ax.set_xticklabels(x_labels, fontsize=10)
    _style_ax(ax)


def plot_compare_combined(
    all_overall: dict[str, dict],
    all_cost: dict[str, dict] | None,
    output_path: Path,
) -> None:
    """Combined 3-row figure: metrics, counts, then severity/cwe/cost/duration."""
    if not all_overall:
        return

    experiments = list(all_overall.keys())
    n_exp = len(experiments)

    fig = plt.figure(figsize=(max(16, n_exp * 2.5), 14))
    gs = fig.add_gridspec(3, 4, hspace=0.45, wspace=0.35, top=0.90)

    # --- Row 1: Overall metrics (spans full width) ---
    ax_metrics = fig.add_subplot(gs[0, :])
    metrics = ["f1_score", "f05_score", "recall", "precision"]
    metric_labels = ["F1", "F0.5", "Recall", "Precision"]
    vals = [[all_overall[e].get(m, 0) for m in metrics] for e in experiments]
    sds = [[all_overall[e].get(f"{m}_std", 0) for m in metrics] for e in experiments]
    _plot_grouped_bars(ax_metrics, experiments, vals, sds, metric_labels, "Score", value_fmt="{:.2%}")
    ax_metrics.set_ylim(0, 1.25)
    ax_metrics.set_yticks([t for t in ax_metrics.get_yticks() if t <= 1.0])
    ax_metrics.set_title("Overall Comparison", fontsize=11, pad=8)

    # --- Row 2: Overall counts (spans full width) ---
    ax_counts = fig.add_subplot(gs[1, :])
    categories = ["true_positives", "false_positives", "false_negatives", "duplicates"]
    cat_labels = ["TP", "FP", "FN", "DUP"]
    vals = [[all_overall[e].get(c, 0) for c in categories] for e in experiments]
    sds = [[all_overall[e].get(f"{c}_std", 0) for c in categories] for e in experiments]
    _plot_grouped_bars(ax_counts, experiments, vals, sds, cat_labels, "Count", value_fmt="{:.1f}")
    ax_counts.set_ylim(bottom=0)
    ax_counts.set_yticks([t for t in ax_counts.get_yticks() if t <= 100])
    ax_counts.set_title("Overall Counts Comparison", fontsize=11, pad=8)

    # --- Row 3, col 0: Severity Score ---
    ax_sev = fig.add_subplot(gs[2, 0])
    sev_vals = [[all_overall[e].get("severity_score", 0)] for e in experiments]
    sev_sds = [[all_overall[e].get("severity_score_std", 0)] for e in experiments]
    _plot_grouped_bars(ax_sev, experiments, sev_vals, sev_sds, ["Severity"], "Score", value_fmt="{:.0f}")
    ax_sev.set_title("Severity Score", fontsize=11, pad=8)

    # --- Row 3, col 1: CWE Coverage ---
    ax_cwe = fig.add_subplot(gs[2, 1])
    cwe_vals = [[all_overall[e].get("cwe_coverage", 0)] for e in experiments]
    cwe_sds = [[all_overall[e].get("cwe_coverage_std", 0)] for e in experiments]
    _plot_grouped_bars(ax_cwe, experiments, cwe_vals, cwe_sds, ["CWE Coverage"], "# Unique CWEs", value_fmt="{:.0f}")
    ax_cwe.set_title("CWE Coverage", fontsize=11, pad=8)

    # --- Row 3, col 2: Cost ---
    ax_cost = fig.add_subplot(gs[2, 2])
    if all_cost:
        cost_vals = [[all_cost[e].get("total_cost", 0)] for e in experiments if e in all_cost]
        cost_sds = [[all_cost[e].get("total_cost_std", 0)] for e in experiments if e in all_cost]
        cost_exps = [e for e in experiments if e in all_cost]
    else:
        cost_vals = [[0] for _ in experiments]
        cost_sds = [[0] for _ in experiments]
        cost_exps = experiments
    _plot_grouped_bars(ax_cost, cost_exps, cost_vals, cost_sds, ["Cost"], "Cost ($)", value_fmt="${:.2f}")
    ax_cost.set_title("Total Cost", fontsize=11, pad=8)

    # --- Row 3, col 3: Duration ---
    ax_dur = fig.add_subplot(gs[2, 3])
    if all_cost:
        dur_vals = [[all_cost[e].get("duration_seconds", 0) / 3600] for e in experiments if e in all_cost]
        dur_sds = [[all_cost[e].get("duration_seconds_std", 0) / 3600] for e in experiments if e in all_cost]
        dur_exps = [e for e in experiments if e in all_cost]
    else:
        dur_vals = [[0] for _ in experiments]
        dur_sds = [[0] for _ in experiments]
        dur_exps = experiments
    _plot_grouped_bars(ax_dur, dur_exps, dur_vals, dur_sds, ["Duration"], "Duration (hours)", value_fmt="{:.1f}h")
    ax_dur.set_title("Total Duration", fontsize=11, pad=8)

    # --- Single legend at the top ---
    handles, labels = ax_metrics.get_legend_handles_labels()
    fig.legend(
        handles,
        labels,
        fontsize=10,
        ncol=n_exp,
        loc="lower center",
        bbox_to_anchor=(0.5, 0.93),
        frameon=False,
        columnspacing=1.0,
        handlelength=1.2,
    )

    fig.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    logger.info(f"Saved combined comparison plot \u2192 {output_path}")


def plot_compare_combined_per_target(
    target_subset_data: dict[str, dict],
    per_target_cost: dict[str, dict] | None,
    output_path: Path,
    target_label: str = "Target",
) -> None:
    """Combined 3-row figure for a single target/subset: metrics, counts, severity/cwe/cost/duration."""
    if not target_subset_data:
        return

    experiments = list(target_subset_data.keys())
    n_exp = len(experiments)

    fig = plt.figure(figsize=(max(16, n_exp * 2.5), 14))
    gs = fig.add_gridspec(3, 4, hspace=0.45, wspace=0.35, top=0.90)

    # --- Row 1: Metrics (spans full width) ---
    ax_metrics = fig.add_subplot(gs[0, :])
    metrics = ["f1_score", "f05_score", "recall", "precision"]
    metric_labels = ["F1", "F0.5", "Recall", "Precision"]
    vals = [[target_subset_data[e].get(m, 0) for m in metrics] for e in experiments]
    sds = [[target_subset_data[e].get(f"{m}_std", 0) for m in metrics] for e in experiments]
    _plot_grouped_bars(ax_metrics, experiments, vals, sds, metric_labels, "Score", value_fmt="{:.2%}")
    ax_metrics.set_ylim(0, 1.25)
    ax_metrics.set_yticks([t for t in ax_metrics.get_yticks() if t <= 1.0])
    ax_metrics.set_title(f"{target_label} \u2014 Metrics Comparison", fontsize=11, pad=8)

    # --- Row 2: Counts (spans full width) ---
    ax_counts = fig.add_subplot(gs[1, :])
    categories = ["true_positives", "false_positives", "false_negatives", "duplicates"]
    cat_labels = ["TP", "FP", "FN", "DUP"]
    vals = [[target_subset_data[e].get(c, 0) for c in categories] for e in experiments]
    sds = [[target_subset_data[e].get(f"{c}_std", 0) for c in categories] for e in experiments]
    _plot_grouped_bars(ax_counts, experiments, vals, sds, cat_labels, "Count", value_fmt="{:.1f}")
    ax_counts.set_ylim(bottom=0)
    ax_counts.set_title(f"{target_label} \u2014 Counts Comparison", fontsize=11, pad=8)

    # --- Row 3, col 0: Severity Score ---
    ax_sev = fig.add_subplot(gs[2, 0])
    sev_vals = [[target_subset_data[e].get("severity_score", 0)] for e in experiments]
    sev_sds = [[target_subset_data[e].get("severity_score_std", 0)] for e in experiments]
    _plot_grouped_bars(ax_sev, experiments, sev_vals, sev_sds, ["Severity"], "Score", value_fmt="{:.0f}")
    ax_sev.set_title("Severity Score", fontsize=11, pad=8)

    # --- Row 3, col 1: CWE Coverage ---
    ax_cwe = fig.add_subplot(gs[2, 1])
    cwe_vals = [[target_subset_data[e].get("cwe_coverage", 0)] for e in experiments]
    cwe_sds = [[target_subset_data[e].get("cwe_coverage_std", 0)] for e in experiments]
    _plot_grouped_bars(ax_cwe, experiments, cwe_vals, cwe_sds, ["CWE Coverage"], "# Unique CWEs", value_fmt="{:.0f}")
    ax_cwe.set_title("CWE Coverage", fontsize=11, pad=8)

    # --- Row 3, col 2: Cost ---
    ax_cost = fig.add_subplot(gs[2, 2])
    if per_target_cost:
        cost_vals = [[per_target_cost[e].get("total_cost", 0)] for e in experiments if e in per_target_cost]
        cost_sds = [[per_target_cost[e].get("total_cost_std", 0)] for e in experiments if e in per_target_cost]
        cost_exps = [e for e in experiments if e in per_target_cost]
    else:
        cost_vals = [[0] for _ in experiments]
        cost_sds = [[0] for _ in experiments]
        cost_exps = experiments
    _plot_grouped_bars(ax_cost, cost_exps, cost_vals, cost_sds, ["Cost"], "Cost ($)", value_fmt="${:.2f}")
    ax_cost.set_title("Cost", fontsize=11, pad=8)

    # --- Row 3, col 3: Duration ---
    ax_dur = fig.add_subplot(gs[2, 3])
    if per_target_cost:
        dur_vals = [[per_target_cost[e].get("duration_seconds", 0) / 3600] for e in experiments if e in per_target_cost]
        dur_sds = [[per_target_cost[e].get("duration_seconds_std", 0) / 3600] for e in experiments if e in per_target_cost]
        dur_exps = [e for e in experiments if e in per_target_cost]
    else:
        dur_vals = [[0] for _ in experiments]
        dur_sds = [[0] for _ in experiments]
        dur_exps = experiments
    _plot_grouped_bars(ax_dur, dur_exps, dur_vals, dur_sds, ["Duration"], "Duration (hours)", value_fmt="{:.1f}h")
    ax_dur.set_title("Duration", fontsize=11, pad=8)

    # --- Single legend at the top ---
    handles, labels = ax_metrics.get_legend_handles_labels()
    fig.legend(
        handles,
        labels,
        fontsize=10,
        ncol=n_exp,
        loc="lower center",
        bbox_to_anchor=(0.5, 0.93),
        frameon=False,
        columnspacing=1.0,
        handlelength=1.2,
    )

    fig.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    logger.info(f"Saved per-target combined comparison plot \u2192 {output_path}")


# ---------------------------------------------------------------------------
# Cumulative comparison plots — compare cumulative results across experiments
# ---------------------------------------------------------------------------


def _plot_jaccard_on_ax(
    ax: plt.Axes,
    overlap_data: dict,
    bar_color: str,
    title: str,
    subset_key: str | None = None,
) -> None:
    """Draw Jaccard similarity bars on an existing axes with comparison aesthetic."""
    if subset_key:
        source = overlap_data.get("per_subset", {}).get(subset_key, {})
    else:
        source = overlap_data.get("overall", {})
    pairwise = source.get("pairwise_jaccard", {})
    mean_jaccard = source.get("mean_jaccard", 0)
    if not pairwise:
        return

    pairs = list(pairwise.keys())
    pair_labels = [p.replace(" vs ", "\nvs\n") for p in pairs]
    values = [pairwise[p] for p in pairs]

    bars = ax.bar(
        pair_labels,
        values,
        color=bar_color,
        edgecolor="white",
        linewidth=0.6,
    )
    for bar, val in zip(bars, values):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + 0.01,
            f"{val:.3f}",
            ha="center",
            va="bottom",
            fontsize=6,
            fontweight="medium",
        )

    ax.axhline(
        y=mean_jaccard, color="#E74C3C", linestyle="--", linewidth=1.2,
        label=f"Mean = {mean_jaccard:.3f}",
    )
    ax.set_ylabel("Jaccard Index", fontsize=10)
    ax.set_ylim(0, 1.15)
    ax.legend(fontsize=8)
    ax.set_title(title, fontsize=10, pad=8)
    if len(pairs) > 3:
        ax.tick_params(axis="x", labelsize=7, rotation=20)
    else:
        ax.tick_params(axis="x", labelsize=8)
    _style_ax(ax)


def _plot_frequency_on_ax(
    ax: plt.Axes,
    overlap_data: dict,
    title: str,
    subset_key: str | None = None,
) -> None:
    """Draw vulnerability frequency bars on an existing axes with comparison aesthetic."""
    if subset_key:
        source = overlap_data.get("per_subset", {}).get(subset_key, {})
    else:
        source = overlap_data.get("overall", {})
    freq = source.get("frequency_distribution", {})
    if not freq:
        return

    keys = sorted(freq.keys(), key=int)
    counts = [freq[k] for k in keys]
    labels = [f"{k} run{'s' if int(k) != 1 else ''}" for k in keys]

    n_bars = len(keys)
    cmap = plt.cm.RdYlGn
    colors = [cmap(i / max(n_bars - 1, 1)) for i in range(n_bars)]

    bars = ax.bar(
        labels,
        counts,
        color=colors,
        edgecolor="white",
        linewidth=0.6,
    )
    for bar, val in zip(bars, counts):
        if val > 0:
            offset = ax.get_ylim()[1] * 0.01 if ax.get_ylim()[1] > 0 else 0.3
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + offset,
                str(val),
                ha="center",
                va="bottom",
                fontsize=6,
                fontweight="medium",
            )

    ax.set_xlabel("Found by N runs", fontsize=9)
    ax.set_ylabel("# GT Vulnerabilities", fontsize=10)
    ax.set_title(title, fontsize=10, pad=8)
    ax.tick_params(axis="x", labelsize=8)
    _style_ax(ax)


def _plot_delta_on_ax(
    ax: plt.Axes,
    cum_data: dict,
    avg_data: dict,
    bar_color: str,
    title: str,
) -> None:
    """Draw relative % delta bars (cum vs avg) for F1, F0.5, Recall, Precision."""
    metric_keys = ["f1_score", "f05_score", "recall", "precision"]
    metric_labels = ["F1", "F0.5", "Recall", "Precision"]

    deltas = []
    for key in metric_keys:
        avg_val = avg_data.get(key, 0)
        cum_val = cum_data.get(key, 0)
        if avg_val != 0:
            deltas.append((cum_val - avg_val) / abs(avg_val) * 100)
        else:
            deltas.append(0.0)

    colors = [bar_color if d >= 0 else "#D65F5F" for d in deltas]

    bars = ax.bar(
        metric_labels,
        deltas,
        color=colors,
        edgecolor="white",
        linewidth=0.6,
    )
    for bar, val in zip(bars, deltas):
        sign = "+" if val >= 0 else ""
        va = "bottom" if val >= 0 else "top"
        offset = 0.5 if val >= 0 else -0.5
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + offset,
            f"{sign}{val:.1f}%",
            ha="center",
            va=va,
            fontsize=7,
            fontweight="medium",
        )

    ax.axhline(y=0, color="#333333", linewidth=0.8)
    ax.set_ylabel("\u0394 (%)", fontsize=10)
    ax.set_title(title, fontsize=10, pad=8)
    ax.tick_params(axis="x", labelsize=8)
    _style_ax(ax)


def _plot_tp_distribution_on_ax(
    ax: plt.Axes,
    overlap_data: dict,
    bar_color: str,
    title: str,
    subset_key: str | None = None,
) -> None:
    """Draw TP distribution bars: % of TPs found in exactly N runs."""
    if subset_key:
        source = overlap_data.get("per_subset", {}).get(subset_key, {})
    else:
        source = overlap_data.get("overall", {})
    freq = source.get("frequency_distribution", {})
    if not freq:
        return

    # Exclude key "0" (vulns not found by any run)
    keys = sorted([k for k in freq.keys() if int(k) > 0], key=int)
    if not keys:
        return

    counts = [freq[k] for k in keys]
    total_tps = sum(counts)
    if total_tps == 0:
        return

    percentages = [c / total_tps * 100 for c in counts]
    labels = [f"{k} run{'s' if int(k) != 1 else ''}" for k in keys]

    n_bars = len(keys)
    cmap = plt.cm.RdYlGn
    colors = [cmap(i / max(n_bars - 1, 1)) for i in range(n_bars)]

    bars = ax.bar(
        labels,
        percentages,
        color=colors,
        edgecolor="white",
        linewidth=0.6,
    )
    for bar, pct in zip(bars, percentages):
        if pct > 0:
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + 0.5,
                f"{pct:.1f}%",
                ha="center",
                va="bottom",
                fontsize=6,
                fontweight="medium",
            )

    ax.set_xlabel("Found by N runs", fontsize=9)
    ax.set_ylabel("% of TPs", fontsize=10)
    ax.set_title(title, fontsize=10, pad=8)
    ax.tick_params(axis="x", labelsize=8)
    _style_ax(ax)


def plot_compare_cumulative_combined(
    all_cumul_overall: dict[str, dict],
    all_overlap: dict[str, dict],
    all_avg_overall: dict[str, dict],
    output_path: Path,
) -> None:
    """Combined 2-row figure for cumulative comparison.

    Row 1: Overall cumulative metrics (F1, F0.5, Recall, Precision).
    Row 2: % delta bars + TP distribution for the experiments
            with largest and smallest |avg_F1 − cumul_F1| delta.
    """
    if not all_cumul_overall:
        return

    experiments = list(all_cumul_overall.keys())
    n_exp = len(experiments)

    # Compute F1 deltas between average and cumulative results
    deltas: dict[str, float] = {}
    for exp in experiments:
        avg_f1 = all_avg_overall.get(exp, {}).get("f1_score", 0)
        cum_f1 = all_cumul_overall[exp].get("f1_score", 0)
        deltas[exp] = abs(avg_f1 - cum_f1)

    # Find min and max delta experiments (only among those with overlap data)
    exps_with_overlap = [e for e in experiments if e in all_overlap and all_overlap[e]]
    if len(exps_with_overlap) < 2:
        exps_with_overlap = experiments[:2] if len(experiments) >= 2 else experiments

    min_exp = min(exps_with_overlap, key=lambda e: deltas.get(e, float("inf")))
    max_exp = max(exps_with_overlap, key=lambda e: deltas.get(e, 0))

    n_cols = 4  # Always 2 pairs

    fig = plt.figure(figsize=(max(16, n_exp * 2.5), 10))
    gs = fig.add_gridspec(2, n_cols, hspace=0.45, wspace=0.35, top=0.88)

    # --- Row 1: Overall cumulative metrics (spans full width) ---
    ax_metrics = fig.add_subplot(gs[0, :])
    metrics = ["f1_score", "f05_score", "recall", "precision"]
    metric_labels = ["F1", "F0.5", "Recall", "Precision"]
    vals = [[all_cumul_overall[e].get(m, 0) for m in metrics] for e in experiments]
    sds = [[all_cumul_overall[e].get(f"{m}_std", 0) for m in metrics] for e in experiments]
    _plot_grouped_bars(ax_metrics, experiments, vals, sds, metric_labels, "Score", value_fmt="{:.2%}")
    ax_metrics.set_ylim(0, 1.25)
    ax_metrics.set_yticks([t for t in ax_metrics.get_yticks() if t <= 1.0])
    ax_metrics.set_title("Cumulative Overall Comparison", fontsize=11, pad=8)

    # --- Row 2: Delta bars + TP distribution ---
    max_idx = experiments.index(max_exp)
    min_idx = experiments.index(min_exp)
    max_color = _COMPARE_COLORS[max_idx % len(_COMPARE_COLORS)]
    min_color = _COMPARE_COLORS[min_idx % len(_COMPARE_COLORS)]

    col = 0

    # Pair 1: max-delta (biggest)
    ax_delta_max = fig.add_subplot(gs[1, col])
    _plot_delta_on_ax(
        ax_delta_max,
        all_cumul_overall[max_exp],
        all_avg_overall.get(max_exp, {}),
        max_color,
        f"\u0394 Cumul vs Avg — {max_exp}",
    )
    col += 1

    ax_tp_max = fig.add_subplot(gs[1, col])
    if max_exp in all_overlap:
        _plot_tp_distribution_on_ax(
            ax_tp_max, all_overlap[max_exp], max_color,
            f"TP Distribution — {max_exp}",
        )
    col += 1

    # Pair 2: min-delta (smallest)
    ax_delta_min = fig.add_subplot(gs[1, col])
    _plot_delta_on_ax(
        ax_delta_min,
        all_cumul_overall[min_exp],
        all_avg_overall.get(min_exp, {}),
        min_color,
        f"\u0394 Cumul vs Avg — {min_exp}",
    )
    col += 1

    ax_tp_min = fig.add_subplot(gs[1, col])
    if min_exp in all_overlap:
        _plot_tp_distribution_on_ax(
            ax_tp_min, all_overlap[min_exp], min_color,
            f"TP Distribution — {min_exp}",
        )

    # --- Synchronize y-axis scales for paired plots ---
    # Delta plots: use symmetric range based on the largest absolute value
    delta_ylim = max(abs(ax_delta_max.get_ylim()[0]), abs(ax_delta_max.get_ylim()[1]),
                     abs(ax_delta_min.get_ylim()[0]), abs(ax_delta_min.get_ylim()[1]))
    delta_ylim *= 1.15  # padding for labels
    ax_delta_max.set_ylim(-delta_ylim, delta_ylim)
    ax_delta_min.set_ylim(-delta_ylim, delta_ylim)
    # TP distribution plots: use the larger upper limit
    tp_ylim = max(ax_tp_max.get_ylim()[1], ax_tp_min.get_ylim()[1])
    ax_tp_max.set_ylim(0, tp_ylim)
    ax_tp_min.set_ylim(0, tp_ylim)

    # --- Single legend at the top (from Row 1) ---
    handles, labels = ax_metrics.get_legend_handles_labels()
    fig.legend(
        handles,
        labels,
        fontsize=10,
        ncol=n_exp,
        loc="lower center",
        bbox_to_anchor=(0.5, 0.91),
        frameon=False,
        columnspacing=1.0,
        handlelength=1.2,
    )

    fig.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    logger.info(f"Saved cumulative combined comparison plot \u2192 {output_path}")


def plot_compare_cumulative_combined_per_target(
    target_cumul_data: dict[str, dict],
    all_overlap: dict[str, dict],
    target_avg_data: dict[str, dict],
    output_path: Path,
    target_id: str = "target",
    subset_name: str = "Target",
) -> None:
    """Combined 2-row figure for per-target cumulative comparison.

    Row 1: Per-target cumulative metrics (F1, F0.5, Recall, Precision).
    Row 2: % delta bars + TP distribution for the experiments
            with largest and smallest |avg_F1 − cumul_F1| delta.
    """
    if not target_cumul_data:
        return

    experiments = list(target_cumul_data.keys())
    n_exp = len(experiments)

    # Compute F1 deltas between average and cumulative results
    deltas: dict[str, float] = {}
    for exp in experiments:
        avg_f1 = target_avg_data.get(exp, {}).get("f1_score", 0)
        cum_f1 = target_cumul_data[exp].get("f1_score", 0)
        deltas[exp] = abs(avg_f1 - cum_f1)

    # Find min and max delta experiments (only among those with overlap data)
    exps_with_overlap = [
        e for e in experiments
        if e in all_overlap and all_overlap[e]
        and all_overlap[e].get("per_subset", {}).get(subset_name, {}).get("frequency_distribution")
    ]
    if len(exps_with_overlap) < 2:
        exps_with_overlap = experiments[:2] if len(experiments) >= 2 else experiments

    min_exp = min(exps_with_overlap, key=lambda e: deltas.get(e, float("inf")))
    max_exp = max(exps_with_overlap, key=lambda e: deltas.get(e, 0))

    n_cols = 4  # Always 2 pairs

    fig = plt.figure(figsize=(max(16, n_exp * 2.5), 10))
    gs = fig.add_gridspec(2, n_cols, hspace=0.45, wspace=0.35, top=0.88)

    # --- Row 1: Per-target cumulative metrics (spans full width) ---
    ax_metrics = fig.add_subplot(gs[0, :])
    metrics = ["f1_score", "f05_score", "recall", "precision"]
    metric_labels = ["F1", "F0.5", "Recall", "Precision"]
    vals = [[target_cumul_data[e].get(m, 0) for m in metrics] for e in experiments]
    sds = [[target_cumul_data[e].get(f"{m}_std", 0) for m in metrics] for e in experiments]
    _plot_grouped_bars(ax_metrics, experiments, vals, sds, metric_labels, "Score", value_fmt="{:.2%}")
    ax_metrics.set_ylim(0, 1.25)
    ax_metrics.set_yticks([t for t in ax_metrics.get_yticks() if t <= 1.0])
    ax_metrics.set_title(f"{target_id} \u2014 Cumulative Comparison", fontsize=11, pad=8)

    # --- Row 2: Delta bars + TP distribution ---
    max_idx = experiments.index(max_exp)
    min_idx = experiments.index(min_exp)
    max_color = _COMPARE_COLORS[max_idx % len(_COMPARE_COLORS)]
    min_color = _COMPARE_COLORS[min_idx % len(_COMPARE_COLORS)]

    col = 0

    # Pair 1: max-delta (biggest)
    ax_delta_max = fig.add_subplot(gs[1, col])
    _plot_delta_on_ax(
        ax_delta_max,
        target_cumul_data[max_exp],
        target_avg_data.get(max_exp, {}),
        max_color,
        f"\u0394 Cumul vs Avg — {max_exp}",
    )
    col += 1

    ax_tp_max = fig.add_subplot(gs[1, col])
    if max_exp in all_overlap:
        _plot_tp_distribution_on_ax(
            ax_tp_max, all_overlap[max_exp], max_color,
            f"TP Distribution — {max_exp}",
            subset_key=subset_name,
        )
    col += 1

    # Pair 2: min-delta (smallest)
    ax_delta_min = fig.add_subplot(gs[1, col])
    _plot_delta_on_ax(
        ax_delta_min,
        target_cumul_data[min_exp],
        target_avg_data.get(min_exp, {}),
        min_color,
        f"\u0394 Cumul vs Avg — {min_exp}",
    )
    col += 1

    ax_tp_min = fig.add_subplot(gs[1, col])
    if min_exp in all_overlap:
        _plot_tp_distribution_on_ax(
            ax_tp_min, all_overlap[min_exp], min_color,
            f"TP Distribution — {min_exp}",
            subset_key=subset_name,
        )

    # --- Synchronize y-axis scales for paired plots ---
    # Delta plots: use symmetric range based on the largest absolute value
    delta_ylim = max(abs(ax_delta_max.get_ylim()[0]), abs(ax_delta_max.get_ylim()[1]),
                     abs(ax_delta_min.get_ylim()[0]), abs(ax_delta_min.get_ylim()[1]))
    delta_ylim *= 1.15  # padding for labels
    ax_delta_max.set_ylim(-delta_ylim, delta_ylim)
    ax_delta_min.set_ylim(-delta_ylim, delta_ylim)
    # TP distribution plots: use the larger upper limit
    tp_ylim = max(ax_tp_max.get_ylim()[1], ax_tp_min.get_ylim()[1])
    ax_tp_max.set_ylim(0, tp_ylim)
    ax_tp_min.set_ylim(0, tp_ylim)

    # --- Single legend at the top (from Row 1) ---
    handles, labels = ax_metrics.get_legend_handles_labels()
    fig.legend(
        handles,
        labels,
        fontsize=10,
        ncol=n_exp,
        loc="lower center",
        bbox_to_anchor=(0.5, 0.91),
        frameon=False,
        columnspacing=1.0,
        handlelength=1.2,
    )

    fig.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    logger.info(f"Saved per-target cumulative combined comparison plot \u2192 {output_path}")


def generate_cumulative_comparison_plots(
    all_cumul_results: dict[str, list[dict]],
    all_cumul_overall: dict[str, dict],
    all_overlap: dict[str, dict],
    all_avg_overall: dict[str, dict],
    plots_dir: Path,
    all_avg_results: dict[str, list[dict]] | None = None,
    all_cost: dict[str, dict] | None = None,
) -> None:
    """Generate all cumulative comparison plots.

    Args:
        all_cumul_results: {label → list of per-subset cumulative result dicts}
        all_cumul_overall: {label → cumulative overall (unweighted) result dict}
        all_overlap: {label → run_overlap.json data dict}
        all_avg_overall: {label → average overall (unweighted) result dict}
        plots_dir: Output directory for PNGs.
        all_avg_results: Optional {label → list of per-subset average result dicts}.
        all_cost: Optional {label → cost metrics dict} for target_id resolution.
    """
    plots_dir.mkdir(parents=True, exist_ok=True)

    if all_cumul_overall:
        plot_compare_overall(
            all_cumul_overall, plots_dir / "compare_overall_cumulative.png",
            title="Cumulative Overall Comparison",
        )
        plot_compare_counts(
            all_cumul_overall, plots_dir / "compare_counts_cumulative.png",
            title="Cumulative Overall Counts Comparison",
        )
        plot_compare_cumulative_combined(
            all_cumul_overall, all_overlap, all_avg_overall,
            plots_dir / "compare_combined_cumulative.png",
        )

    # Per-target cumulative combined plots
    if all_cumul_results:
        subset_names: set[str] = set()
        for results_list in all_cumul_results.values():
            for r in results_list:
                if "subset_name" in r:
                    subset_names.add(r["subset_name"])

        for subset_name in sorted(subset_names):
            # Extract per-subset cumulative data for each experiment
            target_cumul_data: dict[str, dict] = {}
            for label, results_list in all_cumul_results.items():
                for r in results_list:
                    if r.get("subset_name") == subset_name:
                        target_cumul_data[label] = r
                        break

            if not target_cumul_data:
                continue

            # Extract per-subset average data for delta computation
            target_avg_data: dict[str, dict] = {}
            if all_avg_results:
                for label, results_list in all_avg_results.items():
                    for r in results_list:
                        if r.get("subset_name") == subset_name:
                            target_avg_data[label] = r
                            break

            # Resolve target_id from cost per_target keys
            target_id: str | None = None
            if all_cost:
                subset_norm = subset_name.replace("-", "").lower()
                for cost_data in all_cost.values():
                    pt = cost_data.get("per_target", {})
                    for tid in pt:
                        tid_norm = tid.replace("-", "").lower()
                        if tid_norm in subset_norm or subset_norm in tid_norm:
                            target_id = tid
                            break
                    if target_id:
                        break

            filename_slug = target_id if target_id else subset_name.lower().replace(" ", "-")
            filename = f"compare_combined_cumulative_{filename_slug}.png"
            plot_compare_cumulative_combined_per_target(
                target_cumul_data,
                all_overlap,
                target_avg_data,
                plots_dir / filename,
                target_id=filename_slug,
                subset_name=subset_name,
            )


def generate_comparison_plots(
    all_results: dict[str, list[dict]],
    all_overall: dict[str, dict],
    plots_dir: Path,
    all_cost: dict[str, dict] | None = None,
) -> None:
    """Generate all comparison plots.

    Args:
        all_results: {label → list of per-subset result dicts}
        all_overall: {label → overall (unweighted) result dict}
        plots_dir: Output directory for PNGs.
        all_cost: Optional {label → cost metrics dict}.
    """
    plots_dir.mkdir(parents=True, exist_ok=True)

    if all_results:
        plot_compare_metrics(all_results, plots_dir / "compare_metrics.png")

    if all_overall:
        plot_compare_overall(all_overall, plots_dir / "compare_overall.png")
        plot_compare_counts(all_overall, plots_dir / "compare_counts.png")

    if all_cost:
        plot_compare_cost(all_cost, plots_dir / "compare_cost.png")

    if all_overall:
        plot_compare_combined(all_overall, all_cost, plots_dir / "compare_combined.png")

    # Per-target combined plots
    if all_results:
        subset_names: set[str] = set()
        for results_list in all_results.values():
            for r in results_list:
                if "subset_name" in r:
                    subset_names.add(r["subset_name"])

        for subset_name in sorted(subset_names):
            target_subset_data: dict[str, dict] = {}
            for label, results_list in all_results.items():
                for r in results_list:
                    if r.get("subset_name") == subset_name:
                        target_subset_data[label] = r
                        break

            if not target_subset_data:
                continue

            # Resolve target_id from cost per_target keys
            target_id: str | None = None
            per_target_cost: dict[str, dict] | None = None
            if all_cost:
                subset_norm = subset_name.replace("-", "").lower()
                for label, cost_data in all_cost.items():
                    pt = cost_data.get("per_target", {})
                    for tid in pt:
                        tid_norm = tid.replace("-", "").lower()
                        if tid_norm in subset_norm or subset_norm in tid_norm:
                            target_id = tid
                            break
                    if target_id:
                        break

                if target_id:
                    per_target_cost = {}
                    for label, cost_data in all_cost.items():
                        pt = cost_data.get("per_target", {})
                        if target_id in pt:
                            per_target_cost[label] = pt[target_id]

            filename = f"compare_combined_{target_id}.png" if target_id else f"compare_combined_{subset_name.lower()}.png"
            plot_compare_combined_per_target(
                target_subset_data,
                per_target_cost if per_target_cost else None,
                plots_dir / filename,
                target_label=target_id if target_id else subset_name,
            )
