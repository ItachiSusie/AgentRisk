"""Recompute MedAgentBench security outcomes from immutable run events."""
from __future__ import annotations

import json
from pathlib import Path

from .judge import judge
from .runtime import digest


def _find_by_hash(root, fingerprint, glob_pattern):
    matches = [p for p in root.glob(glob_pattern) if p.is_file() and digest(p.read_bytes()) == fingerprint]
    if len(matches) != 1:
        raise ValueError(f"expected one artifact with SHA-256 {fingerprint}, found {len(matches)}")
    return matches[0]


def recompute(run_dir, grader=None):
    run_dir = Path(run_dir)
    manifest = json.loads((run_dir / "manifest.json").read_text())
    root = Path(__file__).resolve().parents[2]
    tasks_path = Path(manifest.get("tasks_path") or root / "data/medsec/upstream/test_data_v2.json")
    if digest(tasks_path.read_bytes()) != manifest["tasks_sha256"]:
        raise ValueError("tasks fingerprint changed")
    tools_path = Path(manifest.get("tools_path") or root / "data/medsec/upstream/funcs_v1.json")
    if digest(tools_path.read_bytes()) != manifest["tools_sha256"]:
        raise ValueError("tools fingerprint changed")
    if manifest.get("splits_sha256"):
        if digest(Path(manifest["splits_path"]).read_bytes()) != manifest["splits_sha256"]:
            raise ValueError("splits fingerprint changed")
    tasks = {t["id"]: t for t in json.loads(tasks_path.read_text())}
    task = tasks[manifest["task_id"]]
    events = [json.loads(line) for line in (run_dir / "events.jsonl").read_text().splitlines()]
    answers = [e["answer"] for e in events if e["kind"] == "final_answer"]
    answer = answers[-1] if answers else None
    sample = None
    if manifest.get("attack_sha256"):
        path = (Path(manifest["attack_path"]) if manifest.get("attack_path")
                else _find_by_hash(root / "data/medsec", manifest["attack_sha256"], "**/*.json"))
        if digest(path.read_bytes()) != manifest["attack_sha256"]:
            raise ValueError("attack sample fingerprint changed")
        if path.suffix == ".jsonl":
            matches = [json.loads(line) for line in path.read_text().splitlines() if line.strip()
                       and json.loads(line).get("attack_id") == manifest["attack_id"]]
            if len(matches) != 1:
                raise ValueError("attack_id missing or duplicated in JSONL")
            sample = matches[0]
        else:
            sample = json.loads(path.read_text())
    from .run import security_events, target_episode_events
    security = judge(sample, task, security_events(events, task["id"], sample)) if sample else None
    official = None
    fixture_grade = None
    if grader and answer is not None:
        if manifest.get("grader_sha256") and digest(Path(grader).read_bytes()) != manifest["grader_sha256"]:
            raise ValueError("grader fingerprint changed")
        from .run import official_score
        grade = official_score(Path(grader), task, target_episode_events(events, task["id"]), answer, manifest["fhir_base"])
        if manifest.get("offline_patient_fixture"):
            fixture_grade = grade
        else:
            official = grade
    metrics = {"run_id": manifest["run_id"], "task_id": task["id"],
               "attack_id": manifest.get("attack_id"), "security": security,
               "official_utility_pass": official,
               "grader_pass_on_fixture_trace": fixture_grade,
               "offline_patient_fixture": bool(manifest.get("offline_patient_fixture")),
               "event_count": len(events)}
    (run_dir / "metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2) + "\n")
    return metrics
