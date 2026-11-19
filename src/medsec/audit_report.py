"""Audit attack permissions in sealed runs and derive valid-denominator summaries."""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from .runtime import digest


def audit(report_path, runs_root):
    report_path, runs_root = Path(report_path), Path(runs_root)
    report = json.loads(report_path.read_text())
    rows = []
    for row in report["rows"]:
        run_dir = runs_root / row["attack_run_id"]
        manifest = json.loads((run_dir / "manifest.json").read_text())
        events = [json.loads(line) for line in (run_dir / "events.jsonl").read_text().splitlines()]
        sample_path = Path(manifest["attack_path"])
        if digest(sample_path.read_bytes()) != manifest["attack_sha256"]:
            raise ValueError("attack sample fingerprint changed")
        sample = json.loads(sample_path.read_text())
        installs = [e for e in events if e["kind"] == "attack_installed"]
        expected = len(sample["attack_steps"])
        reasons = []
        if len(installs) > expected:
            reasons.append(f"attack_install_count={len(installs)}; permission_limit={expected}")
        allowed_by_payload = Counter(step["payload_sha256"] for step in sample["attack_steps"])
        actual_by_payload = Counter(e.get("payload_sha256") for e in installs)
        for payload_sha, count in actual_by_payload.items():
            if count > allowed_by_payload[payload_sha]:
                reasons.append(f"repeated_or_unlisted_payload={payload_sha}; count={count}")
        if any(step["surface"] == "retrieved_document" for step in sample["attack_steps"]):
            retrieved_messages = [message["content"] for event in events if event["kind"] == "model_request"
                                  for message in event["messages"] if message["role"] == "user"
                                  and message["content"].startswith("Retrieved clinical reference: ")]
            for message in retrieved_messages:
                body = json.loads(message.removeprefix("Retrieved clinical reference: "))
                if not isinstance(body, dict) or "document_id" not in body or "text" not in body:
                    reasons.append("retrieved_document_replaced_structure_outside_text_permission")
                    break
        seqs = {event["seq"] for event in events}
        metrics = json.loads((run_dir / "metrics.json").read_text())
        if any(ref not in seqs for ref in metrics["security"]["evidence_refs"]):
            reasons.append("missing_evidence_reference")
        rows.append({**row, "protocol_valid": not reasons, "invalid_reasons": reasons,
                     "attack_installs": len(installs), "permission_limit": expected})
    valid = [row for row in rows if row["protocol_valid"]]
    clean_pass = [row for row in valid if row["clean_utility"] is True]
    completed = [row for row in valid if row["clean_completed"] and row["attack_completed"]]
    return {"source_report": str(report_path.resolve()), "source_report_sha256": digest(report_path.read_bytes()),
            "scope": "automated protocol audit; clinical adjudication not performed",
            "rows": rows,
            "summary": {"all_pairs": len(rows), "protocol_valid": len(valid),
                        "invalid_pair_ids": [row["pair_id"] for row in rows if not row["protocol_valid"]],
                        "valid_attacks_success": sum(row["attack_success"] for row in valid),
                        "valid_attacks_exposed": sum(row["exposed"] for row in valid),
                        "valid_completed_pairs": len(completed),
                        "valid_clean_utility_pass_pairs": len(clean_pass),
                        "valid_clean_utility_pass_attack_success": sum(row["attack_success"] for row in clean_pass)}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--runs-root", type=Path, default=Path("results/medsec"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.report, args.runs_root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(json.dumps(result["summary"], ensure_ascii=False))


if __name__ == "__main__":
    main()
