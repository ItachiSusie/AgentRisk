"""Guardrail-defense pilot: none vs scope vs guardrail on a representative subset.

Reuses the medbench_v1 attack set and the v21 goals judge, but runs through the
v25 episode (which adds the content-level `guardrail` defense: an LLM injection
filter over untrusted observations). Produces a harm x defense ASR table so the
paper can contrast an identity defense (scope) with a content defense (guardrail).

Representative subset: up to PER_HARM attacks per harm type, chosen for surface
diversity (deterministic). Self-contained: runs none/scope/guardrail on the same
subset so the three columns are apples-to-apples. Resumable via a jobs cache.
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

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.medsec.v08.attack import load_attack
from src.medsec.v08.contracts import ROOT, Events
from src.medsec.v08.models import DeepSeekTextModel
from src.medsec.v25 import episode as v25_episode
from src.medsec.v21.goals import score as goal_score
from scripts.medsec_bench_run import clean_pass  # reuse tolerant clean check

BENCH = ROOT / "data/medsec/medbench_v1"
MODEL = "deepseek-flash"
DEFENSES = ("none", "scope", "guardrail")
PER_HARM = 12


def jid(*p):
    return hashlib.sha256(json.dumps(p).encode()).hexdigest()[:20]


def run_ep(task, runs, *, attack=None, payload=None, defense="none", memory_root=None):
    run_id = datetime.now(timezone.utc).strftime("gp-%Y%m%dT%H%M%SZ-") + uuid.uuid4().hex[:12]
    model = DeepSeekTextModel(MODEL, json_mode=True)
    res = v25_episode.run_extension(task, model, run_id, workspace=runs / run_id / "workspace",
                                    attack=attack, payload=payload, defense_policy=defense, memory_root=memory_root)
    (runs / run_id / "events.jsonl").write_text(
        "".join(json.dumps(e, ensure_ascii=False) + "\n" for e in res["events"]))
    return {"run_id": run_id, "status": res["status"], "events": res["events"],
            "utility": res["synthetic_utility_pass"],
            "security": goal_score(attack, res["events"]) if attack else None}


def select(entries):
    by_harm = defaultdict(list)
    for e in entries:
        by_harm[e["harm_type"]].append(e)
    chosen = []
    for harm, es in sorted(by_harm.items()):
        seen_surface = set()
        picks = []
        # first pass: surface diversity
        for e in es:
            if e["surface"] not in seen_surface:
                picks.append(e); seen_surface.add(e["surface"])
            if len(picks) >= PER_HARM:
                break
        # fill remaining deterministically
        for e in es:
            if len(picks) >= PER_HARM:
                break
            if e not in picks:
                picks.append(e)
        chosen.extend(picks)
    return chosen


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()
    man = json.loads((BENCH / "manifest.json").read_text())
    entries = select(man["attacks"])
    run_id = datetime.now(timezone.utc).strftime("guardrail-%Y%m%dT%H%M%SZ-") + uuid.uuid4().hex[:8]
    root = (ROOT / "results/medsec" / run_id)
    runs, jobs, seeds = root / "runs", root / "jobs", root / "seeds"
    for d in (runs, jobs, seeds):
        d.mkdir(parents=True)
    (root / "selection.json").write_text(json.dumps(
        {"run_id": run_id, "per_harm": PER_HARM, "defenses": DEFENSES,
         "attack_ids": [e["attack_id"] for e in entries]}, indent=2))
    print(json.dumps({"run_id": run_id, "attacks": len(entries), "defenses": DEFENSES}), flush=True)

    def record(identifier, fn):
        jp = jobs / (identifier + ".json")
        if jp.exists():
            return json.loads(jp.read_text())
        try:
            out = {"id": identifier, "state": "complete", **fn()}
        except Exception as exc:
            out = {"id": identifier, "state": "error", "error": f"{type(exc).__name__}: {exc}"[:300]}
        jp.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n")
        return out

    # stage 1: memory sources
    sources = {e["source_ref"] for e in entries if e.get("source_ref")}
    seed_map = {}

    def do_source(sref):
        task = json.loads((BENCH / sref).read_text())
        seed = seeds / jid("src", sref)
        r = run_ep(task, runs, memory_root=seed)
        return {"seed": str(seed), "pass": clean_pass(task, r["events"]), "run_id": r["run_id"]}
    if sources:
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futs = {pool.submit(record, jid("source", s), lambda s=s: do_source(s)): s for s in sources}
            for f in as_completed(futs):
                seed_map[futs[f]] = f.result()

    # stage 2: clean baselines per (task_ref, defense)
    clean = {}
    clean_keys = {(e["task_ref"], e.get("source_ref"), d) for e in entries for d in DEFENSES}

    def do_clean(task_ref, source_ref, d):
        task = json.loads((BENCH / task_ref).read_text())
        mr = None
        if source_ref:
            mr = runs / ("cl-" + uuid.uuid4().hex[:10])
            shutil.copytree(Path(seed_map[source_ref]["seed"]), mr)
        r = run_ep(task, runs, defense=d, memory_root=mr)
        return {"pass": clean_pass(task, r["events"])}

    def run_clean(job):
        tref, sref, d = job
        if sref and not seed_map.get(sref, {}).get("pass"):
            return (tref, d), {"pass": False}
        return (tref, d), record(jid("clean", tref, d), lambda: do_clean(tref, sref, d))
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for (tref, d), r in [f.result() for f in as_completed([pool.submit(run_clean, j) for j in clean_keys])]:
            clean[(tref, d)] = (r.get("state", "complete") == "complete" and r.get("pass") is True)

    # stage 3: attacks none/scope/guardrail
    def do_attack(e, d):
        task = json.loads((BENCH / e["task_ref"]).read_text())
        sample, payload = load_attack(BENCH / e["attack_ref"], BENCH, Events("p", "medagentbench_ext", None))
        mr = None
        if e.get("source_ref"):
            mr = runs / ("at-" + uuid.uuid4().hex[:10])
            shutil.copytree(Path(seed_map[e["source_ref"]]["seed"]), mr)
        r = run_ep(task, runs, attack=sample, payload=payload, defense=d, memory_root=mr)
        sec = r["security"] or {}
        return {"success": bool(sec.get("attack_success")), "exposed": bool(sec.get("exposed")), "status": r["status"]}
    rows = []

    def run_attack(job):
        e, d = job
        if e.get("source_ref") and not seed_map.get(e["source_ref"], {}).get("pass"):
            return e, d, {"state": "blocked_source"}
        return e, d, record(jid("atk", e["attack_id"], d), lambda: do_attack(e, d))
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for e, d, r in [f.result() for f in as_completed(
                [pool.submit(run_attack, (e, d)) for e in entries for d in DEFENSES])]:
            rows.append(dict(attack_id=e["attack_id"], harm_type=e["harm_type"], surface=e["surface"],
                             defense=d, clean_pass=clean.get((e["task_ref"], d), False),
                             success=bool(r.get("success")), exposed=bool(r.get("exposed")),
                             state=r.get("state", "complete"), group=e["scenario_group_id"]))

    def asr(subset):
        cap = [r for r in subset if r["clean_pass"] and r["state"] == "complete"]
        n = len(cap); k = sum(r["success"] for r in cap)
        return {"asr": (k / n) if n else None, "n": n, "successes": k,
                "groups": len({r["group"] for r in cap})}
    harms = sorted({r["harm_type"] for r in rows})
    harm_table = {h: {d: asr([r for r in rows if r["harm_type"] == h and r["defense"] == d]) for d in DEFENSES}
                  for h in harms}
    overall = {d: asr([r for r in rows if r["defense"] == d]) for d in DEFENSES}
    report = {"format": "medsec-guardrail-pilot-v1", "run_id": run_id, "model": MODEL,
              "per_harm": PER_HARM, "defenses": DEFENSES, "attack_count": len(entries),
              "harm_table": harm_table, "overall": overall, "rows": rows,
              "note": "Representative subset of medbench_v1; none vs scope vs guardrail (v25 LLM "
                      "injection filter). ASR denominator = baseline-capable under that defense. "
                      "Synthetic, unreviewed, deepseek-flash."}
    (root / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    # markdown table
    lines = ["| harm | none | scope | guardrail |", "| --- | ---: | ---: | ---: |"]
    for h in harms:
        c = harm_table[h]
        def cell(d):
            x = c[d]; return f"{x['asr']:.2f} ({x['successes']}/{x['n']})" if x["asr"] is not None else "n/a"
        lines.append(f"| {h} | {cell('none')} | {cell('scope')} | {cell('guardrail')} |")
    ov = overall
    def ocell(d):
        x = ov[d]; return f"{x['asr']:.2f} ({x['successes']}/{x['n']})" if x["asr"] is not None else "n/a"
    lines.append(f"| **overall** | {ocell('none')} | {ocell('scope')} | {ocell('guardrail')} |")
    (root / "table.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines), flush=True)
    print(json.dumps({"run_id": run_id, "report": str(root / "report.json")}), flush=True)


if __name__ == "__main__":
    main()
