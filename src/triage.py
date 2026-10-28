"""Offline error triage for a finished run: bucket every sample, aggregate label confusion.

This is the *input* to a trajectory-grounded instruction loop (the error-analyst stage):
it does not call any API, it only turns predictions.jsonl + gold into structured records
that an analyst (human or agent) can then inspect one by one.

Usage:
    python src/triage.py results/deepseek-flash/few-shot-bm25-k10-v1/20261025-055210
    python src/triage.py <run_dir> --examples 15 --out-dir <dir>

Writes <run_dir>/triage/triage.jsonl and <run_dir>/triage/summary.md
"""
import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from common import DOMAINS, DRIVERS, compute_metrics, jaccard, load_jsonl

ROOT = Path(__file__).resolve().parent.parent

# A refusal / clarification opener in the proposed action. Only used to *flag* a subset
# for manual review; it is not a label and must not be used for scoring.
REFUSAL_RE = re.compile(
    r"^\s*(?:i\s+(?:can'?t|cannot|won'?t|am\s+unable|'m\s+unable|am\s+not\s+able)"
    r"|sorry[,.]|i\s+apologi[sz]e|unfortunately[,.]"
    r"|could\s+you|can\s+you\s+(?:confirm|clarify)|before\s+i\s+can|i\s+need\s+(?:more|additional)"
    r"|to\s+proceed[,]\s+i\s+need)",
    re.IGNORECASE,
)


def bucket_of(sev_ok, dom_ok, drv_ok, sev_delta):
    if sev_delta > 0:
        return "severity_over"
    if sev_delta < 0:
        return "severity_under"
    if dom_ok and drv_ok:
        return "exact"
    if not dom_ok and not drv_ok:
        return "labels_both_wrong"
    if not dom_ok:
        return "domain_wrong"
    return "driver_wrong"


def label_stats(pairs, universe):
    """pairs: list of (gold_set, pred_set). Returns per-label tp/missing/extra."""
    stats = {lbl: {"gold": 0, "pred": 0, "tp": 0, "missing": 0, "extra": 0} for lbl in universe}
    for gold, pred in pairs:
        for lbl in gold:
            stats[lbl]["gold"] += 1
            if lbl in pred:
                stats[lbl]["tp"] += 1
            else:
                stats[lbl]["missing"] += 1
        for lbl in pred:
            stats[lbl]["pred"] += 1
            if lbl not in gold:
                stats[lbl]["extra"] += 1
    return stats


def confusion_pairs(pairs, top=10):
    """Count (missing gold label -> extra predicted label) co-occurrences."""
    c = Counter()
    for gold, pred in pairs:
        for g in gold - pred:
            for p in pred - gold:
                c[(g, p)] += 1
    return c.most_common(top)


def pct(x):
    return f"{x * 100:.1f}%"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir")
    ap.add_argument("--out-dir", default=None)
    ap.add_argument("--examples", type=int, default=10, help="how many error examples to print")
    args = ap.parse_args()

    run_dir = Path(args.run_dir)
    out_dir = Path(args.out_dir) if args.out_dir else run_dir / "triage"
    out_dir.mkdir(parents=True, exist_ok=True)

    config = json.loads((run_dir / "config.json").read_text())
    golds = {r["example_id"]: r for r in load_jsonl(ROOT / config["data_file"])}
    preds = {r["example_id"]: r for r in load_jsonl(run_dir / "predictions.jsonl")}

    records = []
    for eid, gold in golds.items():
        pred = preds.get(eid)
        if pred is None:
            records.append({"example_id": eid, "status": "missing"})
            continue
        g_sev, p_sev = gold["risk_severity"], pred["risk_severity"]
        g_dom, p_dom = set(gold["risk_domains"]), set(pred["risk_domains"])
        g_drv, p_drv = set(gold["risk_drivers"]), set(pred["risk_drivers"])
        sev_ok = g_sev == p_sev
        dom_ok, drv_ok = g_dom == p_dom, g_drv == p_drv
        action = (gold.get("proposed_action") or "").strip()
        records.append({
            "example_id": eid,
            "status": "scored",
            "bucket": bucket_of(sev_ok, dom_ok, drv_ok, p_sev - g_sev),
            "gold": {"severity": g_sev, "domains": sorted(g_dom), "drivers": sorted(g_drv)},
            "pred": {"severity": p_sev, "domains": sorted(p_dom), "drivers": sorted(p_drv)},
            "severity_delta": p_sev - g_sev,
            "domain_jaccard": round(jaccard(g_dom, p_dom), 4),
            "driver_jaccard": round(jaccard(g_drv, p_drv), 4),
            "domain_missing": sorted(g_dom - p_dom),
            "domain_extra": sorted(p_dom - g_dom),
            "driver_missing": sorted(g_drv - p_drv),
            "driver_extra": sorted(p_drv - g_drv),
            "refusal_like_action": bool(REFUSAL_RE.match(action[:200])),
            "proposed_action": action[:300],
        })

    scored = [r for r in records if r["status"] == "scored"]
    missing = [r["example_id"] for r in records if r["status"] == "missing"]
    metrics = compute_metrics(preds, golds)

    # --- aggregates -------------------------------------------------------
    buckets = Counter(r["bucket"] for r in scored)
    conf = defaultdict(int)
    for r in scored:
        conf[(r["gold"]["severity"], r["pred"]["severity"])] += 1

    by_gold = defaultdict(lambda: {"n": 0, "exact": 0, "err": 0})
    for r in scored:
        g = r["gold"]["severity"]
        by_gold[g]["n"] += 1
        by_gold[g]["exact"] += int(r["severity_delta"] == 0)
        by_gold[g]["err"] += abs(r["severity_delta"])

    dom_stats = label_stats([(set(r["gold"]["domains"]), set(r["pred"]["domains"])) for r in scored], DOMAINS)
    drv_stats = label_stats([(set(r["gold"]["drivers"]), set(r["pred"]["drivers"])) for r in scored], DRIVERS)
    dom_pairs = confusion_pairs([(set(r["gold"]["domains"]), set(r["pred"]["domains"])) for r in scored])
    drv_pairs = confusion_pairs([(set(r["gold"]["drivers"]), set(r["pred"]["drivers"])) for r in scored])

    refusal = [r for r in scored if r["refusal_like_action"]]
    errors = sorted(
        (r for r in scored if r["bucket"] != "exact"),
        key=lambda r: (-abs(r["severity_delta"]), r["domain_jaccard"] + r["driver_jaccard"]),
    )

    # --- write jsonl ------------------------------------------------------
    with (out_dir / "triage.jsonl").open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # --- write summary ----------------------------------------------------
    L = []
    L.append(f"# Triage — {config.get('run_id', run_dir.name)}\n")
    L.append(f"- run: `{run_dir}`")
    L.append(f"- model: `{config.get('params', {}).get('model')}` · split: `{config.get('split')}` · data: `{config.get('data_file')}`")
    L.append(f"- n={metrics['n_total']} · scored={metrics['n_success']} · missing={len(missing)}")
    L.append(f"- MAE={metrics['task1_mae']:.3f} · domain Jaccard={metrics['task2a_mean_jaccard']:.3f}"
             f" · driver Jaccard={metrics['task2b_mean_jaccard']:.3f}\n")

    L.append("## 1. Buckets\n")
    L.append("| bucket | n | share of scored |")
    L.append("| --- | --- | --- |")
    for b in ("exact", "severity_over", "severity_under", "labels_both_wrong", "domain_wrong", "driver_wrong"):
        n = buckets.get(b, 0)
        L.append(f"| {b} | {n} | {pct(n / len(scored)) if scored else '-'} |")
    L.append("")

    L.append("## 2. Severity confusion (gold → pred)\n")
    L.append("| gold \\ pred | 1 | 2 | 3 | 4 | 5 | total |")
    L.append("| --- | --- | --- | --- | --- | --- | --- |")
    for g in range(1, 6):
        row = [conf.get((g, p), 0) for p in range(1, 6)]
        L.append(f"| **{g}** | " + " | ".join(str(x) for x in row) + f" | {sum(row)} |")
    L.append("| total | " + " | ".join(str(sum(conf.get((g, p), 0) for g in range(1, 6))) for p in range(1, 6)) + " | |")
    L.append("")
    L.append("Errors off the diagonal by distance: " + ", ".join(
        f"|Δ|={d}: {sum(conf.get((g, g + d), 0) + conf.get((g, g - d), 0) for g in range(1, 6))}"
        for d in range(1, 5)
    ) + "\n")

    L.append("## 3. By gold severity\n")
    L.append("| gold sev | n | exact | mean abs error |")
    L.append("| --- | --- | --- | --- |")
    for g in sorted(by_gold):
        d = by_gold[g]
        L.append(f"| {g} | {d['n']} | {d['exact']} ({pct(d['exact'] / d['n'])}) | {d['err'] / d['n']:.2f} |")
    L.append("")

    def label_table(title, stats, universe, pairs):
        L.append(f"## {title}\n")
        L.append("| label | gold | pred | correct | missing | extra |")
        L.append("| --- | --- | --- | --- | --- | --- |")
        for lbl in universe:
            s = stats[lbl]
            if s["gold"] == 0 and s["pred"] == 0:
                continue
            L.append(f"| {lbl} | {s['gold']} | {s['pred']} | {s['tp']} | {s['missing']} | {s['extra']} |")
        L.append("")
        if pairs:
            L.append("Top missing→extra pairs: " + "; ".join(f"`{g}`→`{p}` ×{c}" for (g, p), c in pairs) + "\n")

    label_table("4. Domains", dom_stats, DOMAINS, dom_pairs)
    label_table("5. Drivers", drv_stats, DRIVERS, drv_pairs)

    L.append("## 6. Refusal-like proposed actions (flag only, not a label)\n")
    if refusal:
        L.append(f"{len(refusal)} samples whose `proposed_action` opens as a refusal/clarification.\n")
        L.append("| id | gold sev | pred sev | gold domains | pred domains |")
        L.append("| --- | --- | --- | --- | --- |")
        for r in refusal:
            L.append(f"| {r['example_id']} | {r['gold']['severity']} | {r['pred']['severity']} | "
                     f"{', '.join(r['gold']['domains'])} | {', '.join(r['pred']['domains'])} |")
    else:
        L.append("none matched the heuristic")
    L.append("")

    L.append(f"## 7. Top {args.examples} errors (sorted by |Δseverity|, then label Jaccard)\n")
    L.append("| id | gold | pred | Δ | dom J | drv J | bucket |")
    L.append("| --- | --- | --- | --- | --- | --- | --- |")
    for r in errors[: args.examples]:
        L.append(f"| {r['example_id']} | {r['gold']['severity']} | {r['pred']['severity']} | "
                 f"{r['severity_delta']:+d} | {r['domain_jaccard']:.2f} | {r['driver_jaccard']:.2f} | {r['bucket']} |")
    L.append("")
    if missing:
        L.append("Missing predictions: " + ", ".join(missing))

    (out_dir / "summary.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main()
