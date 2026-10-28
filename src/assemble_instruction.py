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
ANCHOR = "Return only a JSON object"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="prompts/zero_shot_v1.txt")
    ap.add_argument("--patches", nargs="+", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--title", default="Decision rules distilled from training errors")
    args = ap.parse_args()

    base = (ROOT / args.base).read_text(encoding="utf-8")
    if ANCHOR not in base:
        raise SystemExit(f"anchor {ANCHOR!r} not found in {args.base}")
    head, tail = base.split(ANCHOR, 1)

    rules = []
    for p in args.patches:
        text = (ROOT / p).read_text(encoding="utf-8").strip()
        if not text:
            raise SystemExit(f"empty patch: {p}")
        rules.append(text)

    block = (f"{args.title}. Each rule names the condition it applies to, the decision it forces, "
             f"and a counter-example that must not get the rule.\n\n"
             + "\n\n".join(rules) + "\n\n")
    out_text = head.rstrip() + "\n\n" + block + ANCHOR + tail

    out_path = ROOT / args.out
    out_path.write_text(out_text, encoding="utf-8")
    base_words = len(base.split())
    print(f"wrote {args.out}: {len(rules)} rules, {base_words} -> {len(out_text.split())} words "
          f"({(len(out_text.split()) / base_words - 1) * 100:+.0f}%)")


if __name__ == "__main__":
    main()
