# Audit v3 summary

- audited: 128

## status

| value | n | share |
| --- | --- | --- |
| kept | 126 | 98% |
| discarded:unexplained | 1 | 1% |
| discarded:gold_questionable | 1 | 1% |

## fact_layer

| value | n | share |
| --- | --- | --- |
| correct | 83 | 65% |
| missed | 28 | 22% |
| misread+missed | 12 | 9% |
| misread | 5 | 4% |

## category

| value | n | share |
| --- | --- | --- |
| scale | 82 | 64% |
| reading | 44 | 34% |
| unexplained | 1 | 1% |
| gold_questionable | 1 | 1% |

- contradiction rate before re-ask: 2/128 = 2%
- still contradictory after re-ask: 0

## blind_implied versus gold / prediction

| value | n | share |
| --- | --- | --- |
| == gold | 88 | 69% |
| == prediction | 40 | 31% |

- cannot tell the two levels apart (v3c cannot_tell / v3, v3b adjacent_defensible): 0/128
- pairs (gold, prediction): (1, 2): 9, (1, 3): 1, (2, 1): 11, (2, 3): 7, (3, 1): 4, (3, 2): 5, (3, 4): 52, (3, 5): 1, (4, 2): 4, (4, 3): 16, (4, 5): 16, (5, 4): 2
- claims found verbatim in the reasoning: 793/793
