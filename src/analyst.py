"""Stage 2: trajectory-grounded error analysis (the agentic error analyst).

Two calls per failure, with a mechanical gate between them:

  call 1  explain   gold basis + VERBATIM evidence quotes + what the current instruction implies
  gate              every quote must be a contiguous substring of the trajectory (else discard)
  call 2  patch     TRIGGER / RULE / COUNTER-EXAMPLE, bounded by neighbouring train samples

The gate is the cheap version of "inspect the artifact and validate the fix": it stops the
model from inventing a failure mechanism that the text does not support.

Usage:
    python src/analyst.py worklist results/_smoke/.../triage/triage.jsonl
    python src/analyst.py run --worklist results/analysis/<name>/worklist.jsonl --limit 5
    python src/analyst.py run --worklist ... --dry-run          # build dossiers, no API call
    python src/analyst.py probe --instruction prompts/zero_shot_v1.txt --patch patches/<id>.txt \
        --ids AGENTRISK-235,AGENTRISK-501
"""
import argparse
import json
import re
import sys
from pathlib import Path

from rank_bm25 import BM25Okapi

from common import DOMAINS, DRIVERS, load_jsonl
from run import PARAMS, get_client

ROOT = Path(__file__).resolve().parent.parent
EXPLAIN_PROMPT = ROOT / "prompts" / "analyst_v1_explain.txt"
PATCH_PROMPT = ROOT / "prompts" / "analyst_v1_patch.txt"
ROOT_CAUSES = ("label_definition", "evidence_reading", "severity_anchor", "output_schema", "unexplained")


# ---------------------------------------------------------------- helpers
def norm(text):
    return re.sub(r"\s+", " ", text or "").strip()


def quote_in_text(quote, haystack_norm):
    q = norm(quote)
    if len(q) < 12:          # too short to be evidence
        return False
    return q in haystack_norm


def tokenize(text):
    return re.findall(r"[a-z0-9]+", (text or "").lower())


def build_pool(rows, k=3):
    """BM25 over the candidate pool's trajectories, for neighbour guardrails."""
    bm25 = BM25Okapi([tokenize(r["formatted_interaction"]) for r in rows])
    return bm25, rows


def neighbours(bm25, rows, row, k=3):
    scores = bm25.get_scores(tokenize(row["formatted_interaction"]))
    order = sorted(range(len(rows)), key=lambda i: (-scores[i], i))
    return [rows[i] for i in order if rows[i]["example_id"] != row["example_id"]][:k]


def call_json(client, system, payload, retries=2):
    for attempt in range(retries + 1):
        try:
            resp = client.chat.completions.create(
                messages=[{"role": "system", "content": system},
                          {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
                **PARAMS,
            )
            content = resp.choices[0].message.content
            return json.loads(content), resp
        except (json.JSONDecodeError, TypeError, IndexError) as exc:
            if attempt == retries:
                raise
            print(f"    retry after bad response: {exc}", flush=True)
    raise RuntimeError("unreachable")


def dossier(row, pred, triage_rec, neighbour_rows):
    """Everything the analyst is allowed to see for one failure."""
    def label_block(r):
        return {"risk_severity": r["risk_severity"], "risk_domains": r["risk_domains"],
                "risk_drivers": r["risk_drivers"]}

    return {
        "example_id": row["example_id"],
        "trajectory": row["formatted_interaction"],
        "proposed_action": row["proposed_action"],
        "gold": label_block(row),
        "prediction": {"risk_severity": pred["risk_severity"], "risk_domains": pred["risk_domains"],
                       "risk_drivers": pred["risk_drivers"]},
        "triage": {k: triage_rec[k] for k in
                   ("bucket", "severity_delta", "domain_missing", "domain_extra",
                    "driver_missing", "driver_extra") if k in triage_rec},
        "why_this_sample_was_selected": (
            f"severity delta {triage_rec.get('severity_delta'):+d}; "
            f"domain missing {triage_rec.get('domain_missing')} / extra {triage_rec.get('domain_extra')}; "
            f"driver missing {triage_rec.get('driver_missing')} / extra {triage_rec.get('driver_extra')}"
        ),
        "neighbour_guardrails": [
            {"example_id": n["example_id"], "gold": label_block(n),
             "proposed_action": n["proposed_action"][:400]}
            for n in neighbour_rows
        ],
    }


# ---------------------------------------------------------------- subcommands
def stratified_sample(fails, n, seed=0):
    """Proportional allocation across buckets, deterministic per bucket."""
    import random
    by = {}
    for r in fails:
        by.setdefault(r["bucket"], []).append(r)
    total = len(fails)
    quota = {b: n * len(v) / total for b, v in by.items()}
    alloc = {b: int(q) for b, q in quota.items()}
    # largest remainder, at least 1 per bucket so rare buckets are represented
    for b in by:
        alloc[b] = max(alloc[b], 1) if len(by[b]) >= 1 else 0
    while sum(alloc.values()) > n:
        b = max((b for b in alloc if alloc[b] > 1), key=lambda b: alloc[b] - quota[b])
        alloc[b] -= 1
    while sum(alloc.values()) < n:
        b = max((b for b in by if alloc[b] < len(by[b])), key=lambda b: quota[b] - alloc[b])
        alloc[b] += 1
    picked = []
    for b, k in sorted(alloc.items()):
        if k:
            picked += random.Random(f"{seed}:{b}").sample(by[b], k)
    return picked, alloc


def cmd_worklist(args):
    recs = load_jsonl(Path(args.triage))
    fails = [r for r in recs if r.get("status") == "scored" and r.get("bucket") != "exact"]
    if args.sample:
        fails, alloc = stratified_sample(fails, min(args.sample, len(fails)), args.seed)
        print("stratified allocation: " + ", ".join(f"{b}={k}" for b, k in sorted(alloc.items())))
        default_name = f"worklist_sample{args.sample}.jsonl"
    else:
        default_name = "worklist.jsonl"
    out = Path(args.out) if args.out else Path(args.triage).parent.parent / default_name
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        for r in fails:
            f.write(json.dumps({"example_id": r["example_id"], "bucket": r["bucket"],
                                "severity_delta": r["severity_delta"]}, ensure_ascii=False) + "\n")
    by = {}
    for r in fails:
        by[r["bucket"]] = by.get(r["bucket"], 0) + 1
    print(f"{len(fails)} failures -> {out}")
    for k, v in sorted(by.items(), key=lambda kv: -kv[1]):
        print(f"  {k}: {v}")


def cmd_run(args):
    triage_dir = Path(args.triage).parent
    run_dir = triage_dir.parent
    config = json.loads((run_dir / "config.json").read_text())
    data_path = ROOT / config["data_file"]
    rows = {r["example_id"]: r for r in load_jsonl(data_path)}
    triage = {r["example_id"]: r for r in load_jsonl(Path(args.triage))}
    preds = {r["example_id"]: r for r in load_jsonl(run_dir / "predictions.jsonl")}

    pool_path = Path(args.pool) if args.pool else data_path
    pool = load_jsonl(pool_path)
    bm25, pool_rows = build_pool(pool)

    worklist = load_jsonl(Path(args.worklist))
    out_dir = Path(args.out_dir) if args.out_dir else ROOT / "results" / "analysis" / run_dir.name
    out_dir.mkdir(parents=True, exist_ok=True)
    lessons_path = out_dir / "lessons.jsonl"
    done = set()
    if lessons_path.exists():
        done = {json.loads(l)["example_id"] for l in lessons_path.read_text().splitlines() if l.strip()}

    instruction = (ROOT / config["prompt_file"]).read_text(encoding="utf-8")
    explain_sys = EXPLAIN_PROMPT.read_text(encoding="utf-8")
    patch_sys = PATCH_PROMPT.read_text(encoding="utf-8")
    todo = [w for w in worklist if w["example_id"] not in done][: args.limit]
    print(f"{len(done)} already analysed, {len(todo)} to do -> {lessons_path}", flush=True)

    client = None if args.dry_run else get_client()
    kept = discarded = 0

    for i, item in enumerate(todo, 1):
        eid = item["example_id"]
        row, pred, tri = rows[eid], preds[eid], triage[eid]
        doss = dossier(row, pred, tri, neighbours(bm25, pool_rows, row, args.neighbours))

        if args.dry_run:
            print(f"[{i}/{len(todo)}] {eid} {tri['bucket']} | dossier {len(json.dumps(doss))} chars")
            if i == 1:
                print(json.dumps(doss, ensure_ascii=False)[:800])
            continue

        payload = dict(doss, instruction=instruction)
        explain, _ = call_json(client, explain_sys, payload)
        quotes = explain.get("evidence") or []
        hay = norm(row["formatted_interaction"] + "\n" + row["proposed_action"])
        ok_quotes = [q for q in quotes if quote_in_text(q, hay)]
        bad_quotes = [q for q in quotes if q not in ok_quotes]
        root_cause_type = explain.get("root_cause_type")

        record = {"example_id": eid, "bucket": tri["bucket"], "gold": doss["gold"],
                  "prediction": doss["prediction"], "explain": explain,
                  "quotes_ok": ok_quotes, "quotes_rejected": bad_quotes,
                  "root_cause_type": root_cause_type, "patch": None, "status": None}

        if root_cause_type not in ROOT_CAUSES:
            record["status"] = "discarded:bad_root_cause_type"
        elif not ok_quotes:
            record["status"] = "discarded:no_verbatim_evidence"
        else:
            patch, _ = call_json(client, patch_sys, {
                "instruction": instruction, "diagnosis": explain,
                "neighbour_guardrails": doss["neighbour_guardrails"],
            })
            record["patch"] = patch
            if not patch.get("patch_text"):
                record["status"] = "discarded:patch_refused"
            else:
                record["status"] = "kept"

        kept += record["status"] == "kept"
        discarded += record["status"] != "kept"
        with lessons_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        print(f"[{i}/{len(todo)}] {eid} {record['status']} "
              f"quotes {len(ok_quotes)}/{len(quotes)} cause={root_cause_type}", flush=True)

    print(f"kept {kept}, discarded {discarded}")


def cmd_probe(args):
    """Apply one patch on top of the instruction and see what flips."""
    instruction = (ROOT / args.instruction).read_text(encoding="utf-8")
    patch = Path(args.patch).read_text(encoding="utf-8")
    system = instruction.rstrip() + "\n\n" + patch.strip() + "\n"
    ids = [i.strip() for i in args.ids.split(",") if i.strip()]
    data_path = ROOT / args.data
    rows = {r["example_id"]: r for r in load_jsonl(data_path)}
    client = get_client()
    flips, breaks = [], []
    for eid in ids:
        row = rows[eid]
        got, _ = call_json(client, system, {"formatted_interaction": row["formatted_interaction"],
                                            "proposed_action": row["proposed_action"]})
        before = {"risk_severity": row.get("_pred_severity"), "risk_domains": row.get("_pred_domains")}
        gold_sev = row["risk_severity"]
        ok_before = None
        ok_after = got.get("risk_severity") == gold_sev
        print(f"{eid}: gold sev {gold_sev} -> patch sev {got.get('risk_severity')} "
              f"{'FIXED' if ok_after else 'still wrong'}; domains {got.get('risk_domains')} "
              f"drivers {got.get('risk_drivers')}")
        (flips if ok_after else breaks).append(eid)
    print(f"\nfixed {len(flips)}/{len(ids)}: {flips}")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="command", required=True)

    w = sub.add_parser("worklist", help="failures from a triage.jsonl")
    w.add_argument("triage")
    w.add_argument("--out", default=None)
    w.add_argument("--sample", type=int, default=None, help="stratified subsample size")
    w.add_argument("--seed", type=int, default=0)
    w.set_defaults(func=cmd_worklist)

    r = sub.add_parser("run", help="explain + patch every failure in a worklist")
    r.add_argument("--triage", required=True, help="<run_dir>/triage/triage.jsonl")
    r.add_argument("--worklist", required=True)
    r.add_argument("--out-dir", default=None)
    r.add_argument("--pool", default=None, help="candidate rows for neighbour guardrails (default: the run's data file)")
    r.add_argument("--neighbours", type=int, default=3)
    r.add_argument("--limit", type=int, default=None)
    r.add_argument("--dry-run", action="store_true")
    r.set_defaults(func=cmd_run)

    p = sub.add_parser("probe", help="run one patch text over some ids")
    p.add_argument("--instruction", default="prompts/zero_shot_v1.txt")
    p.add_argument("--patch", required=True)
    p.add_argument("--ids", required=True)
    p.add_argument("--data", default="data/raw/dev.jsonl")
    p.set_defaults(func=cmd_probe)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
