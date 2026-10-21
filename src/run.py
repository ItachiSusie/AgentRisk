"""Run LLM inference on a dataset split.

Usage:
    python src/run.py --strategy zero-shot --version v1 --limit 5                     # new run
    python src/run.py --strategy zero-shot --version v1 --run-id <run_id> --limit 15  # continue it
    python src/run.py --strategy zero-shot --version v1 --run-id <run_id>             # finish the rest

Every batch of one run writes into the same results/<model>/<strategy>-<version>/<run_id>/ directory.
Samples that already have a valid prediction are skipped, so a run can be stopped and resumed anytime.
Runs on a split other than dev go to results/_smoke/ (not committed) so they never mix with dev runs.
"""
import argparse
import hashlib
import json
import os
import platform
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import openai
from openai import OpenAI

from common import load_jsonl, validate_prediction

ROOT = Path(__file__).resolve().parent.parent
MAX_ATTEMPTS = 3
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

client = OpenAI(
    api_key=os.environ["DEEPSEEK_API_KEY"],
    base_url="https://api.deepseek.com",
    timeout=120.0,
    max_retries=0,  # 由 runner 统一记录并处理重试
)


def request(row, system_prompt):
    payload = {
        "formatted_interaction": row["formatted_interaction"],
        "proposed_action": row["proposed_action"],
    }
    return client.chat.completions.create(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ],
        **PARAMS,
    )


def parse(response):
    choice = response.choices[0]
    if choice.finish_reason != "stop" or not choice.message.content:
        raise ValueError("Incomplete or empty response; record and retry")
    return json.loads(choice.message.content)


def predict_one(row, system_prompt):
    response = request(row, system_prompt)
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


def setup_run_dir(args, prompt_text, prompt_path, data_path, manifest):
    base = ROOT / "results" / ("deepseek-flash" if args.split == "dev" else "_smoke")
    exp_dir = base / f"{args.strategy}-{args.version}"
    prompt_hash = hashlib.sha256(prompt_text.encode("utf-8")).hexdigest()

    if args.run_id is None:
        run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
        run_dir = exp_dir / run_id
        run_dir.mkdir(parents=True)
        (run_dir / "prompt.txt").write_text(prompt_text, encoding="utf-8")
        config = {
            "run_id": run_id,
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
    return run_dir


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--strategy", default="zero-shot")
    parser.add_argument("--version", default="v1")
    parser.add_argument("--split", default="dev")
    parser.add_argument("--run-id", default=None, help="continue an existing run")
    parser.add_argument("--limit", type=int, default=None, help="process at most N more samples")
    args = parser.parse_args()

    prompt_path = ROOT / "prompts" / f"{args.strategy.replace('-', '_')}_{args.version}.txt"
    prompt_text = prompt_path.read_text(encoding="utf-8")
    data_path = ROOT / "data" / "raw" / f"{args.split}.jsonl"
    manifest = json.loads((ROOT / "data" / "MANIFEST.json").read_text())
    pinned = manifest["files"][data_path.name]["sha256"]
    if sha256_of(data_path) != pinned:
        sys.exit(f"{data_path.name} does not match data/MANIFEST.json; run src/download_data.py")

    rows = load_jsonl(data_path)
    run_dir = setup_run_dir(args, prompt_text, prompt_path, data_path, manifest)
    pred_path = run_dir / "predictions.jsonl"
    raw_path = run_dir / "raw_responses.jsonl"

    done = {r["example_id"] for r in load_jsonl(pred_path)} if pred_path.exists() else set()
    todo = [r for r in rows if r["example_id"] not in done]
    if args.limit is not None:
        todo = todo[: args.limit]
    print(f"run {run_dir.name}: {len(done)}/{len(rows)} done, processing {len(todo)} now", flush=True)

    started = now()
    returned_models, failed, ok_count, fatal = set(), [], 0, None
    usage = {"prompt_tokens": 0, "completion_tokens": 0}

    for row in todo:
        eid = row["example_id"]
        for attempt in range(1, MAX_ATTEMPTS + 1):
            t0 = time.time()
            rec = {"example_id": eid, "attempt": attempt, "time": now()}
            prediction, fatal = None, None
            try:
                response = request(row, prompt_text)
                rec["response"] = response.model_dump(mode="json")
                returned_models.add(response.model)
                if response.usage:
                    usage["prompt_tokens"] += response.usage.prompt_tokens
                    usage["completion_tokens"] += response.usage.completion_tokens
                prediction = parse(response)
                validate_prediction(prediction)
                rec["status"] = "ok"
            except RETRYABLE as e:
                rec.update(status="api_error", error=repr(e))
            except openai.OpenAIError as e:  # auth, bad request, ...: fix the config, do not retry
                rec.update(status="fatal_error", error=repr(e))
                fatal = e
            except ValueError as e:  # empty/truncated/invalid JSON/invalid labels
                rec.update(status="invalid_output", error=repr(e))
            rec["seconds"] = round(time.time() - t0, 2)
            append_jsonl(raw_path, rec)  # raw response is on disk before anything else happens

            if fatal is not None:
                break
            if rec["status"] == "ok":
                append_jsonl(pred_path, {"example_id": eid, **prediction})
                ok_count += 1
                print(f"  {eid} ok", flush=True)
                break
            print(f"  {eid} attempt {attempt} {rec['status']}: {rec['error']}", flush=True)
            if attempt < MAX_ATTEMPTS:
                time.sleep(2**attempt + random.random())
        else:
            failed.append(eid)
        if fatal is not None:
            failed.append(eid)
            break

    config_path = run_dir / "config.json"
    config = json.loads(config_path.read_text())
    config["returned_models"] = sorted(set(config["returned_models"]) | returned_models)
    config["invocations"].append(
        {"started": started, "finished": now(), "limit": args.limit, "succeeded": ok_count,
         "failed_ids": failed, **usage}
    )
    config_path.write_text(json.dumps(config, indent=2) + "\n")

    total_done = len(done) + ok_count
    print(f"this invocation: {ok_count} ok, {len(failed)} failed {failed}; tokens {usage}")
    print(f"run total: {total_done}/{len(rows)} valid predictions in {run_dir}")
    if fatal is not None:
        sys.exit("stopped on a non-retryable API error; see raw_responses.jsonl")


if __name__ == "__main__":
    main()
