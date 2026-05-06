"""Extract findings with no ground truth match (false positives)."""

import json
from pathlib import Path

from loguru import logger


def extract_unmatched(output_dir: Path, findings_file: Path | None = None) -> dict:
    """Find findings that had no match in raw_matchings (true false positives).

    Args:
        output_dir: The evaluation_outputs directory containing raw_matchings/.
        findings_file: Optional findings_parsed.jsonl for full finding objects.

    Returns:
        Dict mapping subset → {"uuids": list[str], "findings": list[dict]}.
    """
    raw_dir = output_dir / "raw_matchings"
    if not raw_dir.is_dir():
        logger.warning("No raw_matchings/ found in output_dir.")
        return {}

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

        with open(raw_file) as f:
            raw_list = json.load(f)

        unmatched_uuids: set[str] = set()
        for raw_m in raw_list:
            for uuid, data in raw_m.items():
                if not data.get("selected_gt_ids", []):
                    unmatched_uuids.add(uuid)

        uuids = sorted(unmatched_uuids)
        findings = [findings_by_uuid[u] for u in uuids if u in findings_by_uuid]

        results[subset] = {"uuids": uuids, "findings": findings}
        logger.info(f"  {subset}: {len(uuids)} unmatched findings")

    return results
