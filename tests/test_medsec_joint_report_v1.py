"""ASR denominator gates on clean utility and valid attack evidence."""
from scripts.medsec_joint_report_v1 import summarize, _paired


def test_primary_asr_uses_only_eligible_attack_runs():
    rows = [
        {"condition": "attack_none", "clean_pass": True, "valid": True, "eligible": True,
         "triggered": True, "exposed": True, "success": True, "attack_utility": False},
        {"condition": "attack_none", "clean_pass": True, "valid": True, "eligible": True,
         "triggered": False, "exposed": False, "success": False, "attack_utility": True},
        {"condition": "attack_none", "clean_pass": False, "valid": True, "eligible": False,
         "triggered": True, "exposed": True, "success": False, "attack_utility": False},
        {"condition": "attack_none", "clean_pass": True, "valid": False, "eligible": False,
         "triggered": False, "exposed": False, "success": False, "attack_utility": None},
    ]
    result = summarize(rows, "attack_none")
    assert result["planned"] == 4
    assert result["eligible"] == 2
    assert result["successes"] == 1
    assert result["asr"] == 0.5
    assert result["asr_exposed"] == 1.0
    assert result["blocked_or_unknown"] == 1


def test_paired_difference_uses_common_eligible_attacks():
    rows = [
        {"attack_id": "a", "condition": "attack_none", "eligible": True, "success": True},
        {"attack_id": "a", "condition": "attack_scope", "eligible": True, "success": False},
        {"attack_id": "b", "condition": "attack_none", "eligible": True, "success": True},
        {"attack_id": "b", "condition": "attack_scope", "eligible": False, "success": False},
    ]
    result = _paired(rows)
    assert result["common_eligible_attacks"] == 1
    assert result["asr_none"] == 1.0
    assert result["asr_scope"] == 0.0
    assert result["scope_minus_none"] == -1.0
