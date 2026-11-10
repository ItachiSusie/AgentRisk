# Audit v3 summary

- audited: 107

## status

| value | n | share |
| --- | --- | --- |
| kept | 95 | 89% |
| discarded:gold_questionable | 10 | 9% |
| discarded:unexplained | 2 | 2% |

## fact_layer

| value | n | share |
| --- | --- | --- |
| correct | 68 | 64% |
| misread | 20 | 19% |
| misread+missed | 10 | 9% |
| missed | 9 | 8% |

## category

| value | n | share |
| --- | --- | --- |
| cardinality | 43 | 40% |
| reading | 26 | 24% |
| confusable_pair | 13 | 12% |
| missed_harm | 13 | 12% |
| gold_questionable | 10 | 9% |
| unexplained | 2 | 2% |

- contradiction rate before re-ask: 1/107 = 1%
- still contradictory after re-ask: 0

## blind_implied versus gold / prediction

| value | n | share |
| --- | --- | --- |
| == gold | 67 | 63% |
| == prediction | 40 | 37% |

- cannot tell the two levels apart (v3c cannot_tell / v3, v3b adjacent_defensible): 0/107
- pairs (gold, prediction): (('Discrimination / Fairness', 'Legal / Compliance'), ('Discrimination / Fairness',)): 1, (('Environmental', 'Legal / Compliance'), ('Environmental', 'Financial / Assets')): 1, (('Financial / Assets',), ('Financial / Assets', 'Information Quality')): 1, (('Financial / Assets',), ('Financial / Assets', 'Privacy / Confidentiality')): 1, (('Financial / Assets',), ('Financial / Assets', 'Security / System Integrity')): 1, (('Financial / Assets',), ('No Material Harm',)): 4, (('Financial / Assets', 'Legal / Compliance'), ('Financial / Assets',)): 1, (('Financial / Assets', 'Operational / Service'), ('Financial / Assets',)): 1, (('Financial / Assets', 'Operational / Service'), ('Information Quality', 'Operational / Service')): 2, (('Financial / Assets', 'Operational / Service'), ('Information Quality', 'Privacy / Confidentiality')): 1, (('Financial / Assets', 'Operational / Service'), ('Operational / Service', 'Security / System Integrity')): 1, (('Financial / Assets', 'Privacy / Confidentiality'), ('Privacy / Confidentiality',)): 6, (('Financial / Assets', 'Security / System Integrity'), ('Financial / Assets', 'Privacy / Confidentiality')): 1, (('Financial / Assets', 'Security / System Integrity'), ('Privacy / Confidentiality', 'Security / System Integrity')): 1, (('Information Quality',), ('No Material Harm',)): 1, (('Information Quality', 'Legal / Compliance'), ('No Material Harm',)): 1, (('Information Quality', 'Physical / Health'), ('Physical / Health',)): 1, (('Legal / Compliance', 'Privacy / Confidentiality'), ('Privacy / Confidentiality',)): 6, (('Legal / Compliance', 'Reputational / Social / Psychological'), ('Privacy / Confidentiality',)): 1, (('Legal / Compliance', 'Security / System Integrity'), ('No Material Harm',)): 1, (('No Material Harm',), ('Financial / Assets',)): 1, (('No Material Harm',), ('Physical / Health',)): 1, (('No Material Harm',), ('Privacy / Confidentiality',)): 3, (('No Material Harm',), ('Privacy / Confidentiality', 'Reputational / Social / Psychological')): 1, (('Operational / Service',), ('Information Quality', 'Operational / Service')): 1, (('Operational / Service',), ('No Material Harm',)): 4, (('Operational / Service', 'Physical / Health'), ('Legal / Compliance', 'Physical / Health')): 1, (('Operational / Service', 'Physical / Health'), ('No Material Harm',)): 2, (('Operational / Service', 'Physical / Health'), ('Operational / Service',)): 1, (('Operational / Service', 'Physical / Health'), ('Operational / Service', 'Privacy / Confidentiality')): 1, (('Operational / Service', 'Physical / Health'), ('Physical / Health',)): 3, (('Operational / Service', 'Physical / Health'), ('Physical / Health', 'Privacy / Confidentiality')): 1, (('Operational / Service', 'Reputational / Social / Psychological'), ('Physical / Health', 'Privacy / Confidentiality')): 1, (('Operational / Service', 'Security / System Integrity'), ('Operational / Service',)): 3, (('Operational / Service', 'Security / System Integrity'), ('Security / System Integrity',)): 1, (('Physical / Health',), ('No Material Harm',)): 2, (('Physical / Health', 'Privacy / Confidentiality'), ('Privacy / Confidentiality',)): 1, (('Physical / Health', 'Security / System Integrity'), ('Information Quality', 'Physical / Health')): 1, (('Physical / Health', 'Security / System Integrity'), ('Legal / Compliance', 'Physical / Health')): 1, (('Physical / Health', 'Security / System Integrity'), ('Physical / Health',)): 2, (('Physical / Health', 'Security / System Integrity'), ('Security / System Integrity',)): 1, (('Privacy / Confidentiality',), ('Financial / Assets', 'Privacy / Confidentiality')): 11, (('Privacy / Confidentiality',), ('Legal / Compliance', 'Privacy / Confidentiality')): 2, (('Privacy / Confidentiality',), ('No Material Harm',)): 4, (('Privacy / Confidentiality',), ('Privacy / Confidentiality', 'Reputational / Social / Psychological')): 1, (('Privacy / Confidentiality',), ('Privacy / Confidentiality', 'Security / System Integrity')): 1, (('Privacy / Confidentiality', 'Reputational / Social / Psychological'), ('Privacy / Confidentiality',)): 1, (('Privacy / Confidentiality', 'Security / System Integrity'), ('Legal / Compliance', 'Privacy / Confidentiality')): 1, (('Privacy / Confidentiality', 'Security / System Integrity'), ('No Material Harm',)): 3, (('Privacy / Confidentiality', 'Security / System Integrity'), ('Privacy / Confidentiality',)): 12, (('Privacy / Confidentiality', 'Security / System Integrity'), ('Privacy / Confidentiality', 'Reputational / Social / Psychological')): 1, (('Security / System Integrity',), ('No Material Harm',)): 1, (('Security / System Integrity',), ('Physical / Health',)): 1, (('Security / System Integrity',), ('Physical / Health', 'Security / System Integrity')): 1
- claims found verbatim in the reasoning: 628/628
