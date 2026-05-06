"""One-time script to generate selected_findings.json."""
import json
import random
from collections import defaultdict
from pathlib import Path

DIR = Path(__file__).parent

with open(DIR / "annotations.json") as f:
    annotations = json.load(f)

findings_by_uuid = {}
with open(DIR / "findings.jsonl") as f:
    for line in f:
        item = json.loads(line)
        findings_by_uuid[item["uuid"]] = item

tp_candidates = []
fp_candidates = []

for uuid, ann in annotations.items():
    if ann.get("duplicate", False):
        continue
    if not ann.get("finished", False):
        continue
    selected = ann.get("selected_gt_ids", [])
    fp = ann.get("false_positive", False)
    if len(selected) == 1 and not fp:
        tp_candidates.append(uuid)
    elif len(selected) == 0 and fp:
        fp_candidates.append(uuid)

print(f"TP candidates (1 GT, not dup): {len(tp_candidates)}")
print(f"FP candidates (0 GT, FP=true, not dup): {len(fp_candidates)}")

# Enforce no two TPs share a GT
gt_to_tps = defaultdict(list)
for uuid in tp_candidates:
    gt_id = annotations[uuid]["selected_gt_ids"][0]
    gt_to_tps[gt_id].append(uuid)

print(f"Unique GTs among TP candidates: {len(gt_to_tps)}")

rng = random.Random(42)
unique_tp_pool = []
for gt_id, uuids in sorted(gt_to_tps.items()):
    unique_tp_pool.append(rng.choice(uuids))

rng.shuffle(unique_tp_pool)
print(f"Unique TP pool (1 per GT): {len(unique_tp_pool)}")

selected_tps = unique_tp_pool[:25]
rng.shuffle(fp_candidates)
selected_fps = fp_candidates[:25]

print(f"Selected TPs: {len(selected_tps)}")
print(f"Selected FPs: {len(selected_fps)}")

tp_targets = set(findings_by_uuid[u]["target_id"] for u in selected_tps if u in findings_by_uuid)
fp_targets = set(findings_by_uuid[u]["target_id"] for u in selected_fps if u in findings_by_uuid)
print(f"TP targets: {tp_targets}")
print(f"FP targets: {fp_targets}")

result = {"tp_uuids": selected_tps, "fp_uuids": selected_fps, "seed": 42}
with open(DIR / "selected_findings.json", "w") as f:
    json.dump(result, f, indent=2)
print("Wrote selected_findings.json")
