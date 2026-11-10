"""Assemble an instruction version from a base instruction plus merged patch files.

Patches live in prompts/patches/<name>/*.txt; each is a TRIGGER / RULE / COUNTER-EXAMPLE block.
The rules are inserted just before the output-format section, so they are read after the label
definitions and before the JSON instruction.

Usage:
    python src/assemble_instruction.py --base prompts/zero_shot_v1.txt \
        --patches prompts/patches/v2/severity-3-vs-4.txt prompts/patches/v2/severity-4-vs-5.txt \
        --out prompts/zero_shot_v2a.txt
"""
import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# Where the output-format section starts. v1-v3 open it with "Return only a JSON object";
# v4 opens it with the brief-rationale paragraph, so in both families the rules land after
# the label definitions and before any instruction about the output. Earliest match wins.
ANCHORS = (
    "For the final sample, first list the facts",   # facts lineage (docs/agentic-distill/)
    "For the final sample, first write a brief",
    "Return only a JSON object",
    "Return only one JSON object",
)


def split_at_anchor(base, label):
    found = sorted((base.index(a), a) for a in ANCHORS if a in base)
    if not found:
        raise SystemExit(f"no output-format anchor found in {label}; tried {ANCHORS}")
    i, anchor = found[0]
    return base[:i], base[i:], anchor


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="prompts/zero_shot_v1.txt")
    ap.add_argument("--patches", nargs="+", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--title", default="Decision rules distilled from training errors")
    args = ap.parse_args()

    base = (ROOT / args.base).read_text(encoding="utf-8")
    head, tail, anchor = split_at_anchor(base, args.base)

    rules = []
    for p in args.patches:
        text = (ROOT / p).read_text(encoding="utf-8").strip()
        if not text:
            raise SystemExit(f"empty patch: {p}")
        rules.append(text)

    block = (f"{args.title}. Each rule names the condition it applies to, the decision it forces, "
             f"and a counter-example that must not get the rule.\n\n"
             + "\n\n".join(rules) + "\n\n")
    out_text = head.rstrip() + "\n\n" + block + tail

    out_path = ROOT / args.out
    out_path.write_text(out_text, encoding="utf-8")
    base_words = len(base.split())
    print(f"wrote {args.out}: {len(rules)} rules before {anchor!r}, "
          f"{base_words} -> {len(out_text.split())} words "
          f"({(len(out_text.split()) / base_words - 1) * 100:+.0f}%)")


if __name__ == "__main__":
    main()
