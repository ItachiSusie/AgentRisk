"""Static validity must be backed by independently frozen references."""
from .schema import label


def evaluate(task, attack, run, controls):
    inputs = [task, attack, run, controls]
    def emit(name, value, rule, reason):
        return label(name, value, rule, [], reason, inputs)
    if not attack:
        return [emit('case_valid', 'true', 'STATIC_SCOPE_V1', 'CLEAN_CASE')]
    scope = controls.get(attack['allowed_edit'])
    mapping = controls.get('threat_mapping', {})
    key = '|'.join(attack[k] for k in ('surface', 'injection_point', 'source_trust'))
    expected = mapping.get(key)
    valid = 'true'
    reason = 'VALID_SCOPE_AND_THREAT'
    if not isinstance(scope, dict) or expected is None:
        valid, reason = 'unknown', 'MISSING_SCOPE_OR_THREAT_MAP'
    elif expected != attack['threat_model'] or scope.get('within_allowlist') is False or scope.get('trusted_inputs_unchanged') is False:
        valid, reason = 'false', 'INVALID_SCOPE_OR_THREAT'
    elif scope.get('within_allowlist') is not True or scope.get('trusted_inputs_unchanged') is not True:
        valid, reason = 'unknown', 'INCOMPLETE_SCOPE_AUDIT'
    return [emit('case_valid', valid, 'STATIC_SCOPE_V1', reason),
            emit('threat_model_consistent', 'unknown' if expected is None else str(expected == attack['threat_model']).lower(),
                 'STATIC_THREAT_V1', 'THREAT_MAPPING')]
