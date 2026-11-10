# Audit v3 summary

- audited: 41

## status

| value | n | share |
| --- | --- | --- |
| kept | 39 | 95% |
| discarded:contradiction | 2 | 5% |

## fact_layer

| value | n | share |
| --- | --- | --- |
| correct | 38 | 93% |
| missed | 2 | 5% |
| misread | 1 | 2% |

## category

| value | n | share |
| --- | --- | --- |
| threshold | 27 | 66% |
| weighting | 13 | 32% |
| reading | 1 | 2% |

- contradiction rate before re-ask: 18/41 = 44%
- still contradictory after re-ask: 2

## blind_implied versus gold / prediction

| value | n | share |
| --- | --- | --- |
| == prediction | 28 | 68% |
| == gold | 13 | 32% |

- cannot tell the two levels apart (v3c cannot_tell / v3, v3b adjacent_defensible): 0/41
- pairs (gold, prediction): (3, 4): 20, (4, 3): 21
- claims found verbatim in the reasoning: 198/198
