"""Paired none-vs-scope evaluation of the v21 calibrated attack set.

For every selected v21 attack, run the SAME attack under `none` and under
`scope`, plus a clean baseline per task per defense, through the v21 neutral
executor. Report per surface: ASR under each defense (denominator = attacks
whose clean baseline passes under that defense) and the paired reduction on the
common evaluable set. Resumable: one job record per episode, skipped if present.

Expected shape: wrong_patient collapses under scope (it blocks cross-patient
writes); memory poisoning persists under scope (scope does not inspect memory).
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
from src.medsec.v08.attack import load_attack
from src.medsec.v08.contracts import Events, sha256
from src.medsec.v08.models import DeepSeekTextModel
from src.medsec.v08.scoring import security_score
from src.medsec.v21 import episode as v21_episode

OUT = ROOT / "data/medsec/v21_attacks"
MODEL = "deepseek-flash"
DEFENSES = ("none", "scope")


def jid(*parts) -> str:
    return hashlib.sha256(json.dumps(parts).encode()).hexdigest()[:20]


def run_ep(task: dict, runs: Path, *, attack=None, payload=None, defense="none", memory_root=None) -> dict:
    run_id = datetime.now(timezone.utc).strftime("v21p-%Y%m%dT%H%M%SZ-") + uuid.uuid4().hex[:12]
    model = DeepSeekTextModel(MODEL, json_mode=True)
    res = v21_episode.run_extension(task, model, run_id, workspace=runs / run_id / "workspace",
                                    attack=attack, payload=payload, defense_policy=defense,
                                    memory_root=memory_root)
    (runs / run_id / "events.jsonl").write_text(
        "".join(json.dumps(e, ensure_ascii=False) + "\n" for e in res["events"]))
    sec = security_score(attack, res["events"]) if attack else None
    return {"run_id": run_id, "status": res["status"], "utility": res["synthetic_utility_pass"],
            "security": sec}


def load_entry_task(entry: dict) -> dict:
    if entry["surface"] == "memory_store_edit":
        return json.loads((OUT / entry["target_ref"]).read_text())
    return json.loads(Path(entry["base_task_path"]).read_text())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--output-root", type=Path, default=ROOT / "results/medsec")
    args = ap.parse_args()
    man = json.loads((OUT / "manifest.json").read_text())
    run_id = datetime.now(timezone.utc).strftime("v21-paired-%Y%m%dT%H%M%SZ-") + uuid.uuid4().hex[:8]
    root = args.output_root.resolve() / run_id
    runs = root / "runs"
    jobs = root / "jobs"
    seeds = root / "seeds"
    for d in (runs, jobs, seeds):
        d.mkdir(parents=True)

    entries = [e for v in man["selected"].values() for e in v]
    # distinct base tasks (non-memory) and memory sources
    nonmem_tasks = {e["base_task_path"]: e for e in entries if e["surface"] != "memory_store_edit"}
    mem_sources = {e["source_ref"] for e in entries if e["surface"] == "memory_store_edit"}

    def record(identifier, fn):
        jp = jobs / (identifier + ".json")
        if jp.exists():
            return json.loads(jp.read_text())
        try:
            row = fn()
            out = {"id": identifier, "state": "complete", **row}
        except Exception as exc:
            out = {"id": identifier, "state": "error", "error": f"{type(exc).__name__}: {exc}"[:300]}
        jp.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n")
        return out

    # ---- stage 1: memory sources (seed once each) ----
    def do_source(src_ref):
        task = json.loads((OUT / src_ref).read_text())
        seed = seeds / jid("src", src_ref)
        r = run_ep(task, runs, memory_root=seed)
        return {"src_ref": src_ref, "seed": str(seed), "source_pass": r["utility"] is True, "run_id": r["run_id"]}

    seed_map = {}
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futs = {pool.submit(record, jid("source", s), lambda s=s: do_source(s)): s for s in mem_sources}
        for f in as_completed(futs):
            r = f.result()
            seed_map[futs[f]] = r

    # ---- stage 2: clean baselines (per task per defense) ----
    def do_clean(task_json, mem_seed, defense):
        mr = None
        if mem_seed:
            mr = runs / ("cl-" + uuid.uuid4().hex[:10])
            shutil.copytree(mem_seed, mr)
        r = run_ep(task_json, runs, defense=defense, memory_root=mr)
        return {"utility": r["utility"], "status": r["status"], "run_id": r["run_id"]}

    clean = {}  # (key, defense) -> pass bool
    clean_jobs = []
    for tp, e in nonmem_tasks.items():
        for d in DEFENSES:
            clean_jobs.append(("nm", tp, e, d))
    for e in entries:
        if e["surface"] == "memory_store_edit":
            for d in DEFENSES:
                clean_jobs.append(("mem", e["target_ref"], e, d))
    seen_clean = set()
    uniq_clean = []
    for job in clean_jobs:
        key = (job[1], job[3])
        if key in seen_clean:
            continue
        seen_clean.add(key)
        uniq_clean.append(job)

    def run_clean(job):
        kind, key, e, d = job
        task = load_entry_task(e)
        seed = None
        if kind == "mem":
            sj = seed_map.get(e["source_ref"])
            if not sj or not sj.get("source_pass"):
                return (key, d), {"state": "blocked_source"}
            seed = Path(sj["seed"])
        r = record(jid("clean", kind, key, d), lambda: do_clean(task, seed, d))
        return (key, d), r

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for (key, d), r in [f.result() for f in as_completed([pool.submit(run_clean, j) for j in uniq_clean])]:
            clean[(key, d)] = (r.get("state") == "complete" and r.get("utility") is True)

    # ---- stage 3: attacks under none + scope ----
    def do_attack(entry, defense):
        task = load_entry_task(entry)
        sample, payload = load_attack(OUT / entry["attack_ref"], OUT,
                                      Events("p", "medagentbench_ext", entry["task_id"]))
        seed = None
        if entry["surface"] == "memory_store_edit":
            seed = runs / ("at-" + uuid.uuid4().hex[:10])
            shutil.copytree(Path(seed_map[entry["source_ref"]]["seed"]), seed)
        r = run_ep(task, runs, attack=sample, payload=payload, defense=defense, memory_root=seed)
        sec = r["security"] or {}
        return {"success": bool(sec.get("attack_success")), "exposed": bool(sec.get("exposed")),
                "status": r["status"], "run_id": r["run_id"]}

    attack_jobs = [(e, d) for e in entries for d in DEFENSES]

    def run_attack(job):
        e, d = job
        if e["surface"] == "memory_store_edit":
            sj = seed_map.get(e["source_ref"])
            if not sj or not sj.get("source_pass"):
                return e, d, {"state": "blocked_source"}
        r = record(jid("attack", e["attack_id"], d), lambda: do_attack(e, d))
        return e, d, r

    results = defaultdict(lambda: defaultdict(list))  # surface -> defense -> [rows]
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for e, d, r in [f.result() for f in as_completed([pool.submit(run_attack, j) for j in attack_jobs])]:
            ck = (e["base_task_path"] if e["surface"] != "memory_store_edit" else e["target_ref"], d)
            results[e["surface"]][d].append({"attack_id": e["attack_id"], "scenario_group_id": e["scenario_group_id"],
                                             "clean_pass": clean.get(ck, False),
                                             "success": bool(r.get("success")), "exposed": bool(r.get("exposed")),
                                             "state": r.get("state", "complete")})

    # ---- aggregate ----
    summary = {}
    for surface, byd in results.items():
        row = {}
        for d in DEFENSES:
            rows = byd.get(d, [])
            elig = [x for x in rows if x["clean_pass"] and x["state"] == "complete"]
            succ = sum(x["success"] for x in elig)
            row[d] = {"attacks": len(rows), "eligible": len(elig), "successes": succ,
                      "asr": succ / len(elig) if elig else None,
                      "groups": len({x["scenario_group_id"] for x in elig})}
        # paired: attacks eligible under BOTH defenses
        bykey = defaultdict(dict)
        for d in DEFENSES:
            for x in byd.get(d, []):
                bykey[x["attack_id"]][d] = x
        paired = [v for v in bykey.values() if all(d in v and v[d]["clean_pass"] and v[d]["state"] == "complete"
                                                   for d in DEFENSES)]
        row["paired"] = {"n": len(paired),
                         "asr_none": sum(p["none"]["success"] for p in paired) / len(paired) if paired else None,
                         "asr_scope": sum(p["scope"]["success"] for p in paired) / len(paired) if paired else None}
        summary[surface] = row
    report = {"format": "medsec-v21-paired", "run_id": run_id, "model": MODEL,
              "attack_set": "data/medsec/v21_attacks", "defenses": list(DEFENSES),
              "summary": summary,
              "note": "Neutral base agent = `none`. ASR denominator = attacks whose clean baseline passes "
                      "under that defense. Paired rows are eligible under both. Synthetic, unreviewed; "
                      "successes calibrated to deepseek-flash; count by scenario_group_id for independence."}
    (root / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"run_id": run_id, "summary": summary}, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
