# Audit v3 summary

- audited: 41

## status

| value | n | share |
| --- | --- | --- |
| kept | 33 | 80% |
| discarded:unexplained | 8 | 20% |

## fact_layer

| value | n | share |
| --- | --- | --- |
| correct | 20 | 49% |
| misread | 10 | 24% |
| missed | 7 | 17% |
| misread+missed | 4 | 10% |

## category

| value | n | share |
| --- | --- | --- |
| reading | 13 | 32% |
| threshold | 11 | 27% |
| weighting | 9 | 22% |
| unexplained | 8 | 20% |

- contradiction rate before re-ask: 9/41 = 22%
- still contradictory after re-ask: 0

## blind_implied versus gold / prediction

| value | n | share |
| --- | --- | --- |
| == gold | 22 | 54% |
| == prediction | 19 | 46% |

- cannot tell the two levels apart (v3c cannot_tell / v3, v3b adjacent_defensible): 0/41
- pairs (gold, prediction): (3, 4): 20, (4, 3): 21
- claims found verbatim in the reasoning: 194/194
