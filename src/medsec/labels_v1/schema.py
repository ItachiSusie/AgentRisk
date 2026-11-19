"""Strict required fields and content fingerprints; retain extension fields."""
import hashlib
import json

FIELDS = {
    'task': 'schema_version task_id benchmark_id task_family scenario_group_id split data_origin snapshot_sha256 authorization_scope_ref required_outcome_ref verifier_id review_status',
    'attack': 'attack_id task_id threat_model surface carrier injection_point source_trust allowed_edit trigger_rule_id trigger_ref goal_id goal_ref attack_family_id review_status',
    'run': 'run_id task_id benchmark_id model_version agent_version defense_id condition pair_id snapshot_sha256 events_sha256 outcome_sha256 evidence_complete',
}
CONDITIONS = {'clean_none', 'clean_on', 'attack_none', 'attack_on'}


def digest(value):
    raw = value if isinstance(value, bytes) else json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()
    return hashlib.sha256(raw).hexdigest()


def validate(kind, record):
    missing = set(FIELDS[kind].split()) - record.keys()
    if missing:
        raise ValueError(f'{kind}: missing fields {sorted(missing)}')
    if kind == 'task' and record['benchmark_id'] not in {'medagentbench_ext', 'healthagentbench_synthetic'}:
        raise ValueError('only synthetic tracks are supported')
    if kind == 'run' and (record['condition'] not in CONDITIONS or type(record['evidence_complete']) is not bool):
        raise ValueError('invalid condition or evidence completeness')
    return record


def label(name, value, rule, refs, reason, inputs):
    if value not in {'true', 'false', 'unknown', 'not_applicable'}:
        raise ValueError('invalid four-valued label')
    return {'label_name': name, 'value': value, 'rule_id': rule, 'rule_version': '1.0.0',
            'evidence_refs': refs, 'reason_code': reason, 'input_sha256': digest(inputs)}
