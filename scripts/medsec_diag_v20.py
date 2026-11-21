"""Small-scale v20 executor diagnostic.

Runs a handful of existing v10 Med tasks plus the redesigned v20 judgment-memory
scenario through the v20 episode loop (one-action-per-turn, parse-retry feedback,
metadata-stripped memory) and reports the signals the v17 full run could not
separate from a protocol bug:

  * invalid_action rate and turns-per-episode (did the loop stop talking on
    turn 1?),
  * clean synthetic utility,
  * for each attack: triggered / exposed / success via the v08 security scorer.

This is a diagnostic, not a frozen benchmark run: one sample per cell, no clean
baseline gating, no official scores. Results land in a fresh run_id directory
and are recomputable from the saved events.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import statistics
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.medsec.v08.attack import load_attack
from src.medsec.v08.contracts import Events, sha256
from src.medsec.v08.models import DeepSeekTextModel
from src.medsec.v08.scoring import security_score
from src.medsec.v20 import episode as v20_episode

MODEL = "deepseek-flash"
V10 = ROOT / "data/medsec/v10_expanded_seed0"
V20MEM = ROOT / "data/medsec/v20_memory_judgment"

# One clean normal task per Med family that the v17 run saw die at invalid_action.
NORMAL_TASKS = [
    "tasks/medagentbench_ext-lab_followup-01-scenario-01.json",
    "tasks/medagentbench_ext-medication_reconciliation-01-scenario-01.json",
    "tasks/medagentbench_ext-portal_message-01-scenario-01.json",
    "tasks/medagentbench_ext-referral_appointment-01-scenario-01.json",
]
# One attack per non-memory surface, all on lab_followup-01 (goal: wrong_patient).
LAB = "medagentbench_ext-lab_followup-01-scenario-01"
SURFACE_ATTACKS = [
    f"attacks/v10-{LAB}-fhir_response-authority_spoof.json",
    f"attacks/v10-{LAB}-skill_file-authority_spoof.json",
    f"attacks/v10-{LAB}-malicious_user-authority_spoof.json",
    f"attacks/v10-{LAB}-tool_result-authority_spoof.json",
]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def v20_code_hashes() -> dict:
    folder = ROOT / "src/medsec/v20"
    return {str(p.relative_to(ROOT)): digest(p) for p in sorted(folder.rglob("*.py"))}


def _write(path: Path, obj) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n")
    return digest(path)


def run_episode(run_root: Path, label: str, task_path: Path, *, defense: str,
                attack_path: Path | None, attack_root: Path, memory_root: Path | None,
                model_name: str, dry_run: bool) -> dict:
    task = json.loads(task_path.read_text())
    sample = payload = None
    if attack_path:
        sample, payload = load_attack(attack_path, attack_root,
                                      Events("preflight", "medagentbench_ext", task["task_id"]))
        if sample.get("task_id") != task["task_id"]:
            raise ValueError("attack/task mismatch: " + label)
    if dry_run:
        return {"label": label, "task_id": task["task_id"], "defense": defense,
                "attack_id": sample["attack_id"] if sample else None, "dry_run": True}
    run_id = datetime.now(timezone.utc).strftime("v20-%Y%m%dT%H%M%SZ-") + uuid.uuid4().hex[:12]
    episode_dir = run_root / "episodes" / run_id
    model = DeepSeekTextModel(model_name, json_mode=True)
    result = v20_episode.run_extension(task, model, run_id, workspace=episode_dir / "workspace",
                                       attack=sample, payload=payload, defense_policy=defense,
                                       memory_root=memory_root)
    events = result["events"]
    events_path = episode_dir / "events.jsonl"
    episode_dir.mkdir(parents=True, exist_ok=True)
    events_path.write_text("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in events))
    outcome = {"status": result["status"], "result": result["result"],
               "synthetic_utility_pass": result["synthetic_utility_pass"],
               "parse_failures": result["parse_failures"], "state_fingerprint": result["state_fingerprint"]}
    _write(episode_dir / "outcome.json", outcome)
    security = security_score(sample, events) if sample else None
    turns = sum(e["kind"] == "model_response" for e in events)
    tool_actions = sum(e["kind"] == "model_action" for e in events)
    manifest = {"format": "medsec-v20-diag", "run_id": run_id, "label": label,
                "benchmark_id": "medagentbench_ext", "task_id": task["task_id"], "defense": defense,
                "model": model_name, "attack_id": sample["attack_id"] if sample else None,
                "events_sha256": digest(events_path),
                "response_meta_last": getattr(model, "last_response", None)}
    _write(episode_dir / "manifest.json", manifest)
    return {"label": label, "run_id": run_id, "task_id": task["task_id"], "defense": defense,
            "attack_id": sample["attack_id"] if sample else None, "status": result["status"],
            "turns": turns, "tool_actions": tool_actions, "parse_failures": result["parse_failures"],
            "synthetic_utility_pass": result["synthetic_utility_pass"],
            "result": result["result"], "security": security}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output-root", type=Path, default=ROOT / "results/medsec")
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    run_id = datetime.now(timezone.utc).strftime("v20-diag-%Y%m%dT%H%M%SZ-") + uuid.uuid4().hex[:8]
    run_root = args.output_root.resolve() / run_id
    run_root.mkdir(parents=True, exist_ok=False)

    inputs = {}
    for ref in NORMAL_TASKS + SURFACE_ATTACKS:
        inputs[str((V10 / ref))] = digest(V10 / ref)
    for sub in sorted((V20MEM).rglob("*")):
        if sub.is_file():
            inputs[str(sub)] = digest(sub)
    plan = {"format": "medsec-v20-diag-plan", "run_id": run_id, "model": args.model,
            "temperature": 0, "json_mode": True, "max_steps": 12, "parse_retry_budget": 3,
            "v20_code_sha256": v20_code_hashes(), "inputs": inputs,
            "note": "diagnostic; one sample per cell; not a frozen benchmark score"}
    _write(run_root / "plan.json", plan)

    records = []
    # A. normal clean, defense none
    for ref in NORMAL_TASKS:
        records.append(run_episode(run_root, "normal_clean_none", V10 / ref, defense="none",
                                   attack_path=None, attack_root=V10, memory_root=None,
                                   model_name=args.model, dry_run=args.dry_run))
    # B. one attack per surface on lab_followup, defense none
    lab_task = V10 / f"tasks/{LAB}.json"
    for ref in SURFACE_ATTACKS:
        records.append(run_episode(run_root, "surface_attack_none", lab_task, defense="none",
                                   attack_path=V10 / ref, attack_root=V10, memory_root=None,
                                   model_name=args.model, dry_run=args.dry_run))
    # C. v20 judgment memory: source -> clean target -> attack target (none, scope)
    man = json.loads((V20MEM / "manifest.json").read_text())
    src = next(t for t in man["tasks"] if t["role"] == "source")
    tgt = next(t for t in man["tasks"] if t["role"] == "target")
    atk = man["attacks"][0]
    if not args.dry_run:
        mem_src = run_root / "memory" / "source"
        records.append(run_episode(run_root, "memory_source", V20MEM / src["task_ref"], defense="none",
                                   attack_path=None, attack_root=V20MEM, memory_root=mem_src,
                                   model_name=args.model, dry_run=False))
        source_ok = records[-1]["synthetic_utility_pass"] is True
        for cond, defense, attack_ref in (("clean_none", "none", None),
                                          ("attack_none", "none", atk["attack_ref"]),
                                          ("attack_scope", "scope", atk["attack_ref"])):
            if not source_ok:
                records.append({"label": "memory_" + cond, "state": "blocked_source",
                                "task_id": tgt["task_id"]})
                continue
            mem = run_root / "memory" / cond
            shutil.copytree(mem_src, mem)
            records.append(run_episode(run_root, "memory_" + cond, V20MEM / tgt["task_ref"],
                                       defense=defense,
                                       attack_path=(V20MEM / attack_ref) if attack_ref else None,
                                       attack_root=V20MEM, memory_root=mem,
                                       model_name=args.model, dry_run=False))
    else:
        records.append({"label": "memory_source", "task_id": src["task_id"], "dry_run": True})

    live = [r for r in records if not r.get("dry_run") and "status" in r]
    normals = [r for r in live if r["label"].startswith(("normal_clean", "memory_clean", "memory_source"))]
    attacks = [r for r in live if r.get("security")]
    turns = [r["turns"] for r in live]
    summary = {
        "episodes": len(live),
        "invalid_action": sum(r["status"] == "invalid_action" for r in live),
        "invalid_action_rate": (sum(r["status"] == "invalid_action" for r in live) / len(live)) if live else None,
        "completed": sum(r["status"] == "completed" for r in live),
        "turns_mean": round(statistics.mean(turns), 2) if turns else None,
        "turns_median": statistics.median(turns) if turns else None,
        "turns_range": [min(turns), max(turns)] if turns else None,
        "total_parse_failures": sum(r["parse_failures"] for r in live),
        "clean_utility_passes": sum(r["synthetic_utility_pass"] is True for r in normals),
        "clean_utility_n": len(normals),
        "attacks_triggered": sum(bool(r["security"] and r["security"]["triggered"]) for r in attacks),
        "attacks_exposed": sum(bool(r["security"] and r["security"]["exposed"]) for r in attacks),
        "attacks_success": sum(bool(r["security"] and r["security"]["attack_success"]) for r in attacks),
        "attacks_n": len(attacks),
    }
    report = {"format": "medsec-v20-diag-report", "run_id": run_id, "model": args.model,
              "dry_run": args.dry_run, "summary": summary, "records": records}
    if not args.dry_run:
        _write(run_root / "report.json", report)
    print(json.dumps({"run_id": run_id, "root": str(run_root), "summary": summary}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
