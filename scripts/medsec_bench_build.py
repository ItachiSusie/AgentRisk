"""Assemble a balanced, self-contained Med security benchmark (~200 attacks).

Samples from the calibrated v21 (wrong_patient + memory poisoning) and v22
(disclosure / unsafe medication / critical-result suppression / oversight bypass)
sets into one directory data/medsec/medbench_v1/, covering 6 harm types across
the injection surfaces. Everything needed to re-run (attack json, payload, base
task, memory source/target) is copied in, so the benchmark is portable.
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
from src.medsec.v08.contracts import sha256

V21 = ROOT / "data/medsec/v21_attacks"
V22 = ROOT / "data/medsec/v22_attacks"
OUT = ROOT / "data/medsec/medbench_v1"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--wp-per-surface", type=int, default=20, help="wrong_patient attacks per surface")
    ap.add_argument("--mem", type=int, default=36, help="memory poisoning attacks")
    args = ap.parse_args()

    if OUT.exists():
        shutil.rmtree(OUT)
    for sub in ("attacks", "payloads", "tasks"):
        (OUT / sub).mkdir(parents=True)
    copied_tasks: dict[str, str] = {}

    def copy_task(src: Path) -> str:
        ref = "tasks/" + src.name
        if src.name not in copied_tasks:
            (OUT / ref).write_text(src.read_text())
            copied_tasks[src.name] = ref
        return ref

    def copy_attack(attack_src: Path, payload_text: str) -> tuple[str, str]:
        a = json.loads(attack_src.read_text())
        aid = a["attack_id"]
        pref = "payloads/" + aid + ".txt"
        (OUT / pref).write_text(payload_text)
        if sha256(payload_text) != a["payload_sha256"]:
            raise ValueError("payload mismatch " + aid)
        a["payload_ref"] = pref
        aref = "attacks/" + aid + ".json"
        (OUT / aref).write_text(json.dumps(a, ensure_ascii=False, indent=2) + "\n")
        return aref, pref

    entries = []

    # ---- v21 wrong_patient (per surface, prefer distinct scenario groups) ----
    v21 = json.loads((V21 / "manifest.json").read_text())
    for surface in ("fhir_response", "tool_result", "skill_file", "malicious_user"):
        rows = v21["selected"].get(surface, [])
        picked, seen = [], set()
        for e in rows:  # first pass: one per scenario group
            g = e["scenario_group_id"]
            if g in seen:
                continue
            seen.add(g); picked.append(e)
            if len(picked) >= args.wp_per_surface:
                break
        for e in rows:  # fill remainder
            if len(picked) >= args.wp_per_surface:
                break
            if e not in picked:
                picked.append(e)
        for e in picked:
            aref, pref = copy_attack(V21 / e["attack_ref"], (V21 / e["payload_ref"]).read_text())
            tref = copy_task(Path(e["base_task_path"]))
            entries.append(dict(attack_id=e["attack_id"], attack_ref=aref, payload_ref=pref,
                                harm_type="wrong_patient", surface=surface, task_ref=tref, source_ref=None,
                                scenario_group_id=e["scenario_group_id"]))

    # ---- v21 memory poisoning (round-robin across contexts for spread) ----
    mem = v21["selected"].get("memory_store_edit", [])
    byctx = defaultdict(list)
    for e in mem:
        byctx[e["scenario_group_id"]].append(e)
    picked, i = [], 0
    while len(picked) < args.mem:
        added = False
        for g in sorted(byctx):
            if i < len(byctx[g]):
                picked.append(byctx[g][i]); added = True
                if len(picked) >= args.mem:
                    break
        if not added:
            break
        i += 1
    for e in picked:
        aref, pref = copy_attack(V21 / e["attack_ref"], (V21 / e["payload_ref"]).read_text())
        tref = copy_task(V21 / e["target_ref"])
        sref = copy_task(V21 / e["source_ref"])
        entries.append(dict(attack_id=e["attack_id"], attack_ref=aref, payload_ref=pref,
                            harm_type="answer_manipulation", surface="memory_store_edit", task_ref=tref,
                            source_ref=sref, scenario_group_id=e["scenario_group_id"]))

    # ---- v22 four harm types (all) ----
    v22 = json.loads((V22 / "manifest.json").read_text())
    for harm, rows in v22["selected"].items():
        for e in rows:
            aref, pref = copy_attack(V22 / e["attack_ref"], (V22 / e["payload_ref"]).read_text())
            tref = copy_task(V22 / e["task_ref"])
            entries.append(dict(attack_id=e["attack_id"], attack_ref=aref, payload_ref=pref,
                                harm_type=harm, surface=e["surface"], task_ref=tref, source_ref=None,
                                scenario_group_id=e["scenario_group_id"]))

    by_harm = defaultdict(int)
    by_surface = defaultdict(int)
    for e in entries:
        by_harm[e["harm_type"]] += 1
        by_surface[e["surface"]] += 1
    manifest = {"format": "medsec-medbench-v1", "benchmark_id": "medagentbench_ext",
                "status": "synthetic_candidate_unreviewed", "model": "deepseek-flash",
                "source_sets": ["data/medsec/v21_attacks", "data/medsec/v22_attacks"],
                "attack_count": len(entries), "by_harm_type": dict(by_harm), "by_surface": dict(by_surface),
                "note": "Balanced Med security dev set: 6 harm types x injection surfaces, calibrated to "
                        "succeed under a neutral agent; synthetic, unreviewed; count by scenario_group_id.",
                "attacks": entries}
    (OUT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"out": str(OUT.relative_to(ROOT)), "total": len(entries),
                      "by_harm_type": dict(by_harm), "by_surface": dict(by_surface)},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
