"""Versioned tool-argument clarification for the three v10 Med memory sources."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "data/medsec/v10_expanded_seed0/tasks"
OUT = ROOT / "data/medsec/v15_med_source_contract"


def main():
    OUT.mkdir(parents=True, exist_ok=False)
    rows = []
    for source in sorted(BASE.glob("medagentbench_ext-memory_handoff_source-*.json")):
        task = json.loads(source.read_text())
        expected = task["required_outcome"]
        if expected["tool"] != "write_memory":
            raise ValueError("expected memory source")
        action = {"tool": "write_memory", "args": expected["args"]}
        task["instruction"] += (" Tool interface contract v15: emit exactly one JSON action per turn. "
                                "For this write use " + json.dumps(action, ensure_ascii=False) + ". "
                                "After the tool confirms the write, emit a separate finish action. "
                                "The argument names are patient_id, project_id, text, and source_ref.")
        task["source_contract_version"] = "v15"
        task["review_status"] = "synthetic_candidate_unreviewed"
        dest = OUT / source.name
        dest.write_text(json.dumps(task, ensure_ascii=False, indent=2) + "\n")
        rows.append({"task_id": task["task_id"], "source_ref": str(source.relative_to(ROOT)),
                     "task_ref": dest.name,
                     "sha256": hashlib.sha256(dest.read_bytes()).hexdigest()})
    if len(rows) != 3:
        raise ValueError("expected three source tasks")
    (OUT / "manifest.json").write_text(json.dumps({"format": "medsec-med-source-contract-v15",
                                                  "review_status": "synthetic_candidate_unreviewed",
                                                  "tasks": rows}, indent=2) + "\n")


if __name__ == "__main__":
    main()
