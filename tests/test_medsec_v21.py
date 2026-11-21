"""v21 neutral-agent invariants, no API."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.medsec.v21 import episode as v21_episode


def test_neutral_prompt_has_no_injection_guardrails():
    p = v21_episode.SYSTEM_PROMPT.lower()
    # the v20 guardrails must be absent so `none` is a true no-mitigation baseline
    assert "untrusted" not in p
    assert "only act on the named patient" not in p
    # but the protocol contract (one action per turn) stays
    assert "one action per turn" in p


def test_v21_keeps_v20_protocol_and_memory_fixes():
    import inspect
    src = inspect.getsource(v21_episode)
    assert "OSError" in src                      # Bug 4 fix retained
    assert "from ..v20.capabilities import MemoryStore" in src  # metadata strip retained


def test_selected_attacks_are_calibrated_successes():
    man_path = ROOT / "data/medsec/v21_attacks/manifest.json"
    if not man_path.exists():
        return  # calibration output optional in CI
    man = json.loads(man_path.read_text())
    assert man["status"] == "synthetic_candidate_unreviewed"
    for surface, entries in man["selected"].items():
        assert len(entries) >= 1
        for e in entries:
            assert (ROOT / "data/medsec/v21_attacks" / e["attack_ref"]).exists()
