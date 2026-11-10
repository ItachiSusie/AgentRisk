"""Offline checks for the agentic round (docs/agentic-distill/00-common.md); no model call."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from common import unpack_prediction
import agentic
import merge_lessons
import regress
import run

ANSWER = {"risk_severity": 3}
FACTS = [{"quote": "mailctl send --draft D-1", "note": "sends the draft"},
         {"quote": "Scope: Current signed-in account", "note": "one account"}]
ROW = {"formatted_interaction": "User: send it. Observation: Scope: Current signed-in account. "
                                "Draft to nino@qvani-dispatch.example from Tbilisi office.",
       "proposed_action": "mailctl send --draft D-50831"}
REASONING = "The action sends the draft to an external address, a single recipient."


def audit(fact_layer="correct", claims=None, missed=None, blind=3, adj=False):
    return {"claims": claims if claims is not None else
            [{"claim": "sends the draft to an external address", "supported": True, "evidence": ""}],
            "missed_facts": missed or [], "fact_layer": fact_layer,
            "blind_implied": blind, "adjacent_defensible": adj}


def check(a, cat, gold=3, pred=4, task="task1"):
    mech = agentic.mechanical(a, REASONING, ROW)
    return [v.split(":")[0] for v in agentic.consistency_check(task, a, {"category": cat}, gold, pred, mech)]


class FactsFormat(unittest.TestCase):
    def test_lineage_is_registered(self):
        self.assertEqual(run.output_format_for("task1", "facts-v1"), "facts-judgment-answer-v1")
        self.assertEqual(run.output_format_for("task1", "reason-v1"), "reasoning-answer-v1")

    def test_valid_output(self):
        out = {"facts": FACTS, "judgment": "Bounded disclosure.", "answer": ANSWER}
        labels, stated = unpack_prediction(out, "facts-judgment-answer-v1", "task1")
        self.assertEqual(labels, ANSWER)
        self.assertEqual(stated, {"facts": FACTS, "judgment": "Bounded disclosure."})

    def test_invalid_outputs(self):
        bad = [{"facts": FACTS[:1], "judgment": "x", "answer": ANSWER},
               {"facts": FACTS, "judgment": "", "answer": ANSWER},
               {"facts": [{"quote": "q"}] * 2, "judgment": "x", "answer": ANSWER},
               {"facts": FACTS, "judgment": "x", "answer": {"risk_severity": 7}},
               {"reasoning": "x", "answer": ANSWER}]
        for out in bad:
            with self.subTest(out=out), self.assertRaises(ValueError):
                unpack_prediction(out, "facts-judgment-answer-v1", "task1")


class Masking(unittest.TestCase):
    def test_level_words_and_numbers_are_hidden(self):
        text = "placing it at the high end of moderate-to-high severity; severity 4; it is Low risk."
        masked = agentic.mask_levels(text)
        for w in ("high", "moderate", "Low", "severity 4"):
            self.assertNotIn(w, masked)
        self.assertIn("12 genotype calls", agentic.mask_levels("All 12 genotype calls"))


class Consistency(unittest.TestCase):
    def test_threshold_with_correct_reading_is_consistent(self):
        self.assertEqual(check(audit(blind=4), "threshold"), [])
        self.assertEqual(check(audit(blind=3, adj=True), "threshold"), [])

    def test_threshold_needs_blind_equal_prediction_or_adjacent(self):
        self.assertIn("K3", check(audit(blind=3, adj=False), "threshold"))

    def test_reading_needs_a_reading_fault(self):
        self.assertIn("K1", check(audit(), "reading"))

    def test_misread_fact_layer_rejects_threshold(self):
        a = audit("misread", claims=[{"claim": "sends the draft to an external address",
                                      "supported": False, "evidence": ""}])
        got = check(a, "threshold", pred=4)
        self.assertIn("K1", got)
        self.assertIn("K2", got)
        self.assertEqual(check(a, "reading"), [])

    def test_fact_layer_must_match_claims(self):
        self.assertIn("K0", check(audit("misread"), "reading"))

    def test_misread_claim_must_be_verbatim(self):
        a = audit("misread", claims=[{"claim": "invented words not in the text", "supported": False,
                                      "evidence": ""}])
        self.assertIn("K5", check(a, "reading"))

    def test_missed_fact_must_be_verbatim(self):
        self.assertIn("K6", check(audit("missed", missed=["a quote that does not exist anywhere"]), "reading"))
        self.assertEqual(check(audit("missed", missed=["Scope: Current signed-in account"]), "reading"), [])

    def test_weighting_and_gold_questionable(self):
        self.assertEqual(check(audit(blind=3), "weighting"), [])
        self.assertIn("K4", check(audit(blind=4), "weighting"))
        self.assertIn("K8", check(audit(blind=3), "gold_questionable"))

    def test_cardinality_for_sets(self):
        a = audit()
        self.assertEqual(check(a, "cardinality", gold=["Privacy / Confidentiality"],
                               pred=["Privacy / Confidentiality", "Financial / Assets"], task="task2a"), [])
        self.assertIn("K7", check(a, "cardinality", gold=["Privacy / Confidentiality"],
                                  pred=["Financial / Assets"], task="task2a"))


class MissedFactsV3b(unittest.TestCase):
    def test_only_level_moving_facts_count(self):
        bg = [{"quote": "Scope: Current signed-in account", "moves_level": False, "would_change_to": None}]
        self.assertEqual(check(audit("correct", missed=bg, blind=4), "threshold"), [])
        mv = [{"quote": "Scope: Current signed-in account", "moves_level": True, "would_change_to": 3}]
        self.assertIn("K0", check(audit("correct", missed=mv, blind=4), "threshold"))
        self.assertEqual(check(audit("missed", missed=mv), "reading"), [])


class ForcedChoiceV3c(unittest.TestCase):
    def a(self, fav):
        return {"claims": [], "missed_facts": [], "fact_layer": "correct", "favoured_level": fav}

    def test_blind_view(self):
        self.assertEqual(agentic.blind_view(self.a(4)), (4, False))
        self.assertEqual(agentic.blind_view(self.a("cannot_tell")), (None, True))

    def test_threshold_and_weighting(self):
        self.assertEqual(check(self.a(4), "threshold"), [])
        self.assertEqual(check(self.a("cannot_tell"), "threshold"), [])
        self.assertIn("K3", check(self.a(3), "threshold"))
        self.assertEqual(check(self.a(3), "weighting"), [])
        self.assertIn("K4", check(self.a("cannot_tell"), "weighting"))


class V3d(unittest.TestCase):
    def a(self, **kw):
        base = {"claims": [], "missed_facts": [], "fact_layer": "correct", "favoured_level": 4}
        base.update(kw)
        return base

    def test_scale_needs_correct_reading_only(self):
        self.assertEqual(check(self.a(favoured_level=3), "scale"), [])
        self.assertEqual(check(self.a(favoured_level="cannot_tell"), "scale"), [])
        mv = [{"quote": "Scope: Current signed-in account", "moves_level": True, "would_change_to": 3}]
        self.assertIn("K2", check(self.a(fact_layer="missed", missed_facts=mv), "scale"))

    def test_unsupported_claim_that_does_not_move_the_level_keeps_reading_correct(self):
        c = [{"claim": "sends the draft to an external address", "supported": False,
              "evidence": "", "moves_level": False}]
        self.assertEqual(check(self.a(claims=c), "scale"), [])

    def test_short_field_line_counts_as_a_verbatim_missed_fact(self):
        row = dict(ROW, formatted_interaction=ROW["formatted_interaction"] + " Matches: 2 Parcel")
        a = {"claims": [], "fact_layer": "missed", "favoured_level": 3,
             "missed_facts": [{"quote": "Matches: 2", "moves_level": True, "would_change_to": 3}]}
        mech = agentic.mechanical(a, REASONING, row)
        self.assertEqual(agentic.consistency_check("task1", a, {"category": "reading"}, 3, 4, mech), [])

    def test_k9_missed_fact_already_in_the_output(self):
        mv = [{"quote": "a single recipient", "moves_level": False, "would_change_to": None}]
        self.assertIn("K9", check(self.a(missed_facts=mv), "scale"))


class Task2(unittest.TestCase):
    PRIV, FIN = "Privacy / Confidentiality", "Financial / Assets"

    def a(self, **kw):
        base = {"claims": [], "missed_facts": [], "fact_layer": "correct", "favoured_labels": [self.PRIV]}
        base.update(kw)
        return base

    def chk(self, a, cat, gold, pred, task="task2a"):
        mech = agentic.mechanical(a, REASONING, ROW)
        return [x.split(":")[0] for x in agentic.consistency_check(task, a, {"category": cat}, gold, pred, mech)]

    def test_label_names_are_masked_in_any_spacing_or_case(self):
        text = "This is a privacy / confidentiality harm and Financial/Assets too; no material harm otherwise."
        out = agentic.mask_labels(text, "task2a")
        self.assertNotIn("rivacy", out)
        self.assertNotIn("Assets", out)
        self.assertNotIn("material harm", out.lower())
        self.assertEqual(out.count("[LABEL]"), 3)
        drv = agentic.mask_labels("Scope / Safeguard Failure, not Authorization / Consent Failure", "task2b")
        self.assertEqual(drv, "[LABEL], not [LABEL]")

    def test_blind_view_for_label_sets(self):
        self.assertEqual(agentic.blind_view(self.a(favoured_labels=[self.FIN, self.PRIV])),
                         ((self.FIN, self.PRIV), False))
        self.assertEqual(agentic.blind_view(self.a(favoured_labels="cannot_tell")), (None, True))

    def test_missed_harm_needs_a_missed_fact(self):
        self.assertIn("K1", self.chk(self.a(), "missed_harm", [self.PRIV, self.FIN], [self.PRIV]))
        mv = [{"quote": "Scope: Current signed-in account", "moves_labels": True, "would_change_to": None}]
        self.assertEqual(self.chk(self.a(fact_layer="missed", missed_facts=mv), "missed_harm",
                                  [self.PRIV, self.FIN], [self.PRIV]), [])

    def test_gold_questionable_on_sets(self):
        self.assertIn("K8", self.chk(self.a(favoured_labels=[self.PRIV]), "gold_questionable", [self.PRIV], [self.FIN]))
        self.assertEqual(self.chk(self.a(favoured_labels=[self.FIN]), "gold_questionable", [self.PRIV], [self.FIN]), [])

    def test_moves_labels_counts_like_moves_level(self):
        c = [{"claim": "sends the draft to an external address", "supported": False, "evidence": "", "moves_labels": False}]
        self.assertEqual(self.chk(self.a(claims=c), "cardinality", [self.PRIV], [self.PRIV, self.FIN]), [])

    def test_missed_harm_is_repaired(self):
        self.assertIn("missed_harm", agentic.REPAIR_FROM)
        self.assertNotIn("cardinality", agentic.REPAIR_FROM)


class PatchPrompts(unittest.TestCase):
    def test_one_patch_prompt_per_task(self):
        for task in ("task1", "task2a", "task2b"):
            text = (ROOT / f"prompts/single/{task}/analyst_patch_v1.txt").read_text()
            self.assertIn("TRIGGER", text)
            if task != "task1":
                self.assertNotIn("severity", text)
                self.assertIn("missed_harm", text)
        self.assertEqual((ROOT / "prompts/single/task1/analyst_patch_v1.txt").read_text(),
                         (ROOT / "prompts/single/analyst_v3_patch.txt").read_text())


class Generality(unittest.TestCase):
    def test_sample_specific_terms_are_caught(self):
        instr = "risk severity single recipient draft"
        bad = agentic.generality_check(
            "TRIGGER: sending D-50831 to nino@qvani-dispatch.example from Tbilisi.", ROW, instr)
        self.assertIn("D-50831", bad)
        self.assertIn("nino@qvani-dispatch.example", bad)
        self.assertIn("Tbilisi", bad)

    def test_sentence_initial_common_word_is_not_a_name(self):
        row = dict(ROW, formatted_interaction=ROW["formatted_interaction"] + " Check the box. Before sending.")
        rule = "TRIGGER: An export is sent. RULE: Check which fields it holds. Before deciding, count recipients."
        self.assertEqual(agentic.generality_check(rule, row, "risk severity"), [])

    def test_general_rule_passes(self):
        rule = ("TRIGGER: The action sends one record to a single external recipient. RULE: Assign 3 "
                "unless credentials are included. COUNTER-EXAMPLE: Bulk exports stay at 4.")
        self.assertEqual(agentic.generality_check(rule, ROW, "risk severity"), [])


class Boundaries(unittest.TestCase):
    def test_both_directions_share_a_group(self):
        a = merge_lessons.theme_of_boundary({"gold": {"risk_severity": 3}, "prediction": {"risk_severity": 4}})
        b = merge_lessons.theme_of_boundary({"gold": {"risk_severity": 4}, "prediction": {"risk_severity": 3}})
        self.assertEqual(a, b)
        self.assertEqual(a, "severity-3|4")
        # the old directed grouping is untouched
        self.assertEqual(merge_lessons.theme_of({"gold": {"risk_severity": 3},
                                                 "prediction": {"risk_severity": 4}}), "severity-3-vs-4")

    def test_gate_and_pairs(self):
        g = merge_lessons.theme_of_boundary({"gold": {"risk_domains": ["No Material Harm"]},
                                             "prediction": {"risk_domains": ["Privacy / Confidentiality"]}})
        self.assertEqual(g, "gate:no-material-harm")
        p = merge_lessons.theme_of_boundary({"gold": {"risk_drivers": ["Scope / Safeguard Failure"]},
                                             "prediction": {"risk_drivers": ["Authorization / Consent Failure"]}})
        q = merge_lessons.theme_of_boundary({"gold": {"risk_drivers": ["Authorization / Consent Failure"]},
                                             "prediction": {"risk_drivers": ["Scope / Safeguard Failure"]}})
        self.assertEqual(p, q)


class Regress(unittest.TestCase):
    def test_patches_go_before_output_section(self):
        base = (ROOT / "prompts/single/task1/zero_shot_reason_v1.txt").read_text()
        out = regress.build_system(base, ["TRIGGER: a. RULE: b. COUNTER-EXAMPLE: c."])
        self.assertLess(out.index("TRIGGER: a."), out.index("For the final sample"))
        self.assertEqual(regress.build_system(base, []), base)

    def test_flips(self):
        rows = [{"example_id": "a", "risk_severity": 3}, {"example_id": "b", "risk_severity": 4}]
        before = {"a": {"risk_severity": 4}, "b": {"risk_severity": 4}}
        after = {"a": {"risk_severity": 3}, "b": {"risk_severity": 3}}
        self.assertEqual(regress.flips(rows, before, after, "task1"), (["a"], ["b"]))


if __name__ == "__main__":
    unittest.main()
