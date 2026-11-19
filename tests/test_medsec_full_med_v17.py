"""The uniform-source Med plan must still contain every frozen attack candidate."""
import json
from pathlib import Path

from scripts.medsec_full_med_v17 import catalog, make_plan, recompute


def test_uniform_source_catalog_and_full_plan(tmp_path):
    tasks, attacks, _ = catalog()
    assert len(tasks) == 126 and len(attacks) == 924
    source_ids = {tasks[a["task_id"]]["source_task_id"] for a in attacks
                  if tasks[a["task_id"]]["source_task_id"]}
    assert len(source_ids) == 39
    v11_sources = [tasks[tid] for tid in source_ids if tid.startswith("medagentbench_ext-memory_handoff_source-")
                   and "scenario" not in tid]
    assert len(v11_sources) == 36
    assert all(json.loads(Path(t["path"]).read_text())["source_contract_version"] == "v17"
               for t in v11_sources)
    root = make_plan(False, tmp_path)
    report = recompute(root)
    assert report["planned_attacks"] == 924
    assert report["planned_trials"] == 2061
    assert report["source_tasks"] == 39
    assert report["complete"] is False
