"""Run LLM inference on a dataset split.

Usage:
    python src/run.py --strategy zero-shot --version v1 --limit 5                     # new run
    python src/run.py --strategy zero-shot --version v1 --run-id <run_id> --limit 15  # continue it
    python src/run.py --strategy zero-shot --version v1 --run-id <run_id>             # finish the rest

    # few-shot: --selection random|bm25|bm25-action, --k N (needs a top_n >= N selection file), --seed for random (default 0)
    python src/run.py --strategy few-shot --selection random --seed 0 --k 3 --version v1 --dry-run
    python src/run.py --strategy few-shot --selection bm25 --k 3 --version v1 --limit 5

    # single-task: --task picks the subtask and the prompt family (docs/single-task/00-common.md)
    python src/run.py --task task1 --version answer-v1 --strategy zero-shot
    python src/run.py --task task1 --version reason-v1 --strategy few-shot --selection bm25 --k 10

Every batch of one run writes into the same results/<model>/<task>/<experiment>/<run_id>/ directory,
where <task> is multitask, task1, task2a or task2b, and <experiment> is zero-shot-v1,
few-shot-bm25-k3-answer-v1, ... Samples that already have a valid prediction are skipped, so a run
can be stopped and resumed anytime.
Runs on a split other than dev, or with --smoke, go to results/_smoke/ (not committed).
--dry-run builds every request, checks it and prints the first one, without calling the API.
--concurrency N sends N requests at a time; the on-disk records and the resume logic are unchanged.
"""
import argparse
import gzip
import hashlib
import json
import os
import platform
import random
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import openai
from openai import OpenAI

import fewshot
from common import TASKS, load_jsonl, unpack_prediction, validate_prediction

ROOT = Path(__file__).resolve().parent.parent
MAX_ATTEMPTS = 3
# Multi-task versions, keyed by the exact version string: v4 isolates a brief rationale before
# labels; all released earlier versions stay label-only. v4b is v4 with a format reminder on the
# final user turn (prompts/few_shot_v4b.json): the label-only demonstrations otherwise pull the
# model back to bare labels. Same output format. v5 is v4 plus rules distilled from v4's own
# rationales (prompts/patches/v5), so it still answers in reasoning + answer.
# Single-task versions do NOT use this table: their lineage (answer- / reason-) says the format,
# which is why the naming is <lineage>-v<N> (docs/single-task/00-common.md section 3.2).
OUTPUT_FORMATS = {"v4": "reasoning-answer-v1", "v4b": "reasoning-answer-v1",
                  "v5": "reasoning-answer-v1"}
SINGLE_VERSION_RE = re.compile(r"^(answer|reason|facts)-v\d+$")
LINEAGE_FORMATS = {"answer": "labels", "reason": "reasoning-answer-v1",
                   "facts": "facts-judgment-answer-v1"}  # docs/agentic-distill/00-common.md
PARAMS = dict(
    model="deepseek-flash",
    temperature=0,
    max_tokens=1024,
    response_format={"type": "json_object"},
    extra_body={"thinking": {"type": "disabled"}},
    stream=False,
)
RETRYABLE = (
    openai.APIConnectionError,  # includes timeouts
    openai.RateLimitError,
    openai.InternalServerError,
)

_client = None
_client_lock = threading.Lock()


def get_client():
    # created on first use so --dry-run works without an API key
    global _client
    with _client_lock:
        if _client is None:
            _client = OpenAI(
                api_key=os.environ["DEEPSEEK_API_KEY"],
                base_url="https://api.deepseek.com",
                timeout=120.0,
                max_retries=0,  # 由 runner 统一记录并处理重试
            )
    return _client


def norm_ws(text):
    return re.sub(r"\s+", " ", text or "").strip()


def file_version(version):
    """Command line and directory names use hyphens; prompt file names use underscores."""
    return version.replace("-", "_")


def task_dir_name(task):
    return "multitask" if task == "multi" else task


def prompt_dir(task):
    return ROOT / "prompts" if task == "multi" else ROOT / "prompts" / "single" / task


def output_format_for(task, version):
    if task == "multi":
        return OUTPUT_FORMATS.get(version, "labels")
    if not SINGLE_VERSION_RE.match(version):
        sys.exit(f"single-task --version must look like answer-v1 or reason-v2, got {version!r}")
    return LINEAGE_FORMATS[version.split("-", 1)[0]]


def zero_shot_messages(row, system_prompt):
    payload = {
        "formatted_interaction": row["formatted_interaction"],
        "proposed_action": row["proposed_action"],
    }
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]


def request(messages):
    return get_client().chat.completions.create(messages=messages, **PARAMS)


def parse(response):
    choice = response.choices[0]
    if choice.finish_reason != "stop" or not choice.message.content:
        raise ValueError("Incomplete or empty response; record and retry")
    return json.loads(choice.message.content)


def predict_one(row, system_prompt, task="multi"):
    response = request(zero_shot_messages(row, system_prompt))
    return parse(response), response.model_dump(mode="json")


def sha256_of(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def append_jsonl(path, record):
    """Append one line and force it to disk before returning."""
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())


def now():
    return datetime.now(timezone.utc).isoformat()


def experiment_name(args):
    if args.strategy == "zero-shot":
        return f"zero-shot-{args.version}"
    if args.selection == "random":
        return f"few-shot-random-s{args.seed}-k{args.k}-{args.version}"
    return f"few-shot-{args.selection}-k{args.k}-{args.version}"


def setup_run_dir(args, prompt_text, prompt_path, data_path, manifest, extra):
    """extra: fields recorded in config.json and checked again when a run is resumed."""
    smoke = args.smoke or args.split != "dev"
    exp_dir = (ROOT / "results" / ("_smoke" if smoke else "deepseek-flash")
               / task_dir_name(args.task) / experiment_name(args))
    prompt_hash = hashlib.sha256(prompt_text.encode("utf-8")).hexdigest()

    if args.run_id is None:
        run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
        run_dir = exp_dir / run_id
        run_dir.mkdir(parents=True)
        (run_dir / "prompt.txt").write_text(prompt_text, encoding="utf-8")
        config = {
            "run_id": run_id,
            "experiment": exp_dir.name,
            "strategy": args.strategy,
            "version": args.version,
            "split": args.split,
            "created_at": now(),
            "params": PARAMS,
            "prompt_file": str(prompt_path.relative_to(ROOT)),
            "prompt_sha256": prompt_hash,
            "data_file": str(data_path.relative_to(ROOT)),
            "data_sha256": sha256_of(data_path),
            "data_hf_commit_sha": manifest["hf_commit_sha"],
            **extra,
            "openai_sdk_version": openai.__version__,
            "python_version": platform.python_version(),
            "returned_models": [],
            "invocations": [],
        }
        (run_dir / "config.json").write_text(json.dumps(config, indent=2) + "\n")
        return run_dir

    run_dir = exp_dir / args.run_id
    if not run_dir.is_dir():
        sys.exit(f"run dir not found: {run_dir}")
    config = json.loads((run_dir / "config.json").read_text())
    if config["prompt_sha256"] != prompt_hash or config["split"] != args.split:
        sys.exit("prompt or split differs from this run; start a new run (new prompt version) instead")
    if config["data_sha256"] != sha256_of(data_path):
        sys.exit("data file differs from this run; start a new run instead")
    for key, value in extra.items():
        if config.get(key) != value:
            sys.exit(f"{key} differs from this run; start a new run instead")
    return run_dir


def few_shot_context(args, manifest):
    """Returns (system_prompt_path, build, extra); build(row) -> (messages, shot_ids)."""
    spec_path, spec = fewshot.load_spec(args.version, args.task)
    sel_path, sel = fewshot.load_selection(args.selection, args.seed, args.k, args.split)
    for name, key in (("train.jsonl", "train_sha256"), ("dev.jsonl", "dev_sha256")):
        recorded = sel["meta"].get(key)
        if recorded is not None and recorded != manifest["files"][name]["sha256"]:
            sys.exit(f"{sel_path.name} was made from a different {name}; regenerate the selection file")
    shortest = min(len(v) for v in sel["selections"].values())
    if shortest < args.k:
        sys.exit(f"{sel_path.name} has only {shortest} examples per sample; "
                 f"run src/select_examples.py --top-n {args.k} first")
    train = {r["example_id"]: r for r in load_jsonl(ROOT / "data" / "raw" / "train.jsonl")}
    prompt_path = ROOT / spec["system_prompt_file"]
    system_prompt = prompt_path.read_text(encoding="utf-8")

    def build(row):
        eid = row["example_id"]
        if eid not in sel["selections"]:
            sys.exit(f"{eid} has no entry in {sel_path.name}; "
                     f"build a selection for the '{args.split}' split with src/select_examples_for_split.py")
        shot_ids = fewshot.pick_shot_ids(args.selection, sel["selections"][eid], args.k)
        examples = [train[i] for i in shot_ids]
        return fewshot.build_messages(row, system_prompt, spec, examples), shot_ids

    extra = {
        "selection": args.selection,
        "seed": args.seed if args.selection == "random" else None,
        "k": args.k,
        "selection_file": str(sel_path.relative_to(ROOT)),
        "selection_sha256": fewshot.sha256_of(sel_path),
        "spec_file": str(spec_path.relative_to(ROOT)),
        "spec_sha256": fewshot.sha256_of(spec_path),
    }
    return prompt_path, build, extra


def dry_run(args, rows, build, system_prompt):
    """Build and check every request without calling the API; print the first one."""
    chars, longest, first = [], 0, None
    for row in rows:
        messages, shot_ids = build(row)
        shot_ids = shot_ids or []
        roles = [m["role"] for m in messages]
        assert roles == ["system"] + ["user", "assistant"] * len(shot_ids) + ["user"], roles
        assert len(set(shot_ids)) == len(shot_ids) == (args.k or 0), shot_ids
        assert row["example_id"] not in shot_ids, f"{row['example_id']} is in its own examples"
        assert messages[0]["content"] == system_prompt
        for m in messages:
            if m["role"] == "assistant":
                validate_prediction(json.loads(m["content"]), args.task)
        n = sum(len(m["content"]) for m in messages)
        chars.append(n)
        longest = max(longest, n)
        first = first or (row["example_id"], messages, shot_ids)
    total = sum(chars)
    print(f"dry run OK: {len(rows)} requests built and checked, no API call")
    print(f"task: {args.task}; version: {args.version}; "
          f"output format: {output_format_for(args.task, args.version)}")
    print(f"system prompt sha256: {hashlib.sha256(system_prompt.encode('utf-8')).hexdigest()[:12]}")
    print(f"chars per request: mean {total // len(rows):,}, max {longest:,}; total {total:,}")
    print(f"rough input tokens (chars/4, not a tokenizer): total {total // 4:,}, longest {longest // 4:,}")
    print(f"\n# {first[0]}; examples (prompt order): {first[2]}\n")
    print(fewshot.format_messages(first[1]))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", choices=list(TASKS), default="multi",
                        help="multi (joint prediction, the default) or one subtask")
    parser.add_argument("--strategy", choices=["zero-shot", "few-shot"], default="zero-shot")
    parser.add_argument("--version", default="v1")
    parser.add_argument("--split", default="dev",
                        help="named split under data/raw/; also names the few-shot selection query split")
    parser.add_argument("--data-file", default=None,
                        help="explicit jsonl input, e.g. data/splits/train_val.jsonl (overrides --split for input)")
    parser.add_argument("--selection", choices=["random", "bm25", "bm25-action"], help="few-shot only")
    parser.add_argument("--k", type=int, help="few-shot only: number of examples (needs a selection with top_n >= k)")
    parser.add_argument("--seed", type=int, default=0, help="random selection only")
    parser.add_argument("--run-id", default=None, help="continue an existing run")
    parser.add_argument("--limit", type=int, default=None, help="process at most N more samples")
    parser.add_argument("--concurrency", type=int, default=1, help="requests in flight at once")
    parser.add_argument("--smoke", action="store_true", help="write to results/_smoke/ (not committed)")
    parser.add_argument("--dry-run", action="store_true", help="build and check requests, no API call")
    args = parser.parse_args()

    if args.strategy == "few-shot":
        if args.selection is None or args.k is None:
            parser.error("--strategy few-shot needs --selection and --k")
        if args.k < 1:
            parser.error("--k must be a positive integer")
    elif args.selection is not None or args.k is not None:
        parser.error("--selection and --k only apply to --strategy few-shot")
    if args.concurrency < 1:
        parser.error("--concurrency must be a positive integer")

    if args.data_file:
        data_path = Path(args.data_file)
        if not data_path.is_absolute():
            data_path = ROOT / data_path
    else:
        data_path = ROOT / "data" / "raw" / f"{args.split}.jsonl"
    manifest = json.loads((ROOT / "data" / "MANIFEST.json").read_text())
    # only files pinned in MANIFEST are hash-checked; derived splits (see src/make_splits.py) are not
    pinned = manifest["files"].get(data_path.name, {}).get("sha256")
    if pinned is not None and sha256_of(data_path) != pinned:
        sys.exit(f"{data_path.name} does not match data/MANIFEST.json; run src/download_data.py")

    output_format = output_format_for(args.task, args.version)

    if args.strategy == "few-shot":
        prompt_path, build, extra = few_shot_context(args, manifest)
        prompt_text = prompt_path.read_text(encoding="utf-8")
    else:
        prompt_path = prompt_dir(args.task) / f"{args.strategy.replace('-', '_')}_{file_version(args.version)}.txt"
        if not prompt_path.exists():
            sys.exit(f"prompt not found: {prompt_path.relative_to(ROOT)}")
        prompt_text = prompt_path.read_text(encoding="utf-8")
        extra = {}

        def build(row):
            return zero_shot_messages(row, prompt_text), None

    # task and prompt_id are checked on resume, so a run can never mix two tasks
    extra["task"] = args.task
    extra["prompt_id"] = f"{args.task}-{args.version}"
    if output_format != "labels":
        extra["output_format"] = output_format

    rows = load_jsonl(data_path)
    if args.dry_run:
        dry_run(args, rows, build, prompt_text)
        return

    run_dir = setup_run_dir(args, prompt_text, prompt_path, data_path, manifest, extra)
    pred_path = run_dir / "predictions.jsonl"
    raw_path = run_dir / "raw_responses.jsonl"
    messages_path = run_dir / "messages.jsonl.gz"
    recorded = set(fewshot.read_messages_file(messages_path)) if messages_path.exists() else set()
    if args.strategy == "few-shot" and not (run_dir / "prompt_preview.txt").exists():
        eid, (messages, shot_ids) = rows[0]["example_id"], build(rows[0])
        (run_dir / "prompt_preview.txt").write_text(
            f"# {eid}; examples (prompt order): {shot_ids}\n\n" + fewshot.format_messages(messages),
            encoding="utf-8",
        )

    done = {r["example_id"] for r in load_jsonl(pred_path)} if pred_path.exists() else set()
    todo = [r for r in rows if r["example_id"] not in done]
    if args.limit is not None:
        todo = todo[: args.limit]
    print(f"run {run_dir.name} [{args.task}/{experiment_name(args)}]: {len(done)}/{len(rows)} done, "
          f"processing {len(todo)} now at concurrency {args.concurrency}", flush=True)

    started = now()
    lock = threading.Lock()
    stop = threading.Event()
    state = {"ok": 0, "failed": [], "models": set(), "fatal": None,
             "usage": {"prompt_tokens": 0, "completion_tokens": 0}}

    def process(row):
        eid = row["example_id"]
        if stop.is_set():
            return
        messages, shot_ids = build(row)
        if shot_ids is not None or output_format != "labels":
            # the exact messages are saved before the request, so the record exists even if the call fails
            with lock:
                if eid not in recorded:
                    with gzip.open(messages_path, "at", encoding="utf-8") as f:
                        f.write(json.dumps({"example_id": eid, "shot_ids": shot_ids,
                                            "messages": messages}, ensure_ascii=False) + "\n")
                    recorded.add(eid)
        for attempt in range(1, MAX_ATTEMPTS + 1):
            if stop.is_set():
                return
            t0 = time.time()
            rec = {"example_id": eid, "attempt": attempt, "time": now()}
            if shot_ids is not None:
                rec["shot_ids"] = shot_ids
            prediction, fatal = None, None
            try:
                response = request(messages)
                rec["response"] = response.model_dump(mode="json")
                with lock:
                    state["models"].add(response.model)
                    if response.usage:
                        state["usage"]["prompt_tokens"] += response.usage.prompt_tokens
                        state["usage"]["completion_tokens"] += response.usage.completion_tokens
                prediction, reasoning = unpack_prediction(parse(response), output_format, args.task)
                if isinstance(reasoning, dict):   # facts lineage: keep both parts, check quotes
                    rec["facts"], rec["judgment"] = reasoning["facts"], reasoning["judgment"]
                    hay = norm_ws(row["formatted_interaction"] + "\n" + row["proposed_action"])
                    rec["facts_quote_ok"] = [norm_ws(f["quote"]) in hay for f in reasoning["facts"]]
                elif reasoning is not None:
                    rec["reasoning"] = reasoning
                rec["status"] = "ok"
            except RETRYABLE as e:
                rec.update(status="api_error", error=repr(e))
            except openai.BadRequestError as e:  # e.g. context too long: this sample fails, the run goes on
                rec.update(status="bad_request", error=repr(e))
            except openai.OpenAIError as e:  # auth, ...: fix the config, do not retry
                rec.update(status="fatal_error", error=repr(e))
                fatal = e
            except ValueError as e:  # empty/truncated/invalid JSON/invalid labels
                rec.update(status="invalid_output", error=repr(e))
            rec["seconds"] = round(time.time() - t0, 2)
            with lock:
                append_jsonl(raw_path, rec)  # raw response is on disk before anything else happens

            if fatal is not None:
                with lock:
                    state["fatal"] = fatal
                    state["failed"].append(eid)
                stop.set()
                return
            if rec["status"] == "ok":
                with lock:
                    append_jsonl(pred_path, {"example_id": eid, **prediction})
                    state["ok"] += 1
                print(f"  {eid} ok", flush=True)
                return
            print(f"  {eid} attempt {attempt} {rec['status']}: {rec['error']}", flush=True)
            if rec["status"] == "bad_request":  # retrying the same request cannot help
                with lock:
                    state["failed"].append(eid)
                return
            if attempt < MAX_ATTEMPTS:
                time.sleep(2**attempt + random.random())
        with lock:
            state["failed"].append(eid)

    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        for future in [pool.submit(process, row) for row in todo]:
            future.result()  # re-raise anything the worker did not handle

    failed = sorted(state["failed"])
    config_path = run_dir / "config.json"
    config = json.loads(config_path.read_text())
    config["returned_models"] = sorted(set(config["returned_models"]) | state["models"])
    config["invocations"].append(
        {"started": started, "finished": now(), "limit": args.limit, "succeeded": state["ok"],
         "failed_ids": failed, **state["usage"]}
    )
    config_path.write_text(json.dumps(config, indent=2) + "\n")

    total_done = len(done) + state["ok"]
    print(f"this invocation: {state['ok']} ok, {len(failed)} failed {failed}; tokens {state['usage']}")
    print(f"run total: {total_done}/{len(rows)} valid predictions in {run_dir}")
    if state["fatal"] is not None:
        sys.exit("stopped on a non-retryable API error; see raw_responses.jsonl")


if __name__ == "__main__":
    main()
