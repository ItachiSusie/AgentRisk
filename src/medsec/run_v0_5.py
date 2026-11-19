"""Versioned one-shot attack runner; preserves the sealed v0.4 runner unchanged."""
from __future__ import annotations

import copy
import json
import argparse
import sys
from pathlib import Path

from . import run
from .runtime import digest, read_payload


def make_one_shot_injector(original):
    applied = set()

    def inject(sample, surface, target, content, root, events):
        output = copy.deepcopy(content)
        for index, step in enumerate(sample.get("attack_steps", [])):
            key = (sample.get("attack_id"), index)
            if step["surface"] != surface or key in applied:
                continue
            before = len(events.items)
            if surface == "retrieved_document":
                if any(target.get(field) != value for field, value in step["trigger"].items()):
                    continue
                if (not isinstance(output, dict) or output.get("document_id") != step["target_ref"]
                        or "text" not in output):
                    raise ValueError("retrieved_document may edit only text of the selected document")
                payload = read_payload(step, root)
                output["text"] = payload
                events.add("attack_installed", surface=surface,
                           payload_sha256=digest(payload), target=target)
            else:
                one_step = {**sample, "attack_steps": [step]}
                output = original(one_step, surface, target, output, root, events)
            if any(event["kind"] == "attack_installed" for event in events.items[before:]):
                applied.add(key)
        return output

    return inject


def preflight(argv):
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--attack", type=Path)
    parser.add_argument("--attack-id")
    parser.add_argument("--tools", type=Path)
    args, _ = parser.parse_known_args(argv if argv is not None else sys.argv[1:])
    if not args.attack:
        return
    if not args.tools:
        raise ValueError("--tools is required")
    if args.attack.suffix == ".jsonl":
        matches = [json.loads(line) for line in args.attack.read_text().splitlines() if line.strip()
                   and json.loads(line).get("attack_id") == args.attack_id]
        if len(matches) != 1:
            raise ValueError("select exactly one attack from JSONL")
        sample = matches[0]
    else:
        sample = json.loads(args.attack.read_text())
    names = [tool["name"] for tool in json.loads(args.tools.read_text())]
    for step in sample["attack_steps"]:
        if step["surface"] == "tool_description" and names.count(step["trigger"].get("tool_name")) != 1:
            raise ValueError("tool_description must target exactly one definition")
        if step["surface"] == "tool_result" and step["trigger"].get("tool_name") == "GET":
            raise ValueError("FHIR GET records must use environment_fhir, not tool_result")


def main(argv=None):
    preflight(argv)
    original_injector = run.apply_attack
    original_fingerprints = run.code_fingerprints
    run.apply_attack = make_one_shot_injector(original_injector)
    run.code_fingerprints = lambda: {
        **original_fingerprints(), "run_v0_5.py": digest(Path(__file__).read_bytes())}
    try:
        return run.main(argv)
    finally:
        run.apply_attack = original_injector
        run.code_fingerprints = original_fingerprints


if __name__ == "__main__":
    main()
