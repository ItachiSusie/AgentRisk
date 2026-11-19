"""Native adapter validation, MedAgentBench runs, and HealthAgentBench export."""
from __future__ import annotations

import argparse
import json
import re
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .adapters.healthagentbench import HealthAgentBenchAdapter
from .adapters.medagentbench import MedAgentBenchAdapter
from .attack import load_attack
from .contracts import Events, LOCK, ROOT, code_hashes, load_lock, sha256, tree_hash
from .models import DeepSeekTextModel
from .episode import run_extension
from .scoring import aggregate, recompute


def _reference_model(task: dict):
    def respond(messages):
        if task["id"].startswith("task1_"):
            return "FINISH(" + json.dumps(task["sol"]) + ")"
        if task["id"].startswith("task3_"):
            if any("POST request accepted" in m["content"] for m in messages):
                return "FINISH([])"
            body = {"resourceType": "Observation", "category": [{"coding": [{
                "system": "http://hl7.org/fhir/observation-category", "code": "vital-signs",
                "display": "Vital Signs"}]}], "code": {"text": "BP"},
                "effectiveDateTime": "2023-11-13T10:15:00+00:00", "status": "final",
                "valueString": "118/77 mmHg", "subject": {"reference": "Patient/" + task["eval_MRN"]}}
            return "POST http://127.0.0.1:8080/fhir/Observation\n" + json.dumps(body)
        raise ValueError("reference smoke agent only implements task1 and task3")
    return respond


def _reference_live_model(task: dict):
    """Minimal task1 reference that derives its answer from a real FHIR GET."""
    if not task["id"].startswith("task1_"):
        return _reference_model(task)
    match = re.search(r"name ([A-Za-z-]+) ([A-Za-z-]+) and DOB of (\d{4}-\d{2}-\d{2})",
                      task["instruction"])
    if not match:
        raise ValueError("unsupported task1 instruction format for live reference")
    given, family, dob = match.groups()

    def respond(messages):
        feedback = messages[-1]["content"]
        if not feedback.startswith("Here is the response from the GET request:\n"):
            return ("GET http://127.0.0.1:8080/fhir/Patient?family=" + family +
                    "&given=" + given + "&birthdate=" + dob)
        body = feedback.split("\n", 1)[1].split(". Please call FINISH", 1)[0]
        bundle = json.loads(body)
        entries = bundle.get("entry", [])
        mrn = entries[0]["resource"]["id"] if entries else "Patient not found"
        return "FINISH(" + json.dumps([mrn]) + ")"

    return respond


def _run_med(adapter: MedAgentBenchAdapter, task_id: str, agent: str, model_name: str,
             attack_path: Path | None, attack_root: Path, defense: str, output_root: Path) -> dict:
    task = adapter.load_task(task_id)
    sample = payload = None
    if attack_path:
        sample, payload = load_attack(attack_path, attack_root, Events("preflight", "medagentbench_official", task_id))
        if sample.get("task_id") != task_id:
            raise ValueError("attack/task mismatch")
    model = (_reference_model(task) if agent == "reference" else
             _reference_live_model(task) if agent == "reference-live" else
             DeepSeekTextModel(model_name))
    run_id = datetime.now(timezone.utc).strftime("v08-%Y%m%dT%H%M%SZ-") + uuid.uuid4().hex[:12]
    run = adapter.run(task_id, model, run_id, attack=sample, payload=payload, defense_policy=defense)
    utility = adapter.grade_utility(run)
    output_dir = output_root / run_id
    output_dir.mkdir(parents=True, exist_ok=False)
    events_path = output_dir / "events.jsonl"
    events_path.write_text("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in run["events"]))
    outcome_path = output_dir / "outcome.json"
    outcome_path.write_text(json.dumps({"status": run["status"], "result": run["result"],
                                        "official_utility_pass": utility}, ensure_ascii=False, indent=2) + "\n")
    manifest = {"format": "medsec-v08", "run_id": run_id, "benchmark_id": "medagentbench_official",
                "task_id": task_id, "model": ("reference-smoke" if agent == "reference" else
                                               "reference-live" if agent == "reference-live" else model_name),
                "defense": defense, "upstream_lock_sha256": sha256(LOCK.read_bytes()),
                "code_sha256": code_hashes(), "task_sha256": sha256(json.dumps(task, sort_keys=True)),
                "events_sha256": sha256(events_path.read_bytes()),
                "outcome_sha256": sha256(outcome_path.read_bytes()),
                "attack_ref": str(attack_path.resolve()) if attack_path else None,
                "attack_root": str(attack_root.resolve()) if attack_path else None,
                "attack_sha256": sha256(attack_path.read_bytes()) if attack_path else None,
                "grader_sha256": sha256(adapter.grader.read_bytes()) if adapter.grader else None}
    (output_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    return recompute(output_dir)


def _run_extension(task_path: Path, agent: str, model_name: str, attack_path: Path | None,
                   attack_root: Path, defense: str, output_root: Path,
                   memory_root: Path | None = None) -> dict:
    task = json.loads(task_path.read_text())
    if task["benchmark_id"] != "medagentbench_ext":
        raise ValueError("synthetic Med extension task required")
    sample = payload = None
    if attack_path:
        sample, payload = load_attack(attack_path, attack_root, Events("preflight", "medagentbench_ext", task["task_id"]))
        if sample.get("task_id") != task["task_id"]:
            raise ValueError("attack/task mismatch")
    if agent == "reference":
        if task["family"] == "memory_handoff_target":
            steps = [{"tool": "search_memory", "args": task["memory_scope"]},
                     {"tool": "finish", "args": task["required_outcome"]["args"]}]
        elif task["required_outcome"]["tool"] in {"write_resource", "write_memory"}:
            steps = [{"tool": "read_record", "args": {"patient_id": task["patient_id"]}},
                     task["required_outcome"], {"tool": "finish", "args": {"answer": "done"}}]
        else:
            steps = [{"tool": "read_record", "args": {"patient_id": task["patient_id"]}},
                     {"tool": "finish", "args": task["required_outcome"]["args"]}]
        count = 0

        def model(_messages):
            nonlocal count
            action = steps[min(count, len(steps) - 1)]
            count += 1
            return json.dumps(action)
    else:
        model = DeepSeekTextModel(model_name, json_mode=True)
    run_id = datetime.now(timezone.utc).strftime("v08-%Y%m%dT%H%M%SZ-") + uuid.uuid4().hex[:12]
    output_dir = output_root / run_id
    output_dir.mkdir(parents=True, exist_ok=False)
    result = run_extension(task, model, run_id, workspace=output_dir / "workspace",
                           attack=sample, payload=payload, defense_policy=defense,
                           memory_root=memory_root)
    events_path = output_dir / "events.jsonl"
    events_path.write_text("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in result["events"]))
    outcome_path = output_dir / "outcome.json"
    outcome_path.write_text(json.dumps({"status": result["status"], "result": result["result"],
                                        "synthetic_utility_pass": result["synthetic_utility_pass"],
                                        "state_fingerprint": result["state_fingerprint"]}, indent=2) + "\n")
    manifest = {"format": "medsec-v08", "run_id": run_id, "benchmark_id": "medagentbench_ext",
                "task_id": task["task_id"], "model": "reference-smoke" if agent == "reference" else model_name,
                "defense": defense, "upstream_lock_sha256": sha256(LOCK.read_bytes()),
                "code_sha256": code_hashes(), "task_sha256": sha256(task_path.read_bytes()),
                "task_ref": str(task_path.resolve()),
                "events_sha256": sha256(events_path.read_bytes()), "outcome_sha256": sha256(outcome_path.read_bytes()),
                "attack_ref": str(attack_path.resolve()) if attack_path else None,
                "attack_root": str(attack_root.resolve()) if attack_path else None,
                "attack_sha256": sha256(attack_path.read_bytes()) if attack_path else None,
                "grader_sha256": None, "utility_source": "synthetic_hidden_state_v08"}
    if memory_root:
        manifest["memory_root"] = str(memory_root.resolve())
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return recompute(output_dir)


def _pair(args) -> dict:
    if not args.attack:
        raise ValueError("pair requires an attack sample")
    adapter = MedAgentBenchAdapter(args.upstream_source, args.grader) if args.benchmark == "official" else None
    pair_id = datetime.now(timezone.utc).strftime("v08-pair-%Y%m%dT%H%M%SZ-") + uuid.uuid4().hex[:12]
    pair_dir = args.output_root / pair_id
    if args.memory_root:
        pair_dir.mkdir(parents=True, exist_ok=False)
    rows = []
    for attack_enabled, defense in ((False, "none"), (True, "none"),
                                    (False, "scope"), (True, "scope")):
        attack_path = args.attack if attack_enabled else None
        if adapter:
            row = _run_med(adapter, args.task, args.agent, args.model, attack_path,
                           args.attack_root, defense, args.output_root)
        else:
            condition = ("attack" if attack_enabled else "clean") + "_" + defense
            memory_root = None
            if args.memory_root:
                memory_root = pair_dir / condition / "memory"
                shutil.copytree(args.memory_root, memory_root)
            row = _run_extension(Path(args.task), args.agent, args.model, attack_path,
                                 args.attack_root, defense, args.output_root, memory_root)
        rows.append({"condition": ("attack" if attack_enabled else "clean") + "_" + defense, **row})
    report = {"format": "medsec-v08-pair", "pair_id": pair_id, "benchmark": args.benchmark,
              "task": args.task, "attack": str(args.attack), "conditions": rows}
    pair_path = args.output_root / (pair_id + ".json")
    pair_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    return report


def _import_health(events_file: Path, result_file: Path, task_dir: Path,
                   output_root: Path, attack_path: Path | None, attack_root: Path) -> dict:
    events = [json.loads(line) for line in events_file.read_text().splitlines() if line]
    if not events or any(e["run_id"] != events[0]["run_id"] for e in events):
        raise ValueError("Harbor events missing a unique run ID")
    source_event_run_id = events[0]["run_id"]
    if not isinstance(source_event_run_id, str) or not source_event_run_id:
        raise ValueError("Harbor event run ID missing")
    bridge_hash = next((e.get("bridge_code_sha256") for e in events
                        if e["kind"] == "episode_started"), None)
    current_bridge_hash = code_hashes()["harbor_agent.py"]
    if bridge_hash != current_bridge_hash:
        raise ValueError("Harbor bridge code hash missing or changed; rerun the trial")
    run_id = "v08-health-" + uuid.uuid4().hex
    official = json.loads(result_file.read_text())
    if official.get("task_name") and official["task_name"] != task_dir.name:
        raise ValueError("Harbor result/task mismatch")
    rewards = (official.get("verifier_result") or {}).get("rewards") or {}
    reward = rewards.get("reward")
    status = ("environment_error" if official.get("exception_info") else
              "verifier_missing" if reward is None else "completed")
    task_toml = task_dir / "task.toml"
    if not task_toml.is_file():
        raise ValueError("task.toml missing")
    sample = None
    if attack_path:
        sample, _ = load_attack(attack_path, attack_root, Events("preflight", "healthagentbench_harbor", run_id))
        if sample.get("task_id") != task_dir.name:
            raise ValueError("attack/task mismatch")
    output_dir = output_root / run_id
    output_dir.mkdir(parents=True, exist_ok=False)
    out_events = output_dir / "events.jsonl"
    out_events.write_bytes(events_file.read_bytes())
    outcome = {"status": status, "official_utility_pass": reward == 1 if reward is not None else None,
               "official_reward": reward, "official_source": "harbor-0.23.0-verifier_result"}
    outcome_path = output_dir / "outcome.json"
    outcome_path.write_text(json.dumps(outcome, indent=2) + "\n")
    manifest = {"format": "medsec-v08", "run_id": run_id, "benchmark_id": "healthagentbench_harbor",
                "source_event_run_id": source_event_run_id,
                "task_id": task_dir.name,
                "model": (official.get("agent_info") or {}).get("model_info", {}).get("name")
                         if (official.get("agent_info") or {}).get("model_info") else None,
                "defense": next((e["defense_policy"] for e in events if e["kind"] == "episode_started"), "unknown"),
                "upstream_lock_sha256": sha256(LOCK.read_bytes()),
                "code_sha256": code_hashes(), "task_sha256": tree_hash(task_dir),
                "task_ref": str(task_dir.resolve()), "task_hash_kind": "tree",
                "events_sha256": sha256(out_events.read_bytes()),
                "outcome_sha256": sha256(outcome_path.read_bytes()),
                "official_result_ref": str(result_file.resolve()),
                "official_result_sha256": sha256(result_file.read_bytes()),
                "attack_ref": str(attack_path.resolve()) if attack_path else None,
                "attack_root": str(attack_root.resolve()) if attack_path else None,
                "attack_sha256": sha256(attack_path.read_bytes()) if attack_path else None}
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return recompute(output_dir)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    validate = sub.add_parser("validate-lock")
    validate.add_argument("--med-source", type=Path)
    validate.add_argument("--health-root", type=Path)
    validate.add_argument("--grader", type=Path, default=ROOT / "data/medsec/private/refsol.py")
    med = sub.add_parser("med-run")
    med.add_argument("--upstream-source", type=Path, required=True)
    med.add_argument("--grader", type=Path, default=ROOT / "data/medsec/private/refsol.py")
    med.add_argument("--task-id", required=True)
    med.add_argument("--agent", choices=["reference", "reference-live", "deepseek"], default="reference")
    med.add_argument("--model", default="deepseek-flash")
    med.add_argument("--attack", type=Path)
    med.add_argument("--attack-root", type=Path, default=ROOT / "data/medsec/v08")
    med.add_argument("--defense", choices=["none", "scope"], default="none")
    med.add_argument("--output-root", type=Path, default=ROOT / "results/medsec")
    extension = sub.add_parser("extension-run")
    extension.add_argument("--task", type=Path, required=True)
    extension.add_argument("--agent", choices=["reference", "deepseek"], default="reference")
    extension.add_argument("--model", default="deepseek-flash")
    extension.add_argument("--attack", type=Path)
    extension.add_argument("--attack-root", type=Path, default=ROOT / "data/medsec/v08")
    extension.add_argument("--defense", choices=["none", "scope"], default="none")
    extension.add_argument("--output-root", type=Path, default=ROOT / "results/medsec")
    extension.add_argument("--memory-root", type=Path,
                           help="Explicit shared store for a source/target episode; omit for isolation")
    pair = sub.add_parser("pair")
    pair.add_argument("--benchmark", choices=["official", "extension"], required=True)
    pair.add_argument("--task", required=True, help="Official task ID or extension task JSON path")
    pair.add_argument("--upstream-source", type=Path)
    pair.add_argument("--grader", type=Path, default=ROOT / "data/medsec/private/refsol.py")
    pair.add_argument("--agent", choices=["reference", "reference-live", "deepseek"], default="reference")
    pair.add_argument("--model", default="deepseek-flash")
    pair.add_argument("--attack", type=Path, required=True)
    pair.add_argument("--attack-root", type=Path, default=ROOT / "data/medsec/v08")
    pair.add_argument("--output-root", type=Path, default=ROOT / "results/medsec")
    pair.add_argument("--memory-root", type=Path,
                      help="Seeded source-task memory copied separately into all four conditions")
    health_import = sub.add_parser("health-import")
    health_import.add_argument("--events", type=Path, required=True,
                               help="Harbor agent's medsec-events.jsonl")
    health_import.add_argument("--result", type=Path, required=True,
                               help="Harbor trial result.json with verifier_result.rewards")
    health_import.add_argument("--task-dir", type=Path, required=True)
    health_import.add_argument("--attack", type=Path)
    health_import.add_argument("--attack-root", type=Path, default=ROOT / "data/medsec/v08")
    health_import.add_argument("--output-root", type=Path, default=ROOT / "results/medsec")
    health = sub.add_parser("health-inspect")
    health.add_argument("--upstream-root", type=Path, required=True)
    health.add_argument("--task", default="ehr_compositional_qa_direct")
    export = sub.add_parser("health-export")
    export.add_argument("--upstream-root", type=Path, required=True)
    export.add_argument("--suite", type=Path, default=ROOT / "data/medsec/v07_2_pilot")
    export.add_argument("--out", type=Path, default=ROOT / "data/medsec/v08/harbor_synthetic")
    score = sub.add_parser("score")
    score.add_argument("run_dir", type=Path)
    report = sub.add_parser("report")
    report.add_argument("run_dirs", type=Path, nargs="+")
    report.add_argument("--out", type=Path)
    args = parser.parse_args()
    if args.command == "validate-lock":
        lock = load_lock()
        if args.med_source:
            from .contracts import check_file
            check_file(args.med_source, lock["medagentbench"]["loop_sha256"])
        if args.grader.is_file():
            from .contracts import check_file
            check_file(args.grader, lock["medagentbench"]["grader_sha256"])
        if args.health_root:
            HealthAgentBenchAdapter(args.health_root)
        print(json.dumps({"valid": True, "med_tasks": 300, "med_tools": 9,
                          "health_pinned": bool(args.health_root)}, ensure_ascii=False))
    elif args.command == "med-run":
        adapter = MedAgentBenchAdapter(args.upstream_source, args.grader)
        result = _run_med(adapter, args.task_id, args.agent, args.model,
                          args.attack, args.attack_root, args.defense, args.output_root)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.command == "extension-run":
        result = _run_extension(args.task, args.agent, args.model, args.attack,
                                args.attack_root, args.defense, args.output_root, args.memory_root)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.command == "pair":
        if args.benchmark == "official" and args.upstream_source is None:
            parser.error("--upstream-source is required for official pairs")
        print(json.dumps(_pair(args), ensure_ascii=False, indent=2))
    elif args.command == "health-import":
        print(json.dumps(_import_health(args.events, args.result, args.task_dir,
                                        args.output_root, args.attack, args.attack_root),
                         ensure_ascii=False, indent=2))
    elif args.command == "health-inspect":
        task = HealthAgentBenchAdapter(args.upstream_root).load_task(args.task)
        print(json.dumps({"task_name": task["task_name"],
                          "instruction_sha256": task["instruction_sha256"],
                          "task_toml_sha256": task["task_toml_sha256"],
                          "task_tree_sha256": task["task_tree_sha256"],
                          "artifacts": task["config"].get("artifacts")}, ensure_ascii=False, indent=2))
    elif args.command == "health-export":
        result = HealthAgentBenchAdapter(args.upstream_root).export_synthetic(args.suite, args.out)
        print(json.dumps({"format": result["format"], "tasks": len(result["tasks"])}, ensure_ascii=False))
    elif args.command == "report":
        result = aggregate(args.run_dirs)
        if args.out:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            with args.out.open("x") as handle:
                handle.write(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(recompute(args.run_dir), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
