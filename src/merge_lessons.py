"""Stage 3: consolidate per-failure patches into one instruction patch per theme.

This is the merge operator (M) from the paper: many trajectory-level patches -> one rule per
theme, with recurrence as the signal for what is systematic and what is a one-off.

Usage:
    python src/merge_lessons.py cluster --lessons results/analysis/<name>/lessons.jsonl
    python src/merge_lessons.py merge --lessons ... --instruction prompts/zero_shot_v1.txt \
        --out-dir prompts/patches/v2 --min-support 2

`cluster` is offline. `merge` makes one API call per theme (never per lesson).
"""
import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from common import DOMAINS, DRIVERS, load_jsonl
from run import PARAMS, get_client

ROOT = Path(__file__).resolve().parent.parent
MERGE_PROMPT = ROOT / "prompts" / "merge_v1.txt"

LABELS = list(DOMAINS) + list(DRIVERS)
SHORT = {  # readable theme slugs
    "Scope / Safeguard Failure": "scope-vs-authorization",
    "Authorization / Consent Failure": "scope-vs-authorization",
    "Insufficient Grounding / Uncertainty": "grounding",
    "Untrusted / Conflicting Instructions": "untrusted-instructions",
    "Risky Requested Outcome": "requested-outcome",
    "Execution / Action Hazard": "action-hazard",
    "Privacy / Confidentiality": "privacy-vs-security",
    "Security / System Integrity": "privacy-vs-security",
    "Financial / Assets": "financial",
    "No Material Harm": "no-harm",
    "No Material Risk": "no-harm",
}


def theme_of(lesson):
    """Theme key, in priority order: severity pair > driver involved > domain involved > root cause.

    Counter-examples mention "No Material Harm" on purpose, so scanning the whole patch text
    for labels mis-groups lessons. The gold/prediction diff is the reliable signal.
    """
    gold, pred = lesson.get("gold") or {}, lesson.get("prediction") or {}
    g_sev, p_sev = gold.get("risk_severity"), pred.get("risk_severity")
    if g_sev is not None and p_sev is not None and g_sev != p_sev:
        return f"severity-{g_sev}-vs-{p_sev}"

    for field, order, prefix in (("risk_drivers", DRIVERS, "driver"),
                                 ("risk_domains", DOMAINS, "domain")):
        g = set(gold.get(field) or [])
        p = set(pred.get(field) or [])
        for labels in (g - p, p - g):           # missing first, then extra
            if labels:
                label = sorted(labels, key=lambda l: order.index(l) if l in order else 99)[0]
                return f"{prefix}:{SHORT.get(label) or slug(label)}"
    return f"cause:{lesson.get('root_cause_type', 'unknown')}"


def load_kept(paths):
    kept = []
    for p in paths:
        for rec in load_jsonl(Path(p)):
            if rec.get("status") == "kept":
                kept.append(rec)
    return kept


def slug(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def cmd_cluster(args):
    lessons = load_kept(args.lessons)
    groups = defaultdict(list)
    for l in lessons:
        groups[theme_of(l)].append(l)
    print(f"{len(lessons)} kept lessons -> {len(groups)} themes\n")
    print(f"{'theme':28s} {'support':>7s}  sources")
    for theme, items in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        ids = ",".join(i["example_id"] for i in items[:6])
        print(f"{theme:28s} {len(items):7d}  {ids}{' ...' if len(items) > 6 else ''}")
    low = [t for t, v in groups.items() if len(v) < args.min_support]
    print(f"\nlow-support themes (< {args.min_support}) will go to references/ instead of the main instruction:")
    for t in sorted(low):
        print(f"  {t} ({len(groups[t])})")


def cmd_merge(args):
    lessons = load_kept(args.lessons)
    groups = defaultdict(list)
    for l in lessons:
        groups[theme_of(l)].append(l)
    instruction = (ROOT / args.instruction).read_text(encoding="utf-8")
    merge_sys = MERGE_PROMPT.read_text(encoding="utf-8")
    out_dir = ROOT / args.out_dir
    (out_dir).mkdir(parents=True, exist_ok=True)
    ref_dir = out_dir / "references"
    client = None if args.dry_run else get_client()

    changelog = ["# Instruction patch changelog", "",
                 f"- source lessons: {len(lessons)}",
                 f"- themes: {len(groups)}", ""]
    for theme, items in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        patches = [(i["example_id"], (i["patch"] or {}).get("patch_text", "")) for i in items]
        if args.dry_run:
            print(f"{theme}: {len(items)} patches, {sum(len(p) for _, p in patches)} chars")
            continue
        if len(items) >= args.min_support:
            merged, _ = call_json(client, merge_sys, {
                "instruction": instruction,
                "cluster": [{"source": sid, "patch": p} for sid, p in patches]})
            text = merged.get("patch_text") or ""
            target = out_dir / f"{slug(theme)}.txt"
        else:
            text = "\n\n".join(p for _, p in patches)
            target = ref_dir / f"{slug(theme)}.txt"
            target.parent.mkdir(parents=True, exist_ok=True)
            merged = {"kept_sources": [s for s, _ in patches], "dropped_sources": [],
                      "why": "below min-support: kept verbatim for on-demand reference, not merged into the main instruction"}
        target.write_text(text.strip() + "\n", encoding="utf-8")
        changelog += [f"## {theme} ({len(items)} sources) -> `{target.relative_to(ROOT)}`", "",
                      f"- kept: {', '.join(merged.get('kept_sources') or [])}",
                      f"- dropped: {', '.join(merged.get('dropped_sources') or []) or '—'}",
                      f"- why: {merged.get('why', '')}", ""]
        print(f"{theme}: {len(items)} -> {target.name} ({'main' if len(items) >= args.min_support else 'references'})")

    if not args.dry_run:
        (out_dir / "CHANGELOG.md").write_text("\n".join(changelog) + "\n", encoding="utf-8")
        print(f"wrote {out_dir / 'CHANGELOG.md'}")


def call_json(client, system, payload, retries=2):
    for attempt in range(retries + 1):
        try:
            resp = client.chat.completions.create(
                messages=[{"role": "system", "content": system},
                          {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
                **PARAMS)
            return json.loads(resp.choices[0].message.content), resp
        except (json.JSONDecodeError, TypeError, IndexError):
            if attempt == retries:
                raise


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="command", required=True)
    for name in ("cluster", "merge"):
        p = sub.add_parser(name)
        p.add_argument("--lessons", nargs="+", required=True)
        p.add_argument("--min-support", type=int, default=2)
        if name == "merge":
            p.add_argument("--instruction", default="prompts/zero_shot_v1.txt")
            p.add_argument("--out-dir", default="prompts/patches/v2")
            p.add_argument("--dry-run", action="store_true")
        p.set_defaults(func=cmd_cluster if name == "cluster" else cmd_merge)
    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
