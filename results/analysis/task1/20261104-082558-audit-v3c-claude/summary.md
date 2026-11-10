# Audit v3 summary

- audited: 41

## status

| value | n | share |
| --- | --- | --- |
| kept | 35 | 85% |
| discarded:unexplained | 6 | 15% |

## fact_layer

| value | n | share |
| --- | --- | --- |
| correct | 22 | 54% |
| misread | 9 | 22% |
| missed | 5 | 12% |
| misread+missed | 5 | 12% |

## category

| value | n | share |
| --- | --- | --- |
| threshold | 15 | 37% |
| reading | 13 | 32% |
| weighting | 7 | 17% |
| unexplained | 6 | 15% |

- contradiction rate before re-ask: 6/41 = 15%
- still contradictory after re-ask: 0

## blind_implied versus gold / prediction

| value | n | share |
| --- | --- | --- |
| == prediction | 21 | 51% |
| == gold | 20 | 49% |

- cannot tell the two levels apart (v3c cannot_tell / v3, v3b adjacent_defensible): 0/41
- pairs (gold, prediction): (3, 4): 20, (4, 3): 21
- claims found verbatim in the reasoning: 192/192
