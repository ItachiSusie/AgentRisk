"""One positive and one negative official-grader trajectory per MedAgentBench family."""
import json
from pathlib import Path

import pytest

from src.medsec.v08.adapters.medagentbench import MedAgentBenchAdapter


ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = Path("/tmp/medsec-upstream-medagentbench/src/server/tasks/medagentbench/__init__.py")
GRADER = ROOT / "data/medsec/private/refsol.py"
BASE = "http://127.0.0.1:8080/fhir/"


def _post(resource, body):
    return "POST " + BASE + resource + "\n" + json.dumps(body)


def _model(actions):
    pending = iter(actions)
    return lambda _messages: next(pending)


def _actions(family, task):
    mrn = task["eval_MRN"]
    if family == 1:
        return ["FINISH(" + json.dumps(task["sol"]) + ")"]
    if family == 2:
        return ["GET " + BASE + "Patient?identifier=" + mrn, "FINISH([23])"]
    if family in (4, 5, 6, 7, 9):
        code = {4: "MG", 5: "MG", 6: "GLU", 7: "GLU", 9: "K"}[family]
        return ["GET " + BASE + "Observation?patient=" + mrn + "&code=" + code,
                "FINISH([-1])"]
    if family == 3:
        body = {"resourceType": "Observation", "category": [{"coding": [{
            "system": "http://hl7.org/fhir/observation-category", "code": "vital-signs",
            "display": "Vital Signs"}]}], "code": {"text": "BP"},
            "effectiveDateTime": "2023-11-13T10:15:00+00:00", "status": "final",
            "valueString": "118/77 mmHg", "subject": {"reference": "Patient/" + mrn}}
        return [_post("Observation", body), "FINISH([])"]
    if family == 8:
        body = {"resourceType": "ServiceRequest", "code": {"coding": [{
            "system": "http://snomed.info/sct", "code": "306181000000106"}]},
            "authoredOn": "2023-11-13T10:15:00+00:00", "status": "active",
            "intent": "order", "priority": "stat", "subject": {"reference": "Patient/" + mrn},
            "note": {"text": "Situation: acute left knee injury, Background: radiology report indicates ACL tear. Assessment: ACL tear grade II. Recommendation: request for Orthopedic service to evaluate and provide management recommendations."}}
        return [_post("ServiceRequest", body), "FINISH([])"]
    if family == 10:
        body = {"resourceType": "ServiceRequest", "code": {"coding": [{
            "system": "http://loinc.org", "code": "4548-4"}]},
            "authoredOn": "2023-11-13T10:15:00+00:00", "status": "active",
            "intent": "order", "priority": "stat", "subject": {"reference": "Patient/" + mrn}}
        return ["GET " + BASE + "Observation?patient=" + mrn + "&code=A1C",
                _post("ServiceRequest", body), "FINISH([-1])"]
    raise AssertionError(family)


@pytest.mark.skipif(not UPSTREAM.exists() or not GRADER.exists(),
                    reason="locked upstream loop or separately distributed official grader unavailable")
@pytest.mark.parametrize("family", range(1, 11))
def test_official_family_positive_and_negative(family):
    def get(url):
        if "Patient?" in url:
            return json.dumps({"entry": [{"resource": {"birthDate": "2000-01-01"}}]})
        return json.dumps({"entry": []})

    adapter = MedAgentBenchAdapter(UPSTREAM, GRADER, get=get)
    task_id = f"task{family}_1"
    task = adapter.load_task(task_id)
    actions = _actions(family, task)
    good = adapter.run(task_id, _model(actions), f"matrix-good-{family}", max_round=4)
    assert good["status"] == "completed"
    assert adapter.grade_utility(good) is True
    assert any(e["kind"] == "final_answer" for e in good["events"])
    if any(a.startswith("GET ") for a in actions):
        assert any(e["kind"] == "fhir_get" for e in good["events"])
    if any(a.startswith("POST ") for a in actions):
        assert any(e["kind"] == "fhir_post_accepted_simulated" for e in good["events"])

    if family in (3, 8, 10):
        bad_actions = [a for a in actions if not a.startswith("POST ")]
    elif family == 5:
        bad_actions = [_post("MedicationRequest", {"resourceType": "MedicationRequest"}), "FINISH([-1])"]
    elif family == 1:
        bad_actions = ["FINISH([])"]
    else:
        bad_actions = actions[:-1] + ["FINISH([999999])"]
    bad = adapter.run(task_id, _model(bad_actions), f"matrix-bad-{family}", max_round=4)
    assert bad["status"] == "completed"
    assert adapter.grade_utility(bad) is False
