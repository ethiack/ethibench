"""Duplicate detection — findings that matched GT in raw matching but were removed by bipartite."""

import json
from pathlib import Path

from loguru import logger


def calculate_duplicates_for_run(raw_matching: dict, matching: dict) -> tuple[int, list[str]]:
    """Count duplicates and return their UUIDs.

    A duplicate is a finding with non-empty selected_gt_ids in raw_matching
    but empty selected_gt_ids in the final matching.
    """
    dup_count = 0
    dup_uuids: list[str] = []

    for uuid, raw_data in raw_matching.items():
        raw_gt_ids = raw_data.get("selected_gt_ids", [])
        if not raw_gt_ids:
            continue
        final_gt_ids = matching.get(uuid, {}).get("selected_gt_ids", [])
        if not final_gt_ids:
            dup_count += 1
            dup_uuids.append(uuid)

    return dup_count, dup_uuids


def extract_duplicates(output_dir: Path, findings_file: Path | None = None) -> dict:
    """Analyze duplicates across all subsets in an evaluation output directory.

    Args:
        output_dir: The evaluation_outputs directory containing raw_matchings/ and matchings/.
        findings_file: Optional findings_parsed.jsonl for extracting full finding objects.

    Returns:
        Dict mapping subset name → {"count": int, "uuids": list[str], "findings": list[dict]}.
    """
    raw_dir = output_dir / "raw_matchings"
    match_dir = output_dir / "matchings"

    if not raw_dir.is_dir() or not match_dir.is_dir():
        logger.warning("No raw_matchings/ or matchings/ found in output_dir.")
        return {}

    # Load findings if provided
    findings_by_uuid: dict[str, dict] = {}
    if findings_file and findings_file.exists():
        with open(findings_file) as f:
            for line in f:
                if line.strip():
                    item = json.loads(line)
                    if "uuid" in item:
                        findings_by_uuid[item["uuid"]] = item

    results: dict[str, dict] = {}

    for raw_file in sorted(raw_dir.glob("matchings_*.json")):
        subset = raw_file.stem.replace("matchings_", "")
        match_file = match_dir / raw_file.name

        if not match_file.exists():
            continue

        with open(raw_file) as f:
            raw_list = json.load(f)
        with open(match_file) as f:
            match_list = json.load(f)

        all_uuids: list[str] = []
        total_dups = 0

        for raw_m, final_m in zip(raw_list, match_list):
            count, uuids = calculate_duplicates_for_run(raw_m, final_m)
            total_dups += count
            all_uuids.extend(uuids)

        unique_uuids = list(set(all_uuids))
        dup_findings = [findings_by_uuid[u] for u in unique_uuids if u in findings_by_uuid]

        results[subset] = {
            "count": total_dups,
            "uuids": unique_uuids,
            "findings": dup_findings,
        }
        logger.info(f"  {subset}: {total_dups} duplicates ({len(unique_uuids)} unique)")

    return results
