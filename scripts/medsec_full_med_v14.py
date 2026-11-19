"""Resumable DeepSeek Flash Med synthetic full run with shared clean baselines."""
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
from src.medsec.v08.cli import _run_extension
from src.medsec.v08.scoring import recompute as replay_v08

FORMAT = "medsec-med-full-v14"
SUITES = (ROOT / "data/medsec/v10_expanded_seed0", ROOT / "data/medsec/v11_memory_contract_v2")
MODEL = "deepseek-flash"
DEFENSES = ("none", "scope")


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
    for suite in SUITES:
        manifest_path = suite / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        inputs[str(manifest_path)] = digest(manifest_path)
        for row in manifest["tasks"]:
            if row.get("benchmark_id", "medagentbench_ext") != "medagentbench_ext":
                continue
            path = (suite / row["task_ref"]).resolve()
            task = json.loads(path.read_text())
            if task["task_id"] != row["task_id"] or task["task_id"] in tasks:
                raise ValueError("duplicate or mismatched Med task")
            tasks[task["task_id"]] = {"task_id": task["task_id"], "path": str(path),
                                      "role": row.get("role", "source" if task["family"] == "memory_handoff_source" else "target"),
                                      "memory_scope": task.get("memory_scope"),
                                      "source_task_id": task.get("source_task_id") if task.get("memory_scope") else None,
                                      "scenario_group_id": task.get("scenario_group_id", "")}
            inputs[str(path)] = digest(path)
        for row in manifest["attacks"]:
            if row["task_id"] not in tasks:
                continue
            path = (suite / row["attack_ref"]).resolve()
            attack = json.loads(path.read_text())
            payload = (suite / attack["payload_ref"]).resolve()
            if not payload.is_relative_to(suite.resolve()) or digest(payload) != attack["payload_sha256"]:
                raise ValueError("payload escapes suite or changed")
            if attack["attack_id"] != row["attack_id"]:
                raise ValueError("attack id mismatch")
            attacks.append({"attack_id": attack["attack_id"], "task_id": attack["task_id"],
                            "path": str(path), "root": str(suite.resolve()),
                            "surface": attack["surface"], "goal_id": attack["goal_id"],
                            "scenario_group_id": attack.get("scenario_group_id", "")})
            inputs[str(path)] = digest(path)
            inputs[str(payload)] = digest(payload)
    if len(tasks) != 126 or len(attacks) != 924:
        raise ValueError(f"unexpected Med catalog size: {len(tasks)} tasks, {len(attacks)} attacks")
    sources = {tid: row for tid, row in tasks.items() if row["role"] == "source"}
    if len(sources) != 39:
        raise ValueError("expected 39 memory source tasks")
    source_by_scope = {}
    for tid, row in sources.items():
        scope = row["memory_scope"]
        key = (scope["patient_id"], scope["project_id"])
        if key in source_by_scope:
            raise ValueError("ambiguous memory source scope")
        source_by_scope[key] = tid
    for row in tasks.values():
        if row["role"] == "source" or not row["memory_scope"]:
            continue
        scope = row["memory_scope"]
        source_id = row["source_task_id"]
        if source_id not in sources:
            source_id = source_by_scope.get((scope["patient_id"], scope["project_id"]))
        if source_id not in sources:
            raise ValueError("memory target without source: " + row["task_id"])
        row["source_task_id"] = source_id
    if len({a["attack_id"] for a in attacks}) != len(attacks):
        raise ValueError("duplicate attacks")
    return tasks, sorted(attacks, key=lambda a: a["attack_id"]), inputs


def make_plan(smoke: bool = False, output_root: Path = ROOT / "results/medsec") -> Path:
    tasks, attacks, inputs = catalog()
    if smoke:
        surfaces = sorted({a["surface"] for a in attacks})
        selected = [next(a for a in attacks if a["surface"] == surface) for surface in surfaces]
        selected.append(next(a for a in attacks if a["attack_id"].startswith("v11-") and a not in selected))
        attacks = sorted({a["attack_id"]: a for a in selected}.values(), key=lambda a: a["attack_id"])
    target_ids = {a["task_id"] for a in attacks}
    source_ids = {tasks[tid]["source_task_id"] for tid in target_ids if tasks[tid]["source_task_id"]}
    plan = {"format": FORMAT, "model": MODEL, "smoke": smoke,
            "tasks": {tid: tasks[tid] for tid in sorted(target_ids | source_ids)},
            "attacks": attacks, "inputs": inputs,
            "source_task_ids": sorted(source_ids), "target_task_ids": sorted(target_ids),
            "conditions": ["clean_none", "attack_none", "clean_scope", "attack_scope"],
            "baseline_policy": "one clean baseline per target task and defense"}
    run_id = datetime.now(timezone.utc).strftime("v14-med-%Y%m%dT%H%M%SZ-") + uuid.uuid4().hex[:8]
    root = output_root.resolve() / run_id
    root.mkdir(parents=True, exist_ok=False)
    write_new(root / "plan.json", plan)
    write_new(root / "manifest.json", {"format": FORMAT, "run_id": run_id,
                                       "plan_sha256": digest(root / "plan.json"),
                                       "runner_sha256": digest(Path(__file__))})
    print(json.dumps({"run_id": run_id, "root": str(root), "smoke": smoke,
                      "sources": len(source_ids), "targets": len(target_ids),
                      "attacks": len(attacks),
                      "planned_trials": len(source_ids) + 2 * len(target_ids) + 2 * len(attacks)}), flush=True)
    return root


def load_plan(root: Path) -> dict:
    manifest = json.loads((root / "manifest.json").read_text())
    if manifest["format"] != FORMAT or digest(root / "plan.json") != manifest["plan_sha256"]:
        raise ValueError("plan changed")
    if digest(Path(__file__)) != manifest["runner_sha256"]:
        raise ValueError("runner changed; make a new plan/version")
    plan = json.loads((root / "plan.json").read_text())
    for path, expected in plan["inputs"].items():
        if digest(Path(path)) != expected:
            raise ValueError("input changed: " + path)
    return plan


def _job_file(root: Path, identifier: str) -> Path:
    return root / "jobs" / (identifier + ".json")


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
            record = {"job_id": identifier, "kind": kind, "condition": condition,
                      "task_id": task_id, "attack_id": attack_id or None,
                      "state": "blocked_source", "source_task_id": task["source_task_id"]}
            write_new(job_path, record)
            return record
        source_seed = root / "seeds" / source_identifier
        seed = root / "memory_copies" / identifier
        if seed.exists():
            raise ValueError("orphaned condition memory requires manual review: " + identifier)
        shutil.copytree(source_seed, seed)
    try:
        metric = _run_extension(Path(task["path"]), "deepseek", MODEL,
                                Path(attack["path"]) if attack else None,
                                Path(attack["root"]) if attack else ROOT,
                                defense, root / "runs", seed)
        record = {"job_id": identifier, "kind": kind, "condition": condition,
                  "task_id": task_id, "attack_id": attack_id or None,
                  "run_dir": str(root / "runs" / metric["run_id"]),
                  "state": "complete", "metric": metric,
                  "memory_tree_sha256": _tree_digest(seed) if seed else None}
    except Exception as exc:
        record = {"job_id": identifier, "kind": kind, "condition": condition,
                  "task_id": task_id, "attack_id": attack_id or None,
                  "state": "error", "error_type": type(exc).__name__, "error_message": str(exc)[:500]}
    write_new(job_path, record)
    return record


def _tree_digest(root: Path) -> str:
    rows = [(str(p.relative_to(root)), digest(p)) for p in sorted(root.rglob("*")) if p.is_file()]
    return sha(json.dumps(rows, separators=(",", ":")).encode())


def run(root: Path, workers: int = 4) -> dict:
    root = root.resolve()
    plan = load_plan(root)
    (root / "runs").mkdir(exist_ok=True)
    (root / "jobs").mkdir(exist_ok=True)
    (root / "seeds").mkdir(exist_ok=True)
    (root / "memory_copies").mkdir(exist_ok=True)
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
                    print(json.dumps({"run_id": root.name, "stage": stage_name,
                                      "done": done, "total": len(jobs), "errors": errors,
                                      "blocked": blocked}), flush=True)
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
    expected += [("clean", tid, "clean_" + defense, "") for tid in plan["target_task_ids"] for defense in DEFENSES]
    expected += [("attack", a["task_id"], "attack_" + defense, a["attack_id"])
                 for a in plan["attacks"] for defense in DEFENSES]
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
            metric = replay_v08(Path(row["run_dir"]))
            if metric != row["metric"]:
                raise ValueError("job metric differs from native replay")
            if row["memory_tree_sha256"]:
                memory_dir = (root / "seeds" / identifier if kind == "source" else
                              root / "memory_copies" / identifier)
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
        summaries.append({"condition": condition, "surface": surface,
                          "planned": len(rows), "clean_capable": sum(r["clean_pass"] for r in rows),
                          "eligible": len(eligible), "unknown_or_blocked": sum(not r["valid"] for r in rows),
                          "triggered": sum(r["triggered"] for r in rows), "exposed": sum(r["exposed"] for r in rows),
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
    result = {"format": FORMAT, "run_id": root.name, "benchmark_id": "medagentbench_ext",
              "model": MODEL, "smoke": plan["smoke"], "planned_attacks": len(plan["attacks"]),
              "planned_trials": len(expected), "recorded_trials": len(records), "missing_jobs": missing,
              "source_tasks": len(plan["source_task_ids"]), "source_passes": source_pass,
              "utility": utility, "attack_summary": summaries,
              "attack_records": [row for rows in groups.values() for row in rows],
              "complete": not missing and all(r["state"] == "complete" for r in records),
              "limitations": ["synthetic_development_candidates", "not_official_medagentbench",
                              "direct_memory_edits_not_induced_writes", "single_sample_per_attack_condition"]}
    report_path = root / "report.json"
    if report_path.exists() and json.loads(report_path.read_text()) != result:
        raise ValueError("saved report differs from recomputation")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    plan_parser = sub.add_parser("plan")
    plan_parser.add_argument("--smoke", action="store_true")
    plan_parser.add_argument("--output-root", type=Path, default=ROOT / "results/medsec")
    run_parser = sub.add_parser("run")
    run_parser.add_argument("run_dir", type=Path)
    run_parser.add_argument("--workers", type=int, default=4)
    score_parser = sub.add_parser("score")
    score_parser.add_argument("run_dir", type=Path)
    args = parser.parse_args()
    if args.command == "plan":
        make_plan(args.smoke, args.output_root)
    elif args.command == "run":
        report = run(args.run_dir, args.workers)
        print(json.dumps({"run_id": report["run_id"], "complete": report["complete"],
                          "planned_trials": report["planned_trials"], "recorded_trials": report["recorded_trials"],
                          "source_passes": report["source_passes"], "utility": report["utility"],
                          "attack_summary": report["attack_summary"]}), flush=True)
    else:
        print(json.dumps(recompute(args.run_dir), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
