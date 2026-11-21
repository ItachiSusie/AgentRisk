"""Rebuild data/medsec/v21_attacks/ with ALL calibrated successes (no cap, no model calls).

Reads the saved calibration reports (results[...] rows with success flags) and the
candidate files they reference, and persists every successful attack per surface.
Non-memory surfaces come from the main calibration run; memory_store_edit from the
memory top-up run. Pass the two run ids explicitly so the selection is reproducible.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.medsec.v08.attack import load_attack
from src.medsec.v08.contracts import Events
from src.medsec.v08.contracts import sha256

OUT = ROOT / "data/medsec/v21_attacks"
NONMEM = ("fhir_response", "tool_result", "skill_file", "malicious_user")


def write(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n")


def persist(entry_rows, surface, out):
    """Copy each success row's attack/payload(/tasks) into OUT, return manifest entries."""
    entries = []
    for r in entry_rows:
        attack_path = Path(r["attack_path"])
        cand_dir = attack_path.parents[1]          # <calib run>/candidates
        attack = json.loads(attack_path.read_text())
        payload = (cand_dir / attack["payload_ref"]).read_text()
        aid = attack["attack_id"]
        pref = "payloads/" + aid + ".txt"
        (out / pref).write_text(payload)
        if sha256(payload) != attack["payload_sha256"]:
            raise ValueError("payload sha mismatch for " + aid)
        attack["payload_ref"] = pref
        aref = "attacks/" + aid + ".json"
        write(out / aref, attack)
        entry = dict(attack_id=aid, attack_ref=aref, payload_ref=pref, surface=surface,
                     goal_id=attack["goal_id"], task_id=attack["task_id"], run_id=r.get("run_id"),
                     scenario_group_id=attack.get("scenario_group_id", ""))
        if surface == "memory_store_edit":
            for role_key in ("source", "target"):
                tp = Path(r[role_key])
                tref = "tasks/" + tp.name
                (out / tref).write_text(tp.read_text())
                entry[role_key + "_ref"] = tref
        else:
            entry["base_task_path"] = r["task_path"]
        entries.append(entry)
    return entries


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--nonmem-runs", nargs="+",
                    default=["v21-calib-20261120T004343Z-a113dfe4"],
                    help="one or more calibration run ids whose non-memory successes are merged")
    ap.add_argument("--memory-run", default="v21-calib-20261120T005155Z-597a7d1d")
    args = ap.parse_args()
    # Merge non-memory results across runs, de-duplicating by attack_id.
    nonmem: dict[str, list] = {s: [] for s in NONMEM}
    seen = set()
    for rid in args.nonmem_runs:
        res = json.loads((ROOT / "results/medsec" / rid / "calibration_report.json").read_text())["results"]
        for s in NONMEM:
            for r in res.get(s, []):
                if r["attack_id"] in seen:
                    continue
                seen.add(r["attack_id"])
                nonmem[s].append(r)
    memrep = json.loads((ROOT / "results/medsec" / args.memory_run / "calibration_report.json").read_text())["results"]

    if OUT.exists():
        shutil.rmtree(OUT)
    for sub in ("attacks", "payloads", "tasks"):
        (OUT / sub).mkdir(parents=True)

    selected, summary = {}, {}
    for surface in NONMEM:
        rows = [r for r in nonmem.get(surface, []) if r["success"]]
        selected[surface] = persist(rows, surface, OUT)
        summary[surface] = {"candidates": len(nonmem.get(surface, [])), "successes": len(rows),
                            "selected": len(rows), "exposed": sum(r["exposed"] for r in nonmem.get(surface, []))}
    mrows = [r for r in memrep.get("memory_store_edit", []) if r["success"]]
    selected["memory_store_edit"] = persist(mrows, "memory_store_edit", OUT)
    summary["memory_store_edit"] = {"candidates": len(memrep.get("memory_store_edit", [])),
                                    "successes": len(mrows), "selected": len(mrows),
                                    "exposed": sum(r["exposed"] for r in memrep.get("memory_store_edit", []))}

    manifest = {"format": "medsec-v21-attacks", "status": "synthetic_candidate_unreviewed", "model": "deepseek-flash",
                "selection": "all_calibrated_successes", "calibration_runs": [*args.nonmem_runs, args.memory_run],
                "note": "Every attack that genuinely succeeded on the reference model under the neutral base "
                        "agent (none). Not rigged; success from security_score. Variants on the same base task "
                        "share scenario_group_id and are NOT independent samples.",
                "summary": summary, "selected": selected}
    write(OUT / "manifest.json", manifest)

    # verify every persisted attack loads
    ok = 0
    for surface, entries in selected.items():
        for e in entries:
            load_attack(OUT / e["attack_ref"], OUT, Events("v", "medagentbench_ext", e["task_id"]))
            ok += 1
    total = sum(len(v) for v in selected.values())
    print(json.dumps({"selected_per_surface": {k: len(v) for k, v in selected.items()},
                      "total": total, "load_ok": ok}, indent=2))


if __name__ == "__main__":
    main()
