"""Build and run the synthetic two-substrate pilot without touching frozen runs."""
from __future__ import annotations

import argparse
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .engine import DeepSeekModel, ReferenceModel, SYSTEM_PROMPT_VERSION, run_episode
from .harbor import export_health_tasks
from .schema import payload_text, read_json, sha256, validate_attack, validate_task
from .scoring import recompute, summarize
from .suite import create_suite

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_SUITE = PROJECT_ROOT / "data/medsec/v07_2_pilot"


def _load(suite: Path, attack_ref: str) -> tuple[dict, dict, str, str]:
    suite = suite.resolve()
    attack_path = (suite / attack_ref).resolve()
    if not attack_path.is_relative_to(suite) or not attack_path.is_file():
        raise ValueError("attack must be inside suite")
    attack = read_json(attack_path)
    task_ref = f"tasks/{attack['task_id']}.json"
    task_path = suite / task_ref
    task = read_json(task_path)
    validate_task(task)
    validate_attack(attack, task, suite)
    return task, attack, task_ref, attack_path.relative_to(suite).as_posix()


def _run(suite: Path, task: dict, task_ref: str, attack: dict | None,
         attack_ref: str | None, agent: str, model_name: str,
         defense: str, runs_root: Path) -> dict:
    now = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_id = f"v07-{now}-{uuid.uuid4().hex[:12]}"
    run_dir = runs_root / run_id
    model = ReferenceModel(task) if agent == "reference" else DeepSeekModel(model_name)
    payload = payload_text(attack, suite) if attack else None
    outcome, events = run_episode(task, model, run_id, attack=attack, payload=payload, defense_name=defense)
    run_dir.mkdir(parents=True, exist_ok=False)
    events_path = run_dir / "events.jsonl"
    events_path.write_text("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in events))
    outcome_path = run_dir / "outcome.json"
    outcome_path.write_text(json.dumps(outcome, ensure_ascii=False, indent=2) + "\n")
    manifest = {"format": "medsec-v0.7", "run_id": run_id, "suite_root": str(suite.resolve()),
                "task_ref": task_ref, "task_sha256": sha256((suite / task_ref).read_bytes()),
                "attack_ref": attack_ref, "attack_sha256": sha256((suite / attack_ref).read_bytes()) if attack_ref else None,
                "model": model_name if agent == "deepseek" else "reference-smoke",
                "agent": agent, "defense": defense, "system_prompt_version": SYSTEM_PROMPT_VERSION,
                "events_sha256": sha256(events_path.read_bytes()),
                "outcome_sha256": sha256(outcome_path.read_bytes())}
    (run_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    return recompute(run_dir)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    make = sub.add_parser("init-suite")
    make.add_argument("--out", type=Path, default=DEFAULT_SUITE)
    check = sub.add_parser("validate-suite")
    check.add_argument("--suite", type=Path, default=DEFAULT_SUITE)
    harbor = sub.add_parser("export-harbor")
    harbor.add_argument("--suite", type=Path, default=DEFAULT_SUITE)
    harbor.add_argument("--out", type=Path, default=PROJECT_ROOT / "data/medsec/v07_2_harbor")
    run = sub.add_parser("run-pair")
    run.add_argument("--suite", type=Path, default=DEFAULT_SUITE)
    run.add_argument("--attack", required=True, help="attack path relative to suite")
    run.add_argument("--agent", choices=["reference", "deepseek"], default="reference")
    run.add_argument("--model", default="deepseek-flash")
    run.add_argument("--runs-root", type=Path, default=PROJECT_ROOT / "results/medsec")
    report = sub.add_parser("report")
    report.add_argument("run_dirs", nargs="+", type=Path)
    args = parser.parse_args()
    if args.command == "init-suite":
        print(json.dumps(create_suite(args.out), ensure_ascii=False, indent=2))
    elif args.command == "export-harbor":
        result = export_health_tasks(args.suite, args.out)
        print(json.dumps({"format": result["format"], "task_count": len(result["tasks"])}))
    elif args.command == "validate-suite":
        suite = args.suite.resolve()
        manifest = read_json(suite / "manifest.json")
        for ref in manifest["tasks"]:
            validate_task(read_json(suite / ref))
        for ref in manifest["attacks"]:
            attack = read_json(suite / ref)
            validate_attack(attack, read_json(suite / f"tasks/{attack['task_id']}.json"), suite)
        if len(manifest["tasks"]) != manifest["task_count"] or len(manifest["attacks"]) != manifest["attack_count"]:
            raise ValueError("suite manifest count mismatch")
        print(json.dumps({"status": "valid", "task_count": manifest["task_count"],
                          "attack_count": manifest["attack_count"]}, ensure_ascii=False))
    elif args.command == "run-pair":
        task, attack, task_ref, attack_ref = _load(args.suite, args.attack)
        metrics = []
        for defense in ("none", "scope"):
            metrics.append(_run(args.suite, task, task_ref, None, None,
                                args.agent, args.model, defense, args.runs_root))
            metrics.append(_run(args.suite, task, task_ref, attack, attack_ref,
                                args.agent, args.model, defense, args.runs_root))
        print(json.dumps({"pair": attack["attack_id"], "metrics": metrics,
                          "summary": summarize(metrics)}, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(summarize([recompute(p) for p in args.run_dirs]), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
