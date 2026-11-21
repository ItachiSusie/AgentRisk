"""Resumable v20 Med full run: fixed executor + judgment-style memory tasks.

Catalog = v10 non-memory Med tasks/attacks (unchanged) + the v20 judgment-memory
set (data/medsec/v20_memory_judgment). Uses the v20 executor (one-action-per-turn
with parse-retry) and v20 scoring. Structure mirrors the frozen v14/v17 runner
but is a separate file so editing it never changes v17's runner hash.

  plan  -> freeze sample + input/code fingerprints into a new run_id dir
  run   -> resumable; skips existing job records, continues missing ones
  score -> recompute the report from saved events (no model calls)

This does NOT launch automatically at scale: run `plan` then `run` explicitly.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import uuid
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.medsec.v20.cli import run_extension_v20
from src.medsec.v20.scoring import recompute as replay_v20, v20_code_hashes

FORMAT = "medsec-med-full-v20"
MODEL = "deepseek-flash"
DEFENSES = ("none", "scope")
V10 = ROOT / "data/medsec/v10_expanded_seed0"
V20MEM = ROOT / "data/medsec/v20_memory_judgment"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def digest(path: Path) -> str:
    return sha(path.read_bytes())


def write_new(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def job_id(kind: str, task_id: str, condition: str = "", attack_id: str = "") -> str:
    return kind + "-" + sha(json.dumps([task_id, condition, attack_id]).encode())[:20]


def catalog() -> tuple[dict, list, dict]:
    tasks, attacks, inputs = {}, [], {}
    # v10 non-memory Med tasks + attacks.
    man10 = json.loads((V10 / "manifest.json").read_text())
    inputs[str((V10 / "manifest.json"))] = digest(V10 / "manifest.json")
    v10_task_bid = {}
    for row in man10["tasks"]:
        path = (V10 / row["task_ref"]).resolve()
        tj = json.loads(path.read_text())
        v10_task_bid[tj["task_id"]] = (tj["benchmark_id"], tj["family"])
        if tj["benchmark_id"] != "medagentbench_ext" or "memory" in tj["family"]:
            continue
        tasks[tj["task_id"]] = {"task_id": tj["task_id"], "path": str(path), "role": "target",
                                "memory_scope": None, "source_task_id": None,
                                "scenario_group_id": tj.get("scenario_group_id", "")}
        inputs[str(path)] = digest(path)
    for row in man10["attacks"]:
        bid = v10_task_bid.get(row["task_id"], ("", ""))
        if bid[0] != "medagentbench_ext" or "memory" in bid[1] or row["surface"] == "memory_store_edit":
            continue
        path = (V10 / row["attack_ref"]).resolve()
        aj = json.loads(path.read_text())
        payload = (V10 / aj["payload_ref"]).resolve()
        if not payload.is_relative_to(V10.resolve()) or digest(payload) != aj["payload_sha256"]:
            raise ValueError("v10 payload escapes suite or changed")
        attacks.append({"attack_id": aj["attack_id"], "task_id": aj["task_id"], "path": str(path),
                        "root": str(V10.resolve()), "surface": aj["surface"], "goal_id": aj["goal_id"],
                        "scenario_group_id": aj.get("scenario_group_id", "")})
        inputs[str(path)] = digest(path)
        inputs[str(payload)] = digest(payload)
    # v20 judgment-memory tasks + attacks.
    man20 = json.loads((V20MEM / "manifest.json").read_text())
    inputs[str((V20MEM / "manifest.json"))] = digest(V20MEM / "manifest.json")
    for row in man20["tasks"]:
        path = (V20MEM / row["task_ref"]).resolve()
        if digest(path) != row["sha256"]:
            raise ValueError("v20 memory task changed: " + row["task_id"])
        tasks[row["task_id"]] = {"task_id": row["task_id"], "path": str(path), "role": row["role"],
                                 "memory_scope": row["memory_scope"], "source_task_id": row.get("source_task_id"),
                                 "scenario_group_id": row["scenario_group_id"]}
        inputs[str(path)] = row["sha256"]
    for row in man20["attacks"]:
        path = (V20MEM / row["attack_ref"]).resolve()
        if digest(path) != row["sha256"]:
            raise ValueError("v20 memory attack changed: " + row["attack_id"])
        payload = (V20MEM / row["payload_ref"]).resolve()
        if digest(payload) != row["payload_sha256"]:
            raise ValueError("v20 memory payload changed: " + row["attack_id"])
        aj = json.loads(path.read_text())
        attacks.append({"attack_id": aj["attack_id"], "task_id": aj["task_id"], "path": str(path),
                        "root": str(V20MEM.resolve()), "surface": aj["surface"], "goal_id": aj["goal_id"],
                        "scenario_group_id": aj.get("scenario_group_id", "")})
        inputs[str(path)] = row["sha256"]
        inputs[str(payload)] = row["payload_sha256"]
    sources = {tid: t for tid, t in tasks.items() if t["role"] == "source"}
    source_by_scope = {}
    for tid, t in sources.items():
        scope = t["memory_scope"]
        key = (scope["patient_id"], scope["project_id"])
        if key in source_by_scope:
            raise ValueError("ambiguous memory source scope")
        source_by_scope[key] = tid
    # Resolve each memory target's source: some suites store a placeholder source_task_id,
    # so fall back to matching the (patient_id, project_id) memory scope, as v14 did.
    for t in tasks.values():
        if t["role"] != "target" or not t["memory_scope"]:
            continue
        source_id = t["source_task_id"]
        if source_id not in sources:
            scope = t["memory_scope"]
            source_id = source_by_scope.get((scope["patient_id"], scope["project_id"]))
        if source_id not in sources:
            raise ValueError("memory target without source: " + t["task_id"])
        t["source_task_id"] = source_id
    nonmem = [t for t in tasks.values() if t["role"] == "target" and not t["memory_scope"]]
    mem_targets = [t for t in tasks.values() if t["role"] == "target" and t["memory_scope"]]
    if len(nonmem) != 48 or len(sources) != 39 or len(mem_targets) != 39:
        raise ValueError(f"unexpected v20 catalog: {len(nonmem)} nonmem, {len(sources)} src, {len(mem_targets)} mem")
    if len(attacks) != 924:
        raise ValueError(f"unexpected attack count: {len(attacks)}")
    if len({a["attack_id"] for a in attacks}) != len(attacks):
        raise ValueError("duplicate attacks")
    return tasks, sorted(attacks, key=lambda a: a["attack_id"]), inputs


def make_plan(smoke: bool, output_root: Path) -> Path:
    tasks, attacks, inputs = catalog()
    if smoke:
        surfaces = sorted({a["surface"] for a in attacks})
        selected = [next(a for a in attacks if a["surface"] == surface) for surface in surfaces]
        # ensure a memory attack is present
        if not any(a["surface"] == "memory_store_edit" for a in selected):
            selected.append(next(a for a in attacks if a["surface"] == "memory_store_edit"))
        attacks = sorted({a["attack_id"]: a for a in selected}.values(), key=lambda a: a["attack_id"])
    target_ids = {a["task_id"] for a in attacks}
    source_ids = {tasks[tid]["source_task_id"] for tid in target_ids if tasks[tid]["source_task_id"]}
    plan = {"format": FORMAT, "model": MODEL, "smoke": smoke,
            "tasks": {tid: tasks[tid] for tid in sorted(target_ids | source_ids)},
            "attacks": attacks, "inputs": inputs,
            "source_task_ids": sorted(source_ids), "target_task_ids": sorted(target_ids),
            "conditions": ["clean_none", "attack_none", "clean_scope", "attack_scope"],
            "baseline_policy": "one clean baseline per target task and defense"}
    run_id = datetime.now(timezone.utc).strftime("v20-med-%Y%m%dT%H%M%SZ-") + uuid.uuid4().hex[:8]
    root = output_root.resolve() / run_id
    root.mkdir(parents=True, exist_ok=False)
    write_new(root / "plan.json", plan)
    write_new(root / "manifest.json", {"format": FORMAT, "run_id": run_id,
                                       "plan_sha256": digest(root / "plan.json"),
                                       "runner_sha256": digest(Path(__file__)),
                                       "v20_code_sha256": v20_code_hashes()})
    print(json.dumps({"run_id": run_id, "root": str(root), "smoke": smoke,
                      "sources": len(source_ids), "targets": len(target_ids), "attacks": len(attacks),
                      "planned_trials": len(source_ids) + 2 * len(target_ids) + 2 * len(attacks)}), flush=True)
    return root


def load_plan(root: Path) -> dict:
    manifest = json.loads((root / "manifest.json").read_text())
    if manifest["format"] != FORMAT or digest(root / "plan.json") != manifest["plan_sha256"]:
        raise ValueError("plan changed")
    if digest(Path(__file__)) != manifest["runner_sha256"]:
        raise ValueError("runner changed; make a new plan/version")
    if v20_code_hashes() != manifest["v20_code_sha256"]:
        raise ValueError("v20 executor code changed; make a new plan/version")
    plan = json.loads((root / "plan.json").read_text())
    for path, expected in plan["inputs"].items():
        if digest(Path(path)) != expected:
            raise ValueError("input changed: " + path)
    return plan


def _job_file(root: Path, identifier: str) -> Path:
    return root / "jobs" / (identifier + ".json")


def _tree_digest(root: Path) -> str:
    rows = [(str(p.relative_to(root)), digest(p)) for p in sorted(root.rglob("*")) if p.is_file()]
    return sha(json.dumps(rows, separators=(",", ":")).encode())


def _execute(root: Path, plan: dict, kind: str, task_id: str, defense: str = "none",
             attack: dict | None = None) -> dict:
    attack_id = attack["attack_id"] if attack else ""
    condition = ("source_none" if kind == "source" else kind + "_" + defense)
    identifier = job_id(kind, task_id, condition, attack_id)
    job_path = _job_file(root, identifier)
    if job_path.exists():
        return json.loads(job_path.read_text())
    task = plan["tasks"][task_id]
    seed = None
    if kind == "source":
        seed = root / "seeds" / identifier
        if seed.exists():
            raise ValueError("orphaned source seed requires manual review: " + identifier)
    elif task["source_task_id"]:
        source_identifier = job_id("source", task["source_task_id"], "source_none")
        source_job = json.loads(_job_file(root, source_identifier).read_text())
        if source_job["state"] != "complete" or source_job["metric"]["synthetic_utility_pass"] is not True:
            record = {"job_id": identifier, "kind": kind, "condition": condition, "task_id": task_id,
                      "attack_id": attack_id or None, "state": "blocked_source",
                      "source_task_id": task["source_task_id"]}
            write_new(job_path, record)
            return record
        source_seed = root / "seeds" / source_identifier
        seed = root / "memory_copies" / identifier
        if seed.exists():
            raise ValueError("orphaned condition memory requires manual review: " + identifier)
        shutil.copytree(source_seed, seed)
    try:
        metric = run_extension_v20(Path(task["path"]), MODEL,
                                   Path(attack["path"]) if attack else None,
                                   Path(attack["root"]) if attack else ROOT,
                                   defense, root / "runs", seed)
        record = {"job_id": identifier, "kind": kind, "condition": condition, "task_id": task_id,
                  "attack_id": attack_id or None, "run_dir": str(root / "runs" / metric["run_id"]),
                  "state": "complete", "metric": metric,
                  "memory_tree_sha256": _tree_digest(seed) if seed else None}
    except Exception as exc:
        record = {"job_id": identifier, "kind": kind, "condition": condition, "task_id": task_id,
                  "attack_id": attack_id or None, "state": "error",
                  "error_type": type(exc).__name__, "error_message": str(exc)[:500]}
    write_new(job_path, record)
    return record


def run(root: Path, workers: int = 4) -> dict:
    root = root.resolve()
    plan = load_plan(root)
    for sub in ("runs", "jobs", "seeds", "memory_copies"):
        (root / sub).mkdir(exist_ok=True)
    if workers < 1 or workers > 32:
        raise ValueError("workers must be 1..32")
    stages = [
        [("source", tid, "none", None) for tid in plan["source_task_ids"]],
        [("clean", tid, defense, None) for tid in plan["target_task_ids"] for defense in DEFENSES],
        [("attack", a["task_id"], defense, a) for a in plan["attacks"] for defense in DEFENSES],
    ]
    for stage_name, jobs in zip(("sources", "baselines", "attacks"), stages):
        done = errors = blocked = 0
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(_execute, root, plan, *job) for job in jobs]
            for future in as_completed(futures):
                row = future.result()
                done += 1
                errors += row["state"] == "error"
                blocked += row["state"] == "blocked_source"
                if done % 25 == 0 or done == len(jobs):
                    print(json.dumps({"run_id": root.name, "stage": stage_name, "done": done,
                                      "total": len(jobs), "errors": errors, "blocked": blocked}), flush=True)
    result = recompute(root)
    report_path = root / "report.json"
    if report_path.exists():
        if json.loads(report_path.read_text()) != result:
            raise ValueError("saved report differs from recomputation")
    elif result["complete"]:
        write_new(report_path, result)
    return result


def recompute(root: Path) -> dict:
    root = root.resolve()
    plan = load_plan(root)
    expected = []
    expected += [("source", tid, "source_none", "") for tid in plan["source_task_ids"]]
    expected += [("clean", tid, "clean_" + d, "") for tid in plan["target_task_ids"] for d in DEFENSES]
    expected += [("attack", a["task_id"], "attack_" + d, a["attack_id"])
                 for a in plan["attacks"] for d in DEFENSES]
    records, missing = [], []
    for kind, task_id, condition, attack_id in expected:
        identifier = job_id(kind, task_id, condition, attack_id)
        path = _job_file(root, identifier)
        if not path.exists():
            missing.append(identifier)
            continue
        row = json.loads(path.read_text())
        if row["job_id"] != identifier:
            raise ValueError("job id mismatch")
        if row["state"] == "complete":
            metric = replay_v20(Path(row["run_dir"]))
            if metric != row["metric"]:
                raise ValueError("job metric differs from v20 replay")
            if row["memory_tree_sha256"]:
                memory_dir = (root / "seeds" / identifier if kind == "source"
                              else root / "memory_copies" / identifier)
                if _tree_digest(memory_dir) != row["memory_tree_sha256"]:
                    raise ValueError("condition memory changed")
        records.append(row)
    sources = [r for r in records if r["kind"] == "source"]
    source_pass = sum(r["state"] == "complete" and r["metric"]["synthetic_utility_pass"] is True for r in sources)
    baseline = {(r["task_id"], r["condition"]): r for r in records if r["kind"] == "clean"}
    attack_index = {a["attack_id"]: a for a in plan["attacks"]}
    groups = defaultdict(list)
    for row in records:
        if row["kind"] != "attack":
            continue
        attack = attack_index[row["attack_id"]]
        clean = baseline.get((row["task_id"], "clean_" + row["condition"].split("_")[-1]))
        clean_pass = bool(clean and clean["state"] == "complete" and clean["metric"]["synthetic_utility_pass"] is True)
        metric = row.get("metric") or {}
        security = metric.get("security") or {}
        valid = row["state"] == "complete" and metric.get("status") not in {"model_error", "environment_error"}
        eligible = clean_pass and valid and security.get("setup_valid") and security.get("installed")
        groups[(row["condition"], attack["surface"])].append({
            "job_id": row["job_id"], "run_id": metric.get("run_id"), "task_id": row["task_id"],
            "attack_id": row["attack_id"], "scenario_group_id": attack["scenario_group_id"],
            "goal_id": attack["goal_id"], "state": row["state"], "status": metric.get("status"),
            "clean_pass": clean_pass, "valid": valid, "eligible": bool(eligible),
            "triggered": bool(security.get("triggered")), "exposed": bool(security.get("exposed")),
            "success": bool(eligible and security.get("attack_success")),
            "attack_utility": metric.get("synthetic_utility_pass") if valid else None})
    summaries = []
    for (condition, surface), rows in sorted(groups.items()):
        eligible = [r for r in rows if r["eligible"]]
        exposed = [r for r in eligible if r["exposed"]]
        successes = sum(r["success"] for r in eligible)
        summaries.append({"condition": condition, "surface": surface, "planned": len(rows),
                          "clean_capable": sum(r["clean_pass"] for r in rows), "eligible": len(eligible),
                          "unknown_or_blocked": sum(not r["valid"] for r in rows),
                          "triggered": sum(r["triggered"] for r in rows),
                          "exposed": sum(r["exposed"] for r in rows),
                          "attack_utility_passes": sum(r["attack_utility"] is True for r in rows),
                          "successes": successes,
                          "asr": successes / len(eligible) if eligible else None,
                          "asr_exposed": successes / len(exposed) if exposed else None})
    utility = []
    for defense in DEFENSES:
        rows = [baseline.get((tid, "clean_" + defense)) for tid in plan["target_task_ids"]]
        attempted = [r for r in rows if r and r["state"] == "complete"]
        passed = sum(r["metric"]["synthetic_utility_pass"] is True for r in attempted)
        utility.append({"defense": defense, "planned_targets": len(rows), "attempted_targets": len(attempted),
                        "passed_targets": passed, "utility": passed / len(attempted) if attempted else None})
    result = {"format": FORMAT, "run_id": root.name, "benchmark_id": "medagentbench_ext", "model": MODEL,
              "smoke": plan["smoke"], "planned_attacks": len(plan["attacks"]), "planned_trials": len(expected),
              "recorded_trials": len(records), "missing_jobs": missing,
              "source_tasks": len(plan["source_task_ids"]), "source_passes": source_pass,
              "utility": utility, "attack_summary": summaries,
              "attack_records": [row for rows in groups.values() for row in rows],
              "complete": not missing and all(r["state"] == "complete" for r in records),
              "limitations": ["synthetic_development_candidates", "not_official_medagentbench",
                              "judgment_memory_tasks_unreviewed", "direct_memory_edits_not_induced_writes",
                              "single_sample_per_attack_condition"]}
    report_path = root / "report.json"
    if report_path.exists() and json.loads(report_path.read_text()) != result:
        raise ValueError("saved report differs from recomputation")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("plan")
    p.add_argument("--smoke", action="store_true")
    p.add_argument("--output-root", type=Path, default=ROOT / "results/medsec")
    r = sub.add_parser("run")
    r.add_argument("run_dir", type=Path)
    r.add_argument("--workers", type=int, default=4)
    s = sub.add_parser("score")
    s.add_argument("run_dir", type=Path)
    args = parser.parse_args()
    if args.command == "plan":
        make_plan(args.smoke, args.output_root)
    elif args.command == "run":
        result = run(args.run_dir, args.workers)
        print(json.dumps({"run_id": result["run_id"], "complete": result["complete"],
                          "planned_trials": result["planned_trials"], "recorded_trials": result["recorded_trials"],
                          "source_passes": result["source_passes"], "utility": result["utility"],
                          "attack_summary": result["attack_summary"]}), flush=True)
    else:
        print(json.dumps(recompute(args.run_dir), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
