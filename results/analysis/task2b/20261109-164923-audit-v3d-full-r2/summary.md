# Audit v3 summary

- audited: 153

## status

| value | n | share |
| --- | --- | --- |
| kept | 137 | 90% |
| discarded:gold_questionable | 11 | 7% |
| discarded:unexplained | 5 | 3% |

## fact_layer

| value | n | share |
| --- | --- | --- |
| correct | 115 | 75% |
| misread | 21 | 14% |
| missed | 11 | 7% |
| misread+missed | 6 | 4% |

## category

| value | n | share |
| --- | --- | --- |
| confusable_pair | 85 | 56% |
| reading | 17 | 11% |
| cardinality | 17 | 11% |
| missed_harm | 16 | 10% |
| gold_questionable | 11 | 7% |
| unexplained | 5 | 3% |
| target_confusion | 2 | 1% |

- contradiction rate before re-ask: 1/153 = 1%
- still contradictory after re-ask: 0

## blind_implied versus gold / prediction

| value | n | share |
| --- | --- | --- |
| == gold | 94 | 61% |
| == prediction | 59 | 39% |

- cannot tell the two levels apart (v3c cannot_tell / v3, v3b adjacent_defensible): 0/153
- pairs (gold, prediction): (('Authorization / Consent Failure',), ('Authorization / Consent Failure', 'Risky Requested Outcome')): 1, (('Authorization / Consent Failure',), ('Authorization / Consent Failure', 'Scope / Safeguard Failure')): 1, (('Authorization / Consent Failure',), ('Authorization / Consent Failure', 'Untrusted / Conflicting Instructions')): 2, (('Authorization / Consent Failure',), ('Insufficient Grounding / Uncertainty',)): 1, (('Authorization / Consent Failure',), ('No Material Risk',)): 2, (('Authorization / Consent Failure', 'Insufficient Grounding / Uncertainty'), ('Authorization / Consent Failure', 'Scope / Safeguard Failure')): 1, (('Authorization / Consent Failure', 'Insufficient Grounding / Uncertainty'), ('Authorization / Consent Failure', 'Untrusted / Conflicting Instructions')): 1, (('Authorization / Consent Failure', 'Risky Requested Outcome'), ('No Material Risk',)): 1, (('Authorization / Consent Failure', 'Risky Requested Outcome'), ('Risky Requested Outcome', 'Scope / Safeguard Failure')): 2, (('Authorization / Consent Failure', 'Scope / Safeguard Failure'), ('Authorization / Consent Failure', 'Risky Requested Outcome')): 1, (('Authorization / Consent Failure', 'Untrusted / Conflicting Instructions'), ('Authorization / Consent Failure', 'Insufficient Grounding / Uncertainty')): 1, (('Authorization / Consent Failure', 'Untrusted / Conflicting Instructions'), ('Authorization / Consent Failure', 'Risky Requested Outcome')): 4, (('Authorization / Consent Failure', 'Untrusted / Conflicting Instructions'), ('Authorization / Consent Failure', 'Scope / Safeguard Failure')): 2, (('Authorization / Consent Failure', 'Untrusted / Conflicting Instructions'), ('Execution / Action Hazard', 'Untrusted / Conflicting Instructions')): 1, (('Authorization / Consent Failure', 'Untrusted / Conflicting Instructions'), ('Risky Requested Outcome', 'Untrusted / Conflicting Instructions')): 1, (('Authorization / Consent Failure', 'Untrusted / Conflicting Instructions'), ('Scope / Safeguard Failure', 'Untrusted / Conflicting Instructions')): 1, (('Execution / Action Hazard',), ('Authorization / Consent Failure', 'Scope / Safeguard Failure')): 1, (('Execution / Action Hazard',), ('Execution / Action Hazard', 'Insufficient Grounding / Uncertainty')): 2, (('Execution / Action Hazard',), ('Execution / Action Hazard', 'Scope / Safeguard Failure')): 2, (('Execution / Action Hazard',), ('No Material Risk',)): 7, (('Execution / Action Hazard', 'Insufficient Grounding / Uncertainty'), ('Authorization / Consent Failure', 'Execution / Action Hazard')): 2, (('Execution / Action Hazard', 'Insufficient Grounding / Uncertainty'), ('Risky Requested Outcome', 'Scope / Safeguard Failure')): 1, (('Execution / Action Hazard', 'Risky Requested Outcome'), ('Risky Requested Outcome', 'Scope / Safeguard Failure')): 1, (('Execution / Action Hazard', 'Scope / Safeguard Failure'), ('Insufficient Grounding / Uncertainty',)): 1, (('Insufficient Grounding / Uncertainty',), ('Authorization / Consent Failure',)): 1, (('Insufficient Grounding / Uncertainty',), ('Authorization / Consent Failure', 'Insufficient Grounding / Uncertainty')): 2, (('Insufficient Grounding / Uncertainty',), ('Authorization / Consent Failure', 'Risky Requested Outcome')): 1, (('Insufficient Grounding / Uncertainty',), ('Insufficient Grounding / Uncertainty', 'Scope / Safeguard Failure')): 3, (('Insufficient Grounding / Uncertainty',), ('Insufficient Grounding / Uncertainty', 'Untrusted / Conflicting Instructions')): 1, (('Insufficient Grounding / Uncertainty',), ('No Material Risk',)): 12, (('Insufficient Grounding / Uncertainty',), ('Risky Requested Outcome',)): 1, (('Insufficient Grounding / Uncertainty', 'Scope / Safeguard Failure'), ('Authorization / Consent Failure', 'Execution / Action Hazard')): 1, (('Insufficient Grounding / Uncertainty', 'Scope / Safeguard Failure'), ('Authorization / Consent Failure', 'Insufficient Grounding / Uncertainty')): 5, (('Insufficient Grounding / Uncertainty', 'Scope / Safeguard Failure'), ('Authorization / Consent Failure', 'Risky Requested Outcome')): 1, (('Insufficient Grounding / Uncertainty', 'Scope / Safeguard Failure'), ('Authorization / Consent Failure', 'Scope / Safeguard Failure')): 1, (('Insufficient Grounding / Uncertainty', 'Scope / Safeguard Failure'), ('Authorization / Consent Failure', 'Untrusted / Conflicting Instructions')): 1, (('Insufficient Grounding / Uncertainty', 'Scope / Safeguard Failure'), ('Insufficient Grounding / Uncertainty',)): 1, (('Insufficient Grounding / Uncertainty', 'Scope / Safeguard Failure'), ('No Material Risk',)): 1, (('Insufficient Grounding / Uncertainty', 'Scope / Safeguard Failure'), ('Risky Requested Outcome', 'Scope / Safeguard Failure')): 1, (('Insufficient Grounding / Uncertainty', 'Untrusted / Conflicting Instructions'), ('Authorization / Consent Failure', 'Insufficient Grounding / Uncertainty')): 1, (('Insufficient Grounding / Uncertainty', 'Untrusted / Conflicting Instructions'), ('Authorization / Consent Failure', 'Untrusted / Conflicting Instructions')): 2, (('Insufficient Grounding / Uncertainty', 'Untrusted / Conflicting Instructions'), ('Execution / Action Hazard', 'Untrusted / Conflicting Instructions')): 1, (('Insufficient Grounding / Uncertainty', 'Untrusted / Conflicting Instructions'), ('Insufficient Grounding / Uncertainty', 'Scope / Safeguard Failure')): 1, (('No Material Risk',), ('Execution / Action Hazard',)): 1, (('No Material Risk',), ('Insufficient Grounding / Uncertainty',)): 1, (('No Material Risk',), ('Risky Requested Outcome',)): 2, (('No Material Risk',), ('Risky Requested Outcome', 'Scope / Safeguard Failure')): 1, (('Risky Requested Outcome',), ('Insufficient Grounding / Uncertainty', 'Untrusted / Conflicting Instructions')): 1, (('Risky Requested Outcome',), ('No Material Risk',)): 2, (('Risky Requested Outcome',), ('Risky Requested Outcome', 'Scope / Safeguard Failure')): 1, (('Scope / Safeguard Failure',), ('Authorization / Consent Failure', 'Risky Requested Outcome')): 1, (('Scope / Safeguard Failure',), ('Authorization / Consent Failure', 'Scope / Safeguard Failure')): 3, (('Scope / Safeguard Failure',), ('Insufficient Grounding / Uncertainty', 'Scope / Safeguard Failure')): 1, (('Scope / Safeguard Failure',), ('Risky Requested Outcome', 'Scope / Safeguard Failure')): 2, (('Scope / Safeguard Failure', 'Untrusted / Conflicting Instructions'), ('Authorization / Consent Failure', 'Insufficient Grounding / Uncertainty')): 2, (('Scope / Safeguard Failure', 'Untrusted / Conflicting Instructions'), ('Authorization / Consent Failure', 'Scope / Safeguard Failure')): 2, (('Scope / Safeguard Failure', 'Untrusted / Conflicting Instructions'), ('Authorization / Consent Failure', 'Untrusted / Conflicting Instructions')): 51, (('Scope / Safeguard Failure', 'Untrusted / Conflicting Instructions'), ('Risky Requested Outcome', 'Untrusted / Conflicting Instructions')): 1, (('Untrusted / Conflicting Instructions',), ('Authorization / Consent Failure', 'Untrusted / Conflicting Instructions')): 2, (('Untrusted / Conflicting Instructions',), ('Risky Requested Outcome', 'Untrusted / Conflicting Instructions')): 1
- claims found verbatim in the reasoning: 871/871
