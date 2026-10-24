"""Few-shot helpers: load selections, build the chat messages, and show what a run actually sent.

Usage:
    python src/fewshot.py render --run-dir results/deepseek-flash/<experiment>/<run_id> --id AGENTRISK-004

The message layout is defined by prompts/few_shot_<version>.json (never edit a released version).
Examples are chat turns: system prompt, then (user, assistant) x k, then the sample to assess.
"""
import argparse
import gzip
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FEWSHOT_DIR = ROOT / "data" / "fewshot"
RANKED = ("bm25", "bm25-action")  # selections stored most-similar-first


def sha256_of(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_spec(version):
    path = ROOT / "prompts" / f"few_shot_{version}.json"
    return path, json.loads(path.read_text(encoding="utf-8"))


def selection_path(selection, seed):
    name = {
        "random": f"random_seed{seed}.json",
        "bm25": "bm25_dev_top10.json",
        "bm25-action": "bm25_action_dev_top10.json",
    }[selection]
    return FEWSHOT_DIR / name


def load_selection(selection, seed):
    path = selection_path(selection, seed)
    if not path.exists():
        sys.exit(f"selection file not found: {path}; run src/select_examples.py")
    return path, json.loads(path.read_text(encoding="utf-8"))


def pick_shot_ids(selection, selected_ids, k):
    """First k ids of the stored list (so k=3 is inside k=5 is inside k=10), in prompt order."""
    ids = list(selected_ids[:k])
    if len(ids) < k:
        raise ValueError(f"selection has only {len(ids)} examples, k={k}")
    # ranked selections put the most similar example last, closest to the sample being assessed
    return ids[::-1] if selection in RANKED else ids


def user_content(row, spec):
    """Same JSON payload as zero-shot, for examples and for the sample being assessed."""
    return json.dumps({key: row[key] for key in spec["user_payload_keys"]}, ensure_ascii=False)


def assistant_content(row, spec):
    return json.dumps({key: row[key] for key in spec["assistant_output_keys"]}, ensure_ascii=False)


def build_messages(row, system_prompt, spec, examples):
    """examples: train rows in prompt order."""
    messages = []
    if spec["preamble"]:
        system_prompt = system_prompt + "\n\n" + spec["preamble"]
    messages.append({"role": "system", "content": system_prompt})
    for ex in examples:
        messages.append({"role": "user", "content": user_content(ex, spec)})
        messages.append({"role": "assistant", "content": assistant_content(ex, spec)})
    messages.append({"role": "user", "content": user_content(row, spec)})
    return messages


def format_messages(messages):
    """Readable text: user JSON payloads are unpacked so newlines show as newlines."""
    parts = []
    shot = 0
    for i, m in enumerate(messages):
        if m["role"] == "system":
            header = "SYSTEM"
            body = m["content"]
        elif m["role"] == "user":
            header = f"USER (example {shot + 1})" if i < len(messages) - 1 else "USER (sample to assess)"
            try:
                payload = json.loads(m["content"])
                body = "\n\n".join(f"{key}:\n{value}" for key, value in payload.items())
            except (json.JSONDecodeError, AttributeError):
                body = m["content"]
        else:
            header = f"ASSISTANT (example {shot + 1} gold answer)"
            body = m["content"]
            shot += 1
        parts.append(f"===== {header} =====\n{body}")
    return "\n\n".join(parts) + "\n"


def read_messages_file(path):
    """example_id -> record; the last record wins if an id was written twice."""
    records = {}
    with gzip.open(path, "rt", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rec = json.loads(line)
                records[rec["example_id"]] = rec
    return records


def render(args):
    path = Path(args.run_dir) / "messages.jsonl.gz"
    if not path.exists():
        sys.exit(f"no messages.jsonl.gz in {args.run_dir}")
    records = read_messages_file(path)
    if args.id not in records:
        sys.exit(f"{args.id} not in {path} ({len(records)} samples recorded)")
    rec = records[args.id]
    print(f"# {args.id}; examples (prompt order): {rec['shot_ids']}\n")
    print(format_messages(rec["messages"]))


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("render", help="print the full messages one sample received")
    p.add_argument("--run-dir", required=True)
    p.add_argument("--id", required=True)
    p.set_defaults(func=render)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
