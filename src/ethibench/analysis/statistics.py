"""Matching statistics — GT coverage, findings-per-GT distribution."""

import json
from collections import defaultdict
from pathlib import Path

from loguru import logger


def load_ground_truths(gt_dir: Path) -> tuple[dict[str, dict], dict[str, list[str]]]:
    """Load all GT files and return (gt_by_id, gt_ids_by_subset)."""
    gt_by_id: dict[str, dict] = {}
    gt_ids_by_subset: dict[str, list[str]] = defaultdict(list)

    for gt_file in gt_dir.glob("*_gt.jsonl"):
        with open(gt_file) as f:
            for line in f:
                if not line.strip():
                    continue
                gt = json.loads(line)
                gt_id = gt.get("id")
                subset = gt.get("subset_name")
                if gt_id and subset:
                    gt_by_id[gt_id] = gt
                    gt_ids_by_subset[subset].append(gt_id)

    return gt_by_id, dict(gt_ids_by_subset)


def compute_statistics(
    output_dir: Path,
    gt_dir: Path,
) -> dict:
    """Compute matching statistics from raw_matchings and ground truth.

    Returns a dict with:
      - total_gt: total ground truth entries
      - total_subsets: number of subsets
      - per_subset: dict of subset → {total_gt, matched_gt, unmatched_gt, findings_per_gt_avg, ...}
      - unmatched_gts: list of GT entries with no findings across any run
    """
    gt_by_id, gt_ids_by_subset = load_ground_truths(gt_dir)
    raw_dir = output_dir / "raw_matchings"

    if not raw_dir.is_dir():
        logger.warning("No raw_matchings/ found.")
        return {}

    # Build gt_id → list of finding UUIDs from raw matchings
    gt_to_findings: dict[str, set[str]] = defaultdict(set)

    for raw_file in raw_dir.glob("matchings_*.json"):
        with open(raw_file) as f:
            raw_list = json.load(f)
        for raw_m in raw_list:
            for uuid, data in raw_m.items():
                for gt_id in data.get("selected_gt_ids", []):
                    gt_to_findings[gt_id].add(uuid)

    # Per-subset stats
    per_subset: dict[str, dict] = {}
    all_unmatched: list[dict] = []

    for subset, gt_ids in sorted(gt_ids_by_subset.items()):
        matched = 0
        findings_counts: list[int] = []
        for gt_id in gt_ids:
            n = len(gt_to_findings.get(gt_id, set()))
            findings_counts.append(n)
            if n > 0:
                matched += 1
            else:
                all_unmatched.append(gt_by_id[gt_id])

        total = len(gt_ids)
        avg = sum(findings_counts) / total if total else 0
        max_f = max(findings_counts) if findings_counts else 0
        min_f = min(findings_counts) if findings_counts else 0

        per_subset[subset] = {
            "total_gt": total,
            "matched_gt": matched,
            "unmatched_gt": total - matched,
            "findings_per_gt_avg": round(avg, 2),
            "findings_per_gt_max": max_f,
            "findings_per_gt_min": min_f,
        }
        logger.info(f"  {subset}: {matched}/{total} GTs matched, avg {avg:.1f} findings/GT")

    return {
        "total_gt": len(gt_by_id),
        "total_subsets": len(gt_ids_by_subset),
        "per_subset": per_subset,
        "unmatched_gts": all_unmatched,
    }
