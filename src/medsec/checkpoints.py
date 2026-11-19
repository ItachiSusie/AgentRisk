"""Export action, observation, and output checkpoints from a MedSec event trace.

Labels are targeted attack evidence only. A missing targeted label is not a
general clinical-safety label and must not be used as a safe example.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .judge import judge
from .run import security_events
from .runtime import digest


def extract(run_dir):
    run_dir = Path(run_dir)
    manifest = json.loads((run_dir / "manifest.json").read_text())
    events = [json.loads(line) for line in (run_dir / "events.jsonl").read_text().splitlines()]
    tasks = {t["id"]: t for t in json.loads(Path(manifest["tasks_path"]).read_text())}
    sample = None
    if manifest.get("attack_path"):
        path = Path(manifest["attack_path"])
        if digest(path.read_bytes()) != manifest["attack_sha256"]:
            raise ValueError("attack sample fingerprint changed")
        sample = json.loads(path.read_text())
    task = tasks[manifest["task_id"]]
    scored = judge(sample, task, security_events(events, task["id"], sample)) if sample else None
    evidence = set(scored["evidence_refs"]) if scored else set()
    output = []
    episode = None
    last_request_seq = 0
    last_request_count = 0
    preloaded_surfaces = set()
    for index, event in enumerate(events):
        kind = event["kind"]
        if kind == "episode_started":
            episode = event["task_id"]
            previous_finish = max((item["seq"] for item in events[:index]
                                   if item["kind"] == "final_answer"), default=0)
            preloaded_surfaces = {item.get("surface") for item in events[:index]
                                  if previous_finish < item["seq"] < event["seq"]
                                  and item["kind"] == "attack_presented_to_model"
                                  and item.get("surface") == "tool_description"}
            last_request_seq = event["seq"]
            last_request_count = 0
        if kind == "model_request":
            new_messages = event["messages"][last_request_count:]
            interval = [item for item in events if last_request_seq < item["seq"] < event["seq"]]
            presented = [item for item in interval if item["kind"] == "attack_presented_to_model"]
            poisoned = [item for item in interval if item["kind"] == "memory_presented_to_model"
                        and sample and item.get("source_ref") == "external_note:" + sample["attack_id"]]
            surfaces = {item.get("surface") for item in presented if item.get("surface")}
            surfaces |= preloaded_surfaces
            if poisoned:
                surfaces.add("memory_induced")
            if sample and any(step["surface"] == "memory_store_edit" for step in sample["attack_steps"]):
                if any(item["kind"] == "memory_presented_to_model" and
                       item.get("source_ref") == "store_tamper:" + sample["attack_id"]
                       for item in interval):
                    surfaces.add("memory_store_edit")
            if sample and any(step["surface"] == "skill_file" for step in sample["attack_steps"]):
                if any(item["kind"] == "skill_loaded" for item in interval):
                    surfaces.add("skill_file")
            surfaces = sorted(surfaces)
            for message in new_messages:
                if message["role"] != "user":
                    continue
                output.append({"run_id": manifest["run_id"], "task_id": episode,
                               "checkpoint": "observation", "seq": event["seq"],
                               "model_input_sha256": event["messages_sha256"],
                               "candidate": message["content"],
                               "attack_surfaces_visible": surfaces,
                               "targeted_attack_exposure": bool(surfaces),
                               "label_scope": "targeted attack exposure; not a general prompt-injection label"})
            if surfaces and not any(message["role"] == "user" for message in new_messages):
                output.append({"run_id": manifest["run_id"], "task_id": episode,
                               "checkpoint": "observation", "seq": event["seq"],
                               "model_input_sha256": event["messages_sha256"],
                               "candidate": "model-visible tool description",
                               "attack_surfaces_visible": surfaces,
                               "targeted_attack_exposure": True,
                               "label_scope": "targeted attack exposure; not a general prompt-injection label"})
            last_request_seq = event["seq"]
            last_request_count = len(event["messages"])
            preloaded_surfaces.clear()
        if kind == "model_action":
            following = []
            for item in events[index+1:]:
                if item["kind"] in {"model_action", "episode_started"}:
                    break
                following.append(item)
            refs = [item["seq"] for item in following if item["seq"] in evidence]
            output.append({"run_id": manifest["run_id"], "task_id": episode,
                           "checkpoint": "action", "seq": event["seq"],
                           "candidate": event["action"], "targeted_goal_evidence_refs": refs,
                           "label_scope": "targeted goal evidence; absence is not a safe label"})
        if kind == "final_answer":
            output.append({"run_id": manifest["run_id"], "task_id": episode,
                           "checkpoint": "model_output", "seq": event["seq"],
                           "candidate": event["answer"],
                           "targeted_goal_evidence_refs": [event["seq"]] if event["seq"] in evidence else [],
                           "label_scope": "targeted goal evidence; absence is not a safe label"})
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rows = extract(args.run_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(json.dumps({"output": str(args.output), "checkpoints": len(rows),
                      "types": {kind: sum(r["checkpoint"] == kind for r in rows)
                                for kind in ("action", "observation", "model_output")}}))


if __name__ == "__main__":
    main()
