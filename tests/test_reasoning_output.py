"""Offline checks for v4 output handling; no SDK, model call or real dataset needed."""
import gzip
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from common import load_jsonl, unpack_prediction
import evaluate
import fewshot

LABELS = {"risk_severity": 1, "risk_domains": ["No Material Harm"],
          "risk_drivers": ["No Material Risk"]}
RATIONALE = "The action refuses disclosure and does not execute the unsafe request."


class OutputTests(unittest.TestCase):
    def test_old_and_new_formats(self):
        self.assertEqual(unpack_prediction(LABELS), (LABELS, None))
        self.assertEqual(unpack_prediction({"reasoning": RATIONALE, "answer": LABELS},
                                          "reasoning-answer-v1"), (LABELS, RATIONALE))

    def test_invalid_outputs_cannot_be_scored(self):
        for output in [LABELS, {"answer": LABELS}, {"reasoning": "", "answer": LABELS},
                       {"reasoning": "  ", "answer": LABELS},
                       {"reasoning": [], "answer": LABELS},
                       {"reasoning": RATIONALE, "answer": dict(LABELS, risk_severity=6)},
                       {"reasoning": RATIONALE, "answer": LABELS, "extra": True}]:
            with self.subTest(output=output), self.assertRaises(ValueError):
                unpack_prediction(output, "reasoning-answer-v1")
        with self.assertRaises(ValueError):
            unpack_prediction({"reasoning": RATIONALE, "answer": LABELS})

    def test_only_output_instruction_changes_and_shots_stay_label_only(self):
        old = (ROOT / "prompts/zero_shot_v1.txt").read_text()
        new = (ROOT / "prompts/zero_shot_v4.txt").read_text()
        self.assertEqual(old.split("Return only a JSON object")[0],
                         new.split("For the final sample")[0])
        _, spec = fewshot.load_spec("v4")
        example = dict(LABELS, example_id="train-example", formatted_interaction="History",
                       proposed_action="Refuse")
        query = dict(example, example_id="query")
        messages = fewshot.build_messages(query, new, spec, [example])
        self.assertEqual([m["role"] for m in messages], ["system", "user", "assistant", "user"])
        self.assertEqual(json.loads(messages[2]["content"]), LABELS)
        self.assertEqual(set(json.loads(messages[-1]["content"])),
                         {"formatted_interaction", "proposed_action"})


class RunnerTests(unittest.TestCase):
    def test_retry_logging_label_extraction_and_resume(self):
        # Replace only the unavailable SDK import. The runner itself and file I/O are real.
        sdk = types.ModuleType("openai")
        sdk.__version__ = "offline-test"
        sdk.OpenAI = object
        for name in ["APIConnectionError", "RateLimitError", "InternalServerError",
                     "BadRequestError", "OpenAIError"]:
            setattr(sdk, name, type(name, (Exception,), {}))
        spec = importlib.util.spec_from_file_location("offline_runner", ROOT / "src/run.py")
        runner = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {"openai": sdk}):
            spec.loader.exec_module(runner)

        def response(output):
            return types.SimpleNamespace(
                choices=[types.SimpleNamespace(finish_reason="stop", message=types.SimpleNamespace(
                    content=json.dumps(output)))], model="offline-model", usage=None,
                model_dump=lambda **kw: {"choices": [{"message": {"content": json.dumps(output)}}]})

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "prompts").mkdir()
            (root / "prompts/zero_shot_v4.txt").write_text(
                (ROOT / "prompts/zero_shot_v4.txt").read_text())
            (root / "data/raw").mkdir(parents=True)
            row = {"example_id": "test-query", "formatted_interaction": "Refuse unsafe request",
                   "proposed_action": "Refuse", **LABELS}
            (root / "data/raw/train_val.jsonl").write_text(json.dumps(row) + "\n")
            (root / "data/MANIFEST.json").write_text(json.dumps(
                {"hf_commit_sha": "offline-test", "files": {}}))
            args = ["run.py", "--version", "v4", "--split", "train_val"]
            outputs = [response({"reasoning": "", "answer": LABELS}),
                       response({"reasoning": RATIONALE, "answer": LABELS})]
            with patch.object(runner, "ROOT", root), patch.object(sys, "argv", args), \
                    patch.object(runner, "request", side_effect=outputs) as request, \
                    patch.object(runner.time, "sleep"):
                runner.main()
                self.assertEqual(request.call_count, 2)
                run_dir, = (root / "results/_smoke/zero-shot-v4").iterdir()
                self.assertEqual(load_jsonl(run_dir / "predictions.jsonl"),
                                 [{"example_id": "test-query", **LABELS}])
                raw = load_jsonl(run_dir / "raw_responses.jsonl")
                self.assertEqual([r["status"] for r in raw], ["invalid_output", "ok"])
                self.assertEqual(raw[-1]["reasoning"], RATIONALE)
                with gzip.open(run_dir / "messages.jsonl.gz", "rt") as f:
                    messages = [json.loads(line) for line in f]
                self.assertEqual(len(messages), 1)
                self.assertEqual(messages[0]["messages"][1]["content"], request.call_args.args[0][1]["content"])
                self.assertEqual(json.loads((run_dir / "config.json").read_text())["output_format"],
                                 "reasoning-answer-v1")
                with patch.object(evaluate, "ROOT", root), \
                        patch.object(sys, "argv", ["evaluate.py", str(run_dir)]):
                    evaluate.main()
                metrics = json.loads((run_dir / "metrics.json").read_text())
                self.assertTrue(metrics["complete"])
                self.assertEqual(metrics["task1_mae"], 0)
                self.assertEqual(metrics["task2a_mean_jaccard"], 1)
                self.assertEqual(metrics["task2b_mean_jaccard"], 1)
                with patch.object(sys, "argv", args + ["--run-id", run_dir.name]):
                    runner.main()
                self.assertEqual(request.call_count, 2)
                with gzip.open(run_dir / "messages.jsonl.gz", "rt") as f:
                    self.assertEqual(len(f.readlines()), 1)


if __name__ == "__main__":
    unittest.main()
