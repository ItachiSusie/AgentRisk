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
import sys
from collections import Counter, defaultdict
from pathlib import Path

from common import DOMAINS, DRIVERS, compute_metrics, jaccard, load_jsonl, task_fields

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
    """Joint prediction: one bucket per sample across all three fields."""
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


def bucket_set(gold, pred, prefix):
    """Single-task multi-label bucket: missing / extra / swap are different defects.

    A model that adds a second label it should not have is doing something different from one
    that misses a label that is there, so the distilled rules have to treat them apart.
    """
    if gold == pred:
        return "exact"
    if gold > pred:
        return f"{prefix}_missing"
    if pred > gold:
        return f"{prefix}_extra"
    return f"{prefix}_swap"


# Buckets printed, in order, per task. Single-task runs never produce the other tasks' buckets.
BUCKETS = {
    "multi": ("exact", "severity_over", "severity_under", "labels_both_wrong",
              "domain_wrong", "driver_wrong"),
    "task1": ("exact", "severity_over", "severity_under"),
    "task2a": ("exact", "domain_missing", "domain_extra", "domain_swap"),
    "task2b": ("exact", "driver_missing", "driver_extra", "driver_swap"),
}
SET_FIELD = {"task2a": ("risk_domains", "domain", DOMAINS),
             "task2b": ("risk_drivers", "driver", DRIVERS)}


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
    ap.add_argument("--task", default=None,
                    help="optional: assert the run is this task (the task is read from config.json)")
    ap.add_argument("--out-dir", default=None)
    ap.add_argument("--examples", type=int, default=10, help="how many error examples to print")
    args = ap.parse_args()

    run_dir = Path(args.run_dir)
    out_dir = Path(args.out_dir) if args.out_dir else run_dir / "triage"
    out_dir.mkdir(parents=True, exist_ok=True)

    config = json.loads((run_dir / "config.json").read_text())
    task = config.get("task", "multi")   # runs predating single-task support are joint
    if args.task and args.task != task:
        sys.exit(f"--task {args.task} but {run_dir}/config.json says task={task}")
    fields = task_fields(task)
    golds = {r["example_id"]: r for r in load_jsonl(ROOT / config["data_file"])}
    preds = {r["example_id"]: r for r in load_jsonl(run_dir / "predictions.jsonl")}

    records = []
    for eid, gold in golds.items():
        pred = preds.get(eid)
        if pred is None:
            records.append({"example_id": eid, "status": "missing"})
            continue
        action = (gold.get("proposed_action") or "").strip()
        rec = {"example_id": eid, "status": "scored", "gold": {}, "pred": {}}
        if task == "multi":
            g_sev, p_sev = gold["risk_severity"], pred["risk_severity"]
            g_dom, p_dom = set(gold["risk_domains"]), set(pred["risk_domains"])
            g_drv, p_drv = set(gold["risk_drivers"]), set(pred["risk_drivers"])
            rec.update({
                "bucket": bucket_of(g_sev == p_sev, g_dom == p_dom, g_drv == p_drv, p_sev - g_sev),
                "gold": {"severity": g_sev, "domains": sorted(g_dom), "drivers": sorted(g_drv)},
                "pred": {"severity": p_sev, "domains": sorted(p_dom), "drivers": sorted(p_drv)},
                "severity_delta": p_sev - g_sev,
                "domain_jaccard": round(jaccard(g_dom, p_dom), 4),
                "driver_jaccard": round(jaccard(g_drv, p_drv), 4),
                "domain_missing": sorted(g_dom - p_dom), "domain_extra": sorted(p_dom - g_dom),
                "driver_missing": sorted(g_drv - p_drv), "driver_extra": sorted(p_drv - g_drv),
            })
        elif task == "task1":
            g_sev, p_sev = gold["risk_severity"], pred["risk_severity"]
            delta = p_sev - g_sev
            rec.update({
                "bucket": "exact" if delta == 0 else ("severity_over" if delta > 0 else "severity_under"),
                "gold": {"severity": g_sev}, "pred": {"severity": p_sev},
                "severity_delta": delta,
            })
        else:
            field, prefix, _ = SET_FIELD[task]
            g, p = set(gold[field]), set(pred[field])
            plural = prefix + "s"
            rec.update({
                "bucket": bucket_set(g, p, prefix),
                "gold": {plural: sorted(g)}, "pred": {plural: sorted(p)},
                f"{prefix}_jaccard": round(jaccard(g, p), 4),
                f"{prefix}_missing": sorted(g - p), f"{prefix}_extra": sorted(p - g),
            })
        rec["refusal_like_action"] = bool(REFUSAL_RE.match(action[:200]))
        rec["proposed_action"] = action[:300]
        records.append(rec)

    scored = [r for r in records if r["status"] == "scored"]
    missing = [r["example_id"] for r in records if r["status"] == "missing"]
    metrics = compute_metrics(preds, golds, task)

    # --- aggregates -------------------------------------------------------
    buckets = Counter(r["bucket"] for r in scored)
    has_sev = "risk_severity" in fields
    conf, by_gold = defaultdict(int), defaultdict(lambda: {"n": 0, "exact": 0, "err": 0})
    if has_sev:
        for r in scored:
            g, delta = r["gold"]["severity"], r["severity_delta"]
            conf[(g, r["pred"]["severity"])] += 1
            by_gold[g]["n"] += 1
            by_gold[g]["exact"] += int(delta == 0)
            by_gold[g]["err"] += abs(delta)

    def set_pairs(plural):
        return [(set(r["gold"][plural]), set(r["pred"][plural])) for r in scored]

    set_tables = []   # (section title, stats, universe, confusion pairs)
    if "risk_domains" in fields:
        pairs = set_pairs("domains")
        set_tables.append(("Domains", label_stats(pairs, DOMAINS), DOMAINS, confusion_pairs(pairs)))
    if "risk_drivers" in fields:
        pairs = set_pairs("drivers")
        set_tables.append(("Drivers", label_stats(pairs, DRIVERS), DRIVERS, confusion_pairs(pairs)))

    def error_rank(r):
        """Worst first, in whatever the task actually measures."""
        sev = -abs(r["severity_delta"]) if has_sev else 0
        js = [r[k] for k in ("domain_jaccard", "driver_jaccard") if k in r]
        return (sev, sum(js) if js else 0)

    refusal = [r for r in scored if r["refusal_like_action"]]
    errors = sorted((r for r in scored if r["bucket"] != "exact"), key=error_rank)

    # --- write jsonl ------------------------------------------------------
    with (out_dir / "triage.jsonl").open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # --- write summary ----------------------------------------------------
    L = []
    L.append(f"# Triage — {config.get('run_id', run_dir.name)}\n")
    L.append(f"- run: `{run_dir}`")
    L.append(f"- model: `{config.get('params', {}).get('model')}` · split: `{config.get('split')}` · data: `{config.get('data_file')}`")
    L.append(f"- task: `{task}` · prompt: `{config.get('prompt_id', config.get('version'))}`")
    L.append(f"- n={metrics['n_total']} · scored={metrics['n_success']} · missing={len(missing)}")
    shown = [(k, v) for k, v in (("MAE", metrics.get("task1_mae")),
                                 ("domain Jaccard", metrics.get("task2a_mean_jaccard")),
                                 ("driver Jaccard", metrics.get("task2b_mean_jaccard"))) if v is not None]
    L.append("- " + " · ".join(f"{k}={v:.3f}" for k, v in shown) + "\n")

    L.append("## 1. Buckets\n")
    L.append("| bucket | n | share of scored |")
    L.append("| --- | --- | --- |")
    for b in BUCKETS[task]:
        n = buckets.get(b, 0)
        L.append(f"| {b} | {n} | {pct(n / len(scored)) if scored else '-'} |")
    L.append("")

    section = 1

    def label_table(title, stats, universe, pairs):
        L.append(f"## {title}\n")
        L.append("| label | gold | pred | correct | missing | extra |")
        L.append("| --- | --- | --- | --- | --- | --- |")
        for lbl in universe:
            st = stats[lbl]
            if st["gold"] == 0 and st["pred"] == 0:
                continue
            L.append(f"| {lbl} | {st['gold']} | {st['pred']} | {st['tp']} | {st['missing']} | {st['extra']} |")
        L.append("")
        if pairs:
            L.append("Top missing→extra pairs: "
                     + "; ".join(f"`{g}`→`{q}` ×{c}" for (g, q), c in pairs) + "\n")

    if has_sev:
        section += 1
        L.append(f"## {section}. Severity confusion (gold → pred)\n")
        L.append("| gold \\ pred | 1 | 2 | 3 | 4 | 5 | total |")
        L.append("| --- | --- | --- | --- | --- | --- | --- |")
        for g in range(1, 6):
            row = [conf.get((g, q), 0) for q in range(1, 6)]
            L.append(f"| **{g}** | " + " | ".join(str(x) for x in row) + f" | {sum(row)} |")
        L.append("| total | " + " | ".join(
            str(sum(conf.get((g, q), 0) for g in range(1, 6))) for q in range(1, 6)) + " | |")
        L.append("")
        L.append("Errors off the diagonal by distance: " + ", ".join(
            f"|Δ|={d}: {sum(conf.get((g, g + d), 0) + conf.get((g, g - d), 0) for g in range(1, 6))}"
            for d in range(1, 5)) + "\n")

        section += 1
        L.append(f"## {section}. By gold severity\n")
        L.append("| gold sev | n | exact | mean abs error |")
        L.append("| --- | --- | --- | --- |")
        for g in sorted(by_gold):
            d = by_gold[g]
            L.append(f"| {g} | {d['n']} | {d['exact']} ({pct(d['exact'] / d['n'])}) | {d['err'] / d['n']:.2f} |")
        L.append("")

    for title, stats, universe, pairs in set_tables:
        section += 1
        label_table(f"{section}. {title}", stats, universe, pairs)

    section += 1
    L.append(f"## {section}. Refusal-like proposed actions (flag only, not a label)\n")
    if refusal:
        L.append(f"{len(refusal)} samples whose `proposed_action` opens as a refusal/clarification.\n")
        keys = sorted(set(k for r in refusal for k in r["gold"]))
        L.append("| id | " + " | ".join(f"gold {k} / pred {k}" for k in keys) + " |")
        L.append("| --- |" + " --- |" * len(keys))
        for r in refusal:
            cells = []
            for k in keys:
                g, q = r["gold"].get(k), r["pred"].get(k)
                fmt = lambda v: ", ".join(v) if isinstance(v, list) else str(v)
                cells.append(f"{fmt(g)} / {fmt(q)}")
            L.append(f"| {r['example_id']} | " + " | ".join(cells) + " |")
    else:
        L.append("none matched the heuristic")
    L.append("")

    section += 1
    L.append(f"## {section}. Top {args.examples} errors (worst first in this task's own metric)\n")
    jkeys = [k for k in ("domain_jaccard", "driver_jaccard") if any(k in r for r in errors)]
    cols = (["gold sev", "pred sev", "Δ"] if has_sev else []) + [k.split("_")[0] + " J" for k in jkeys]
    L.append("| id | " + " | ".join(cols) + " | bucket |")
    L.append("| --- |" + " --- |" * (len(cols) + 1))
    for r in errors[: args.examples]:
        cells = ([str(r["gold"]["severity"]), str(r["pred"]["severity"]), f"{r['severity_delta']:+d}"]
                 if has_sev else [])
        cells += [f"{r[k]:.2f}" for k in jkeys]
        L.append(f"| {r['example_id']} | " + " | ".join(cells) + f" | {r['bucket']} |")
    L.append("")
    if missing:
        L.append("Missing predictions: " + ", ".join(missing))

    (out_dir / "summary.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main()
