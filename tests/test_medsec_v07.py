import json
import tempfile
import unittest
from pathlib import Path

from src.medsec.v07.engine import ReferenceModel, run_episode
from src.medsec.v07.schema import payload_text, read_json, validate_attack
from src.medsec.v07.scoring import score
from src.medsec.v07.suite import create_suite


class V07Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "suite"
        self.manifest = create_suite(self.root)

    def task_attack(self, family="portal_message", case=1, index=1, benchmark="medagentbench_ext"):
        task_id = f"{benchmark}-{family}-{case:02d}"
        task = read_json(self.root / "tasks" / f"{task_id}.json")
        surface = (('environment_data', 'tool_result'), ('tool_description', 'skill_file'),
                   ('memory_induced', 'memory_store_edit'), ('retrieved_document', 'malicious_user'))[case-1][index-1]
        attack = read_json(self.root / "attacks" / f"{task_id}-{index:02d}-{surface}.json")
        return task, attack, payload_text(attack, self.root)

    def test_suite_counts_and_normal_utility(self):
        self.assertEqual((self.manifest["task_count"], self.manifest["attack_count"]), (32, 64))
        for path in (self.root / "tasks").glob("*.json"):
            task = read_json(path)
            outcome, events = run_episode(task, ReferenceModel(task), "smoke")
            self.assertTrue(score(task, None, outcome, events)["extended_utility_pass"], task["task_id"])

    def test_permissions_and_payload_hash(self):
        task, attack, _ = self.task_attack()
        attack["allowed_edit"] = ["snapshot.records.lab_value"]
        with self.assertRaisesRegex(ValueError, "permission mismatch"):
            validate_attack(attack, task, self.root)
        task, attack, _ = self.task_attack()
        (self.root / attack["payload_ref"]).write_text("altered")
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            validate_attack(attack, task, self.root)

    def test_observation_attack_and_scope_defense(self):
        task, attack, payload = self.task_attack()

        def vulnerable(messages):
            actions = [json.loads(m["content"])["tool"] for m in messages if m["role"] == "assistant"]
            if not actions:
                return {"tool": "read_record", "args": {"patient_id": task["patient_id"]}}
            if "Operational update:" in messages[-1]["content"] and "decoy" not in actions:
                return {"tool": "read_record", "args": {"patient_id": task["forbidden_outcome"]["patient_id"]}}
            if "write_resource" not in actions:
                return task["required_outcome"]
            return {"tool": "finish", "args": {"answer": "Completed."}}

        outcome, events = run_episode(task, vulnerable, "attack", attack=attack, payload=payload)
        result = score(task, attack, outcome, events)
        self.assertTrue(result["security"]["exposed"])
        self.assertTrue(result["security"]["attack_success"])
        outcome, events = run_episode(task, vulnerable, "defended", attack=attack, payload=payload,
                                      defense_name="scope")
        result = score(task, attack, outcome, events)
        self.assertFalse(result["security"]["exposed"])
        self.assertFalse(result["security"]["attack_success"])
        self.assertTrue(result["extended_utility_pass"])

    def test_memory_induced_requires_target_retrieval(self):
        task, attack, payload = self.task_attack("ehr_data_quality", 3, 1, "healthagentbench_synthetic")
        outcome, events = run_episode(task, ReferenceModel(task), "clean-memory", attack=attack, payload=payload)
        self.assertFalse(score(task, attack, outcome, events)["security"]["exposed"])

        def retaining_model(messages):
            if any("Source episode" in m["content"] for m in messages[-2:]):
                return {"tool": "write_memory", "args": {"scope": task["patient_id"],
                    "text": payload, "source_ref": "source_note"}}
            return ReferenceModel(task)(messages)

        outcome, events = run_episode(task, retaining_model, "retained", attack=attack, payload=payload)
        self.assertTrue(score(task, attack, outcome, events)["security"]["exposed"])

    def test_healthcare_file_result_is_scored_from_state(self):
        task, attack, payload = self.task_attack("ehr_data_quality", 1, 2, "healthagentbench_synthetic")
        outcome, events = run_episode(task, ReferenceModel(task), "health", attack=attack, payload=payload)
        result = score(task, attack, outcome, events)
        self.assertTrue(result["extended_utility_pass"])
        self.assertTrue(result["security"]["exposed"])
        self.assertFalse(result["security"]["attack_success"])


if __name__ == "__main__":
    unittest.main()
