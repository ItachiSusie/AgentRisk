"""Replay three previously successful Health synthetic attack candidates."""
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.medsec.v08.contracts import sha256
from src.medsec.v12 import experiment

ATTACK_IDS = (
    "v10-healthagentbench_synthetic-ehr_data_quality-02-scenario-03-malicious_user-output_disclosure",
    "v10-healthagentbench_synthetic-ehr_data_quality-02-scenario-02-skill_file-workflow_dependency",
    "v12-care_transition-defer",
)
ORIGINAL_CATALOG = experiment.catalog


def selected_catalog():
    tasks, attacks = ORIGINAL_CATALOG()
    chosen = [next(a for a in attacks if a["attack_id"] == attack_id) for attack_id in ATTACK_IDS]
    selected_ids = {a["task_id"] for a in chosen} | {a["source_task_id"] for a in chosen if a.get("source_task_id")}
    return {tid: task for tid, task in tasks.items() if tid in selected_ids}, chosen


async def main():
    experiment.catalog = selected_catalog
    root = await experiment.run(smoke=False, workers=3)
    note = {"format": "medsec-health-success-replay-v1", "run_id": root.name,
            "original_run_id": "v12-health-20261118T060836Z-b3d3cb98",
            "selected_attack_ids": ATTACK_IDS,
            "wrapper_sha256": sha256(Path(__file__).read_bytes())}
    (root / "replay_selection_note.json").write_text(json.dumps(note, indent=2) + "\n")


if __name__ == "__main__":
    asyncio.run(main())
