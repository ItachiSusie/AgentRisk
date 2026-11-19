"""Versioned memory source prompts are isolated from the v10 task files."""
import json
from pathlib import Path

from scripts.medsec_full_med_v15 import catalog, make_plan, recompute, core


ROOT = Path(__file__).resolve().parents[1]


def test_source_contract_keeps_v10_tasks_immutable():
    tasks, attacks, _ = catalog()
    assert len(tasks) == 126 and len(attacks) == 924
    sources = [t for t in tasks.values() if t["role"] == "source" and "scenario" in t["task_id"]]
    assert len(sources) == 3
    for row in sources:
        task = json.loads(Path(row["path"]).read_text())
        assert task["source_contract_version"] == "v15"
        assert "one JSON action per turn" in task["instruction"]
        original = ROOT / "data/medsec/v10_expanded_seed0/tasks" / Path(row["path"]).name
        assert "source_contract_version" not in json.loads(original.read_text())


def test_v15_plan_and_smoke_replay(tmp_path):
    previous_format = core.FORMAT
    core.FORMAT = "medsec-med-full-v15"
    try:
        root = make_plan(True, tmp_path)
        plan = json.loads((root / "plan.json").read_text())
        assert plan["format"] == "medsec-med-full-v15"
        assert len(plan["attacks"]) == 6
        report = recompute(root)
        assert report["complete"] is False and report["recorded_trials"] == 0
    finally:
        core.FORMAT = previous_format
