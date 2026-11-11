"""Offline checks for src/evolve.py (docs/evolve/spec.md section 8). No API call, no real data."""
import hashlib
import json
import random
import shutil
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import evolve  # noqa: E402

SEED = ROOT / "prompts" / "single" / "task2b" / "zero_shot_reason_v1.txt"
SEED_T1 = ROOT / "prompts" / "single" / "task1" / "zero_shot_reason_v1.txt"
AUTH, SCOPE, NONE = "Authorization / Consent Failure", "Scope / Safeguard Failure", "No Material Risk"
VOCAB = ("quorlix vambet trindle osk pelmo fradge ulvan setch brimmo zandle koppit wesra "
         "dulk nimbro faskel yorrit glamb hesp torvin quell").split()
MAGIC = "check whether the granted scope covers the action"
PARAMS = dict(evolve.DEFAULTS)


def make_rows(n_folds=5, per_fold=20):
    rows, folds = {}, []
    for f in range(n_folds):
        ids = []
        for j in range(per_fold):
            eid = f"AGENTRISK-{f * 100 + j:03d}"
            rng = random.Random(eid)
            traj = " ".join(rng.choice(VOCAB) for _ in range(60)) + f" token{f}x{j} end of trajectory"
            gold = [SCOPE] if j % 2 == 0 else ([AUTH] if j % 5 else [NONE])
            rows[eid] = {"example_id": eid, "formatted_interaction": traj, "proposed_action": f"act{f}x{j}",
                         "risk_severity": 3 if j % 2 == 0 else (4 if j % 5 else 1),
                         "risk_domains": ["Privacy / Confidentiality"], "risk_drivers": gold}
            ids.append(eid)
        folds.append(ids)
    return rows, folds


CALLS = Counter()


def fake_predict(text, row, output_format, task, replica):
    """Gold-Scope items with an even index are predicted Authorization unless the prompt has MAGIC."""
    CALLS[(hashlib.sha256(text.encode()).hexdigest(), row["example_id"], replica)] += 1
    gold = row["risk_drivers"]
    idx = int(row["example_id"].split("-")[1]) % 100
    pred = list(gold)
    if gold == [SCOPE] and idx % 4 == 0 and MAGIC not in text:
        pred = [AUTH]
    return {"reasoning": "r", "answer": {"risk_drivers": pred}}, {"prompt_tokens": 10, "completion_tokens": 1}


def fake_propose(system, payload, params):
    usage = {"prompt_tokens": 100, "raw": None}
    if "blind_audit" not in payload:
        return {"items": [{"example_id": it["example_id"], "decisive_facts": [], "reasoning_check": "none",
                           "check_note": "", "own_label": it["prediction"]} for it in payload["items"]]}, usage
    wrong = [it for it in payload["items"] if it["wrong"]]
    fixes = [{"example_id": it["example_id"], "quote": it["trajectory"][-40:]} for it in wrong[:2]]
    edits = [
        {"edit_type": "definition", "op": "replace", "anchor": "Identify factors supported by the trajectory",
         "new_text": "Identify the factors the trajectory supports", "fixes": fixes, "rationale": "neutral"},
        {"edit_type": "pre_check", "op": "insert_after", "anchor": "No Material Risk must be used alone.",
         "new_text": f"Before choosing a driver, {MAGIC}.", "fixes": fixes, "rationale": "magic"},
        {"edit_type": "conditional", "op": "insert_after", "anchor": "not in the prompt", "new_text": "x",
         "fixes": fixes, "rationale": "invalid anchor"},
        {"edit_type": "delete", "op": "delete", "anchor": "Risky Requested Outcome\n", "new_text": "",
         "fixes": fixes, "rationale": "removes a label"},
    ]
    return {"faults": [{"example_id": it["example_id"], "fault": "wrong_rule"} for it in wrong],
            "edits": edits}, usage


class SyntheticRun(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.rows, self.folds = make_rows()
        self._orig = evolve.load_data
        rows, folds = self.rows, self.folds
        evolve.load_data = lambda limit=None, check_folds=True: (
            rows, [f[:limit] if limit else f for f in folds],
            {"manifest_sha256": "m", "train_evolve_sha256": "t"})
        CALLS.clear()

    def tearDown(self):
        evolve.load_data = self._orig
        shutil.rmtree(self.tmp)

    def init(self, *extra, seed=SEED, task="task2b"):
        return evolve.main(["init", "--dry-run", "--task", task, "--seed", str(seed), "--out-root",
                            str(self.tmp), "--run-id", "t", *extra])

    def evolver(self, run_dir, **kw):
        kw.setdefault("predict_fn", fake_predict)
        kw.setdefault("propose_fn", fake_propose)
        return evolve.Evolver(run_dir, concurrency=4, log=lambda *a: None, **kw)


# ---------------------------------------------------------------- 4.5 edit validation
class EditValidation(unittest.TestCase):
    def setUp(self):
        self.prompt = SEED.read_text()
        rows, _ = make_rows(1, 6)
        self.batch = list(rows.values())
        self.fixes = [{"example_id": r["example_id"], "quote": r["formatted_interaction"][-40:]}
                      for r in self.batch[:2]]

    def edit(self, **kw):
        e = {"edit_type": "pre_check", "op": "insert_after", "anchor": "No Material Risk must be used alone.",
             "new_text": "Before choosing, confirm who approved the action.", "fixes": self.fixes}
        e.update(kw)
        return e

    def check(self, e, tried=()):
        return evolve.validate_edit(e, self.prompt, self.prompt, "task2b", self.batch, set(tried), PARAMS)

    def test_valid_edit_applies(self):
        cand, reason = self.check(self.edit())
        self.assertIsNone(reason)
        self.assertIn("No Material Risk must be used alone.\nBefore choosing, confirm", cand)

    def test_anchor_missing_or_duplicated(self):
        self.assertIn("0 times", self.check(self.edit(anchor="not in the prompt"))[1])
        dup = "the"   # occurs many times
        self.assertIn("times", self.check(self.edit(anchor=dup))[1])

    def test_protected_label_removed(self):
        _, reason = self.check(self.edit(op="delete", anchor="   Scope / Safeguard Failure\n", new_text=""))
        self.assertIn("protected", reason)
        _, reason = self.check(self.edit(op="replace", anchor="Scope / Safeguard Failure",
                                         new_text="Scope Failure"))
        self.assertIn("protected", reason)

    def test_label_line_reworded(self):
        _, reason = self.check(self.edit(op="replace", anchor="   Execution / Action Hazard",
                                         new_text="   Execution / Action Hazard (tool misuse)"))
        self.assertIn("label line", reason)

    def test_output_tail_changed(self):
        _, reason = self.check(self.edit(op="replace", anchor="Keep the justification to at most 120 words",
                                         new_text="Keep the justification to at most 80 words"))
        self.assertIn("tail", reason)

    def test_quote_must_be_verbatim_and_two_items(self):
        bad = [dict(self.fixes[0]), {"example_id": self.fixes[1]["example_id"], "quote": "an invented quote here"}]
        self.assertIn("verbatim", self.check(self.edit(fixes=bad))[1])
        self.assertIn("distinct", self.check(self.edit(fixes=[self.fixes[0], self.fixes[0]]))[1])
        outsider = [self.fixes[0], {"example_id": "AGENTRISK-999", "quote": "whatever text is here"}]
        self.assertIn("not a batch item", self.check(self.edit(fixes=outsider))[1])

    def test_malformed_edit_fields_are_rejected(self):
        for fields in ({"anchor": [1]}, {"new_text": [1]}, {"op": [1]},
                       {"fixes": "bad"}, {"fixes": [1]},
                       {"fixes": [{"example_id": [], "quote": "text"}]}):
            with self.subTest(fields=fields):
                candidate, reason = self.check(self.edit(**fields))
                self.assertIsNone(candidate)
                self.assertIsNotNone(reason)

    def test_size_limits(self):
        long = " ".join(["word"] * 61)
        self.assertIn("words >", self.check(self.edit(new_text=long))[1])
        p = dict(PARAMS, max_growth_words=5)
        _, reason = evolve.validate_edit(self.edit(), self.prompt, self.prompt, "task2b", self.batch, set(), p)
        self.assertIn("seed", reason)

    def test_copied_text_and_ids(self):
        copied = " ".join(self.batch[0]["formatted_interaction"].split()[:5])
        self.assertIn("copies", self.check(self.edit(new_text=f"Note that {copied}."))[1])
        self.assertIn("id", self.check(self.edit(new_text="Unlike AGENTRISK-012, check consent."))[1])
        # phrases the prompt already uses are not "copied from the batch"
        self.assertIsNone(self.check(self.edit(new_text="Assess the proposed action itself first."))[1])

    def test_identical_prompt_rejected(self):
        cand, _ = self.check(self.edit())
        self.assertIn("already tried", self.check(self.edit(), tried={evolve.norm_ws(cand)})[1])

    def test_delete_removes_whole_line(self):
        text = "a line\nremove me please\nlast line\n"
        out = evolve.apply_edit(text, {"op": "delete", "anchor": "remove me please", "new_text": ""})
        self.assertEqual(out, "a line\nlast line\n")

    def test_task1_level_names_protected(self):
        p = SEED_T1.read_text()
        self.assertEqual(len(evolve.protected_strings("task1", p)), 5)
        e = self.edit(op="replace", anchor="3 Moderate:", new_text="3 Medium:",)
        _, reason = evolve.validate_edit(e, p, p, "task1", self.batch, set(), PARAMS)
        self.assertIn("protected", reason)
        e = self.edit(op="replace", anchor="meaningful risk with substantial consequences",
                      new_text="meaningful risk with consequences that are hard to undo")
        self.assertIsNone(evolve.validate_edit(e, p, p, "task1", self.batch, set(), PARAMS)[1])


# ---------------------------------------------------------------- ledger and gates
def recs(values, task="task2b"):
    field = evolve.FIELD[task]
    return {f"AGENTRISK-{n:03d}": ({"status": "ok", "labels": {field: v}} if v is not None else {"status": "invalid"})
            for n, v in enumerate(values)}


def gold_rows(values, task="task2b"):
    field = evolve.FIELD[task]
    return {f"AGENTRISK-{n:03d}": {"example_id": f"AGENTRISK-{n:03d}", field: v} for n, v in enumerate(values)}


class LedgerAndGates(unittest.TestCase):
    def test_ledger(self):
        led = evolve.ledger([0, 0, 1, 0.5, 1], [0, 1, 0, 0.5, 0.5])
        self.assertEqual((led["improved"], led["worsened"], led["net"]), (2, 1, 1))
        self.assertEqual((led["right_to_wrong"], led["wrong_to_right"], led["base_correct"]), (1, 1, 2))

    def gate(self, gold, champ, cand, task="task2b", tau=0.0, **p):
        rows = gold_rows(gold, task)
        ids = sorted(rows)
        fold_of = {i: n % 4 for n, i in enumerate(ids)}
        return evolve.full_gate_metrics(task, rows, recs(champ, task), recs(cand, task), ids, fold_of,
                                        dict(PARAMS, **p), tau)

    def test_clear_gain_passes(self):
        gold = [[SCOPE]] * 40 + [[AUTH]] * 40
        champ = [[AUTH]] * 20 + [[SCOPE]] * 20 + [[AUTH]] * 40
        cand = [[SCOPE]] * 40 + [[AUTH]] * 40
        passed, m = self.gate(gold, champ, cand)
        self.assertTrue(passed, m["gates"])
        self.assertEqual(m["ledger"]["net"], 20)

    def test_g1_needs_net_above_noise(self):
        gold = [[SCOPE]] * 40 + [[AUTH]] * 40
        champ = [[AUTH]] * 6 + [[SCOPE]] * 34 + [[AUTH]] * 40
        cand = [[SCOPE]] * 40 + [[AUTH]] * 40
        self.assertTrue(self.gate(gold, champ, cand)[1]["gates"]["G1_gain"]["pass"])
        self.assertFalse(self.gate(gold, champ, cand, tau=4)[1]["gates"]["G1_gain"]["pass"])   # need 8
        self.assertFalse(self.gate(gold, champ, cand, min_net=7)[1]["gates"]["G1_gain"]["pass"])

    def test_g2_right_to_wrong_cap(self):
        gold = [[SCOPE]] * 40 + [[AUTH]] * 40
        champ = [[AUTH]] * 20 + [[SCOPE]] * 20 + [[AUTH]] * 40
        cand = [[SCOPE]] * 40 + [[SCOPE]] * 3 + [[AUTH]] * 37    # fixes 20, breaks 3 of 60 correct
        _, m = self.gate(gold, champ, cand)
        self.assertFalse(m["gates"]["G2_no_damage"]["pass"])     # cap 0.03 * 60 = 1.8

    def test_g3_rejects_label_swap(self):
        """The Task 2b Authorization <-> Scope failure: FP of one label down, its FN up, no real gain."""
        gold = [[AUTH]] * 30 + [[SCOPE]] * 30
        champ = [[AUTH]] * 30 + [[AUTH]] * 30           # Scope never predicted
        cand = [[SCOPE]] * 30 + [[SCOPE]] * 30           # now Authorization is never predicted
        _, m = self.gate(gold, champ, cand)
        g3 = m["gates"]["G3_no_shift"]
        self.assertFalse(g3["pass"])
        self.assertIn(AUTH, g3["swapped_labels"])

    def test_g3_rejects_label_count_drift(self):
        gold = [[AUTH]] * 40
        champ = [[AUTH]] * 40
        cand = [[AUTH, SCOPE]] * 8 + [[AUTH]] * 32
        self.assertFalse(self.gate(gold, champ, cand)[1]["gates"]["G3_no_shift"]["pass"])

    def test_g3_task1_level_shift_and_gold1(self):
        gold = [1] * 20 + [3] * 20 + [4] * 20
        champ = [1] * 20 + [4] * 10 + [3] * 10 + [4] * 20
        cand = [2] * 3 + [1] * 17 + [3] * 20 + [3] * 20      # 3->4 fixed, but all 4s pulled to 3
        _, m = self.gate(gold, champ, cand, task="task1")
        self.assertFalse(m["gates"]["G3_no_shift"]["pass"])
        self.assertIn(4, m["gates"]["G3_no_shift"]["levels_grown"])
        self.assertEqual(m["gates"]["G2_no_damage"]["gold1_lost"], 3)
        self.assertFalse(m["gates"]["G2_no_damage"]["pass"])

    def test_g5_stability_and_g6_validity(self):
        gold = [[SCOPE]] * 80
        champ = [[AUTH]] * 20 + [[SCOPE]] * 60
        cand = [[SCOPE]] * 20 + [[SCOPE]] * 60
        rows = gold_rows(gold)
        ids = sorted(rows)
        fold_of = {i: (0 if n < 20 else 1 + n % 3) for n, i in enumerate(ids)}   # all gain in fold 0
        _, m = evolve.full_gate_metrics("task2b", rows, recs(champ), recs(cand), ids, fold_of, PARAMS, 0)
        self.assertFalse(m["gates"]["G5_stability"]["pass"])
        cand2 = [[SCOPE]] * 20 + [None] + [[SCOPE]] * 59
        _, m = self.gate(gold, champ, cand2)
        self.assertFalse(m["gates"]["G6_validity"]["pass"])

    def test_invalid_counts_as_worst_loss(self):
        rows = gold_rows([3], "task1")
        self.assertEqual(evolve.item_loss("task1", rows["AGENTRISK-000"], {"status": "invalid"}), 4.0)


# ---------------------------------------------------------------- target selection, data roles
class TargetsAndRoles(unittest.TestCase):
    def test_task1_cost_weights_distance(self):
        rows = gold_rows([3, 3, 3, 1, 1], "task1")
        preds = recs([4, 4, 4, 3, 3], "task1")
        cells = evolve.wrong_cells("task1", rows, preds, sorted(rows))
        self.assertEqual(cells[0]["cell"], [1, 3])      # 2 items x distance 2 = 4 > 3 items x 1
        self.assertEqual(cells[0]["cost"], 4)

    def test_task2_cells_include_pure_fn_fp(self):
        rows = gold_rows([[SCOPE], [AUTH, SCOPE], [AUTH]])
        preds = recs([[AUTH], [AUTH], [AUTH, SCOPE]])
        cells = {tuple(c["cell"]): c["count"] for c in evolve.wrong_cells("task2b", rows, preds, sorted(rows))}
        self.assertEqual(cells, {(SCOPE, AUTH): 1, (SCOPE, None): 1, (None, SCOPE): 1})

    def test_blocked_cells(self):
        k = evolve.cell_key([3, 4])
        self.assertTrue(evolve.cell_blocked({k: ["failed", "failed"]}, k))
        self.assertFalse(evolve.cell_blocked({k: ["failed", "accepted"]}, k))
        self.assertTrue(evolve.cell_blocked({k: ["label_noise"]}, k))

    def test_payload_outside_fold_raises(self):
        with self.assertRaises(evolve.DataRoleError):
            evolve.assert_ids_in_fold({"items": [{"example_id": "AGENTRISK-001"}, {"x": "AGENTRISK-777"}]},
                                      ["AGENTRISK-001"])
        evolve.assert_ids_in_fold({"items": [{"example_id": "AGENTRISK-001"}]}, ["AGENTRISK-001"])


class DataRoleInRun(SyntheticRun):
    def test_proposer_refuses_outside_ids(self):
        ev = self.evolver(self.init())
        with self.assertRaises(evolve.DataRoleError):
            ev.propose(ev.run_dir / "x.json", evolve.BLIND_PROMPT,
                       {"items": [{"example_id": self.folds[2][0]}]}, self.folds[1])

    def test_batches_come_from_the_proposing_fold(self):
        ev = self.evolver(self.init())
        ev.baseline()
        ev.step(rounds=1)
        batch = json.loads((ev.run_dir / "rounds" / "round_01" / "batch.json").read_text())
        self.assertTrue(set(batch["order"]) <= set(self.folds[1]))
        self.assertTrue(batch["right"])
        payload = json.loads((ev.run_dir / "cache" / "proposer" / "round_01_proposer_edit.json").read_text())
        self.assertTrue(set(evolve.ID_RE.findall(json.dumps(payload))) <= set(self.folds[1]))


# ---------------------------------------------------------------- the loop end to end
class Loop(SyntheticRun):
    def test_accepts_the_real_fix_and_exports(self):
        ev = self.evolver(self.init())
        base = ev.baseline()
        self.assertEqual(base["tau"], 0)
        ev.step(rounds=1)
        d = json.loads((ev.run_dir / "rounds" / "round_01" / "decision.json").read_text())
        self.assertEqual(d["outcome"], "accepted", d)
        champ = ev.state["champion"]
        self.assertIn(MAGIC, ev.prompt_text(champ))
        cands = json.loads((ev.run_dir / "rounds" / "round_01" / "candidates.json").read_text())
        reasons = {c["edit_type"]: c.get("rejected") for c in cands}
        self.assertIsNone(reasons["pre_check"])
        self.assertIn("anchor", reasons["conditional"])
        self.assertIn("protected", reasons["delete"])
        self.assertTrue(all(i in ev.preds_of(champ) for i in ev.all_ids))   # champion covers all items
        pm = ev.process_metrics()
        self.assertEqual(pm["accepted_edits"], 1)
        self.assertLess(pm["champion_vs_seed_train_evolve"]["diff"], 0)
        # export, then refuse to overwrite (prompt freeze rule)
        prompts = self.tmp / "prompts"
        out, cl = evolve.export_prompt(ev, "reason-v9", prompts_root=prompts)
        self.assertEqual(out.read_text(), ev.prompt_text(champ))
        self.assertIn("Round 1", cl.read_text())
        with self.assertRaises(SystemExit):
            evolve.export_prompt(ev, "reason-v9", prompts_root=prompts)
        with self.assertRaises(SystemExit):
            evolve.export_prompt(ev, "facts-v9", prompts_root=prompts)

    def test_stops_on_patience(self):
        def useless(system, payload, params):
            out, usage = fake_propose(system, payload, params)
            if "edits" in out:
                out["edits"] = [e for e in out["edits"] if e["edit_type"] != "pre_check"]
            return out, usage
        ev = self.evolver(self.init(), propose_fn=useless)
        ev.baseline()
        ev.step()
        self.assertEqual(ev.state["stopped"], "patience")
        self.assertEqual(ev.state["round"], 2)

    def test_label_noise_round_is_skipped_not_failed(self):
        def noisy(system, payload, params):
            out, usage = fake_propose(system, payload, params)
            if "faults" in out:
                out["faults"] = [dict(f, fault="sound_but_wrong") for f in out["faults"]]
            return out, usage
        ev = self.evolver(self.init(), propose_fn=noisy)
        ev.baseline()
        ev.step(rounds=1)
        self.assertEqual(ev.state["decisions"][0]["outcome"], "skipped")
        self.assertEqual(ev.state["patience"], 0)
        self.assertIn("label_noise", list(ev.state["cell_history"].values())[0])

    def test_resume_after_kill_requests_nothing_twice(self):
        run_dir = self.init()
        ev = self.evolver(run_dir)
        ev.baseline()
        orig = evolve.full_gate_metrics

        def killed(*a, **kw):
            raise KeyboardInterrupt("killed after the quick gate")
        evolve.full_gate_metrics = killed
        try:
            with self.assertRaises(KeyboardInterrupt):
                ev.step(rounds=1)
        finally:
            evolve.full_gate_metrics = orig
        rd = run_dir / "rounds" / "round_01"
        self.assertTrue((rd / "quick_gate.json").exists())
        self.assertFalse((rd / "decision.json").exists())
        proposer_calls = []

        def counting(system, payload, params):
            proposer_calls.append(1)
            return fake_propose(system, payload, params)
        ev2 = self.evolver(run_dir, propose_fn=counting)
        ev2.step(rounds=1)
        self.assertEqual(ev2.state["decisions"][0]["outcome"], "accepted")
        self.assertEqual(proposer_calls, [])                 # replayed from disk
        self.assertEqual(max(CALLS.values()), 1, [k for k, v in CALLS.items() if v > 1][:3])

    def test_resume_restores_candidate_registrations(self):
        run_dir = self.init()
        ev = self.evolver(run_dir)
        ev.baseline()
        candidates_path = run_dir / "rounds" / "round_01" / "candidates.json"
        save_state = ev.save_state

        def interrupted_save():
            if candidates_path.exists():
                raise KeyboardInterrupt
            save_state()

        ev.save_state = interrupted_save
        with self.assertRaises(KeyboardInterrupt):
            ev.step(rounds=1)
        candidates = [c["cand_id"] for c in evolve.read_json(candidates_path) if "cand_id" in c]
        self.assertTrue(candidates)
        resumed = self.evolver(run_dir)
        self.assertTrue(set(candidates).isdisjoint(resumed.state["prompts"]))
        resumed.step(rounds=1)
        for cid in candidates:
            self.assertIn(evolve.norm_ws(resumed.prompt_text(cid)), resumed.tried_norms())
        self.assertEqual(max(CALLS.values()), 1)

    def test_budget_stops_cleanly(self):
        ev = self.evolver(self.init("--param", "budget_tokens=2100"))
        ev.baseline()   # 200 requests x 10 tokens = 2000; the check runs before each batch of 64
        ev.step()       # blind call adds 100 -> the edit call is refused
        self.assertEqual(ev.state["stopped"], "budget")

    def test_placebo_permutes_gold_shown_to_proposer(self):
        seen = {}

        def spy(system, payload, params):
            if "blind_audit" in payload:
                seen["gold"] = {it["example_id"]: it["gold"] for it in payload["items"]}
            return fake_propose(system, payload, params)
        ev = self.evolver(self.init("--param", "placebo=1"), propose_fn=spy)
        ev.baseline()
        ev.step(rounds=1)
        true = {i: self.rows[i]["risk_drivers"] for i in seen["gold"]}
        self.assertEqual(sorted(map(str, seen["gold"].values())), sorted(map(str, true.values())))
        self.assertNotEqual(seen["gold"], true)

    def test_api_outage_is_not_cached(self):
        """Exhausted retries with transport errors stay retryable, including mixed failures."""
        down = {"on": True}
        mixed_id = self.folds[0][0]
        mixed_attempts = []

        def flaky(text, row, output_format, task, replica):
            if down["on"] and row["example_id"] == mixed_id and not mixed_attempts:
                mixed_attempts.append(1)
                return {}, {}
            if down["on"] and row["example_id"] in (mixed_id, self.folds[3][5]):
                raise ConnectionError("simulated outage")
            return fake_predict(text, row, output_format, task, replica)
        evolve.time.sleep, orig_sleep = (lambda s: None), evolve.time.sleep
        try:
            run_dir = self.init()
            cfg = json.loads((run_dir / "config.json").read_text())
            cfg["dry_run"] = False           # dry runs re-raise; exercise the real error path
            (run_dir / "config.json").write_text(json.dumps(cfg))
            ev = self.evolver(run_dir, predict_fn=flaky)
            with self.assertRaises(evolve.ApiUnavailable):
                ev.baseline()
            self.assertNotIn(mixed_id, ev.preds_of("s0"))
            self.assertNotIn(self.folds[3][5], ev.preds_of("s0"))
            down["on"] = False
            ev2 = self.evolver(run_dir, predict_fn=flaky)
            ev2.baseline()
            self.assertEqual(ev2.preds_of("s0")[self.folds[0][0]]["status"], "ok")
        finally:
            evolve.time.sleep = orig_sleep

    def test_blind_output_with_stray_id_does_not_block(self):
        def typo(system, payload, params):
            out, usage = fake_propose(system, payload, params)
            if "items" in out and "blind_audit" not in payload:
                out["items"].append({"example_id": "AGENTRISK-4130", "check_note": "x"})
                out["items"][0]["check_note"] = "similar to AGENTRISK-999"
            return out, usage
        ev = self.evolver(self.init(), propose_fn=typo)
        ev.baseline()
        ev.step(rounds=1)
        self.assertEqual(ev.state["decisions"][0]["outcome"], "accepted")
        dropped = json.loads((ev.run_dir / "rounds" / "round_01" / "blind_sanitized.json").read_text())
        self.assertIn("AGENTRISK-4130", dropped["dropped"])

    def test_blind_call_sees_no_gold_direction(self):
        seen = {}

        def spy(system, payload, params):
            if "blind_audit" not in payload:
                seen["boundary"] = payload["boundary"]
                seen["items"] = payload["items"]
            return fake_propose(system, payload, params)
        ev = self.evolver(self.init(), propose_fn=spy)
        ev.baseline()
        ev.step(rounds=1)
        text = json.dumps(seen, ensure_ascii=False)
        self.assertNotIn("gold", text)
        self.assertNotIn("missing", text)
        self.assertNotIn("wrong", text)
        self.assertEqual(seen["boundary"]["options"], sorted(seen["boundary"]["options"]))

    def test_tau_ignores_label_order(self):
        def reorder(text, row, output_format, task, replica):
            out, usage = fake_predict(text, row, output_format, task, replica)
            out["answer"]["risk_drivers"] = [AUTH, SCOPE] if replica == 0 else [SCOPE, AUTH]
            return out, usage
        ev = self.evolver(self.init(), predict_fn=reorder)
        self.assertEqual(ev.baseline()["tau"], 0)

    def test_config_records_shas_and_params(self):
        run_dir = self.init("--param", "min_net=7", "--limit-per-fold", "10")
        cfg = json.loads((run_dir / "config.json").read_text())
        self.assertEqual(cfg["params"]["min_net"], 7)
        self.assertEqual(cfg["limit_per_fold"], 10)
        self.assertEqual(cfg["seeds"][0]["sha256"], evolve.sha256_text(SEED.read_text()))
        self.assertIn("blind", cfg["proposer_prompts"])
        with self.assertRaises(SystemExit):     # every run gets a new run_id
            self.init()


if __name__ == "__main__":
    unittest.main()
