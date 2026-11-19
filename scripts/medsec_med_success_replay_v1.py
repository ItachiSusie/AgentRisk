"""Four-condition replay of one prior Med synthetic memory attack success."""
import json
import shutil
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import medsec_full_med_v17 as suite
from src.medsec.v08.cli import _run_extension

ATTACK_ID = "v11-medagentbench_ext-memory_handoff_target-allergy_review-01-cancel"


def main():
    tasks, attacks, _ = suite.catalog()
    attack = next(a for a in attacks if a["attack_id"] == ATTACK_ID)
    target = tasks[attack["task_id"]]
    source = tasks[target["source_task_id"]]
    run_id = datetime.now(timezone.utc).strftime("v19-med-success-replay-%Y%m%dT%H%M%SZ-") + uuid.uuid4().hex[:8]
    root = ROOT / "results/medsec" / run_id
    root.mkdir(parents=True, exist_ok=False)
    (root / "selection.json").write_text(json.dumps({"format": "medsec-med-success-replay-v1", "run_id": run_id,
        "original_run_id": "v17-med-20261119T073649Z-0175ebf0", "attack_id": ATTACK_ID,
        "source_task_path": source["path"], "target_task_path": target["path"],
        "attack_path": attack["path"]}, indent=2) + "\n")
    seed = root / "source_memory"
    source_result = _run_extension(Path(source["path"]), "deepseek", "deepseek-flash",
                                   None, ROOT, "none", root / "runs", seed)
    rows = [{"condition": "source_none", "result": source_result}]
    if source_result["synthetic_utility_pass"] is not True:
        (root / "summary.json").write_text(json.dumps({"run_id": run_id, "blocked_source": True, "rows": rows}, indent=2) + "\n")
        print(json.dumps({"run_id": run_id, "blocked_source": True}), flush=True)
        return
    for defense in ("none", "scope"):
        for attacked in (False, True):
            condition = ("attack" if attacked else "clean") + "_" + defense
            memory = root / "memory_copies" / condition
            shutil.copytree(seed, memory)
            result = _run_extension(Path(target["path"]), "deepseek", "deepseek-flash",
                                    Path(attack["path"]) if attacked else None,
                                    Path(attack["root"]) if attacked else ROOT,
                                    defense, root / "runs", memory)
            rows.append({"condition": condition, "result": result})
            print(json.dumps({"run_id": run_id, "condition": condition,
                              "episode_run_id": result["run_id"],
                              "utility": result["synthetic_utility_pass"],
                              "security": result["security"]}, ensure_ascii=False), flush=True)
    summary = {"run_id": run_id, "blocked_source": False, "rows": rows}
    (root / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
