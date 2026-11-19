"""The full Med plan must cover each attack once and preserve source dependencies."""
import json

from scripts.medsec_full_med_v14 import catalog, load_plan, make_plan, recompute


def test_full_catalog_and_memory_sources():
    tasks, attacks, inputs = catalog()
    assert len(tasks) == 126
    assert len(attacks) == 924
    assert len({a["attack_id"] for a in attacks}) == 924
    assert len({a["task_id"] for a in attacks}) == 87
    sources = {tasks[a["task_id"]]["source_task_id"] for a in attacks
               if tasks[a["task_id"]]["source_task_id"]}
    assert len(sources) == 39
    assert all(source in tasks and tasks[source]["role"] == "source" for source in sources)
    assert all(path and fingerprint for path, fingerprint in inputs.items())


def test_smoke_plan_is_separate_and_unscored_before_execution(tmp_path):
    root = make_plan(smoke=True, output_root=tmp_path)
    plan = load_plan(root)
    assert {a["surface"] for a in plan["attacks"]} == {
        "fhir_response", "malicious_user", "skill_file", "tool_result", "memory_store_edit"}
    assert any(a["attack_id"].startswith("v11-") for a in plan["attacks"])
    assert set(plan["source_task_ids"]) <= set(plan["tasks"])
    result = recompute(root)
    assert result["complete"] is False
    assert result["recorded_trials"] == 0
    assert result["planned_trials"] == len(plan["source_task_ids"]) + 2 * len(plan["target_task_ids"]) + 2 * len(plan["attacks"])
    assert not (root / "report.json").exists()
