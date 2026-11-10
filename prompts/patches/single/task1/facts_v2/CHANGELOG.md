# facts-v2 patches

Source: `results/analysis/task1/20261107-082751-repair-v1/repair.jsonl` (agentic repair loop, Claude-written patches, deepseek regression on train_evolve).
Merge: each kept patch is included verbatim (every one passed its own regression; triggers are narrow). The severity-1|2 gate group is excluded by default (docs/agentic-distill/02-task1.md §0.1).

- AGENTRISK-017 (severity-3|4, 4 predicted as 3, passed on attempt 2) -> `prompts/patches/single/task1/facts_v2/severity-3-or-4_AGENTRISK-017.txt`
- AGENTRISK-111 (severity-2|3, 2 predicted as 3, passed on attempt 3) -> `prompts/patches/single/task1/facts_v2/severity-2-or-3_AGENTRISK-111.txt`
- AGENTRISK-122 (severity-3|4, 3 predicted as 4, passed on attempt 1) -> `prompts/patches/single/task1/facts_v2/severity-3-or-4_AGENTRISK-122.txt`
- AGENTRISK-224 (severity-3|4, 3 predicted as 4, passed on attempt 3) -> `prompts/patches/single/task1/facts_v2/severity-3-or-4_AGENTRISK-224.txt`
- AGENTRISK-442 (severity-2|3, 3 predicted as 2, passed on attempt 1) -> `prompts/patches/single/task1/facts_v2/severity-2-or-3_AGENTRISK-442.txt`
- AGENTRISK-494 (severity-1|2) excluded: gate group
- AGENTRISK-561 (severity-3|4, 3 predicted as 4, passed on attempt 2) -> `prompts/patches/single/task1/facts_v2/severity-3-or-4_AGENTRISK-561.txt`
- AGENTRISK-562 (severity-3|4, 3 predicted as 4, passed on attempt 3) -> `prompts/patches/single/task1/facts_v2/severity-3-or-4_AGENTRISK-562.txt`
- AGENTRISK-623 (severity-3|4, 4 predicted as 3, passed on attempt 3) -> `prompts/patches/single/task1/facts_v2/severity-3-or-4_AGENTRISK-623.txt`
- AGENTRISK-634 (severity-3|4, 3 predicted as 4, passed on attempt 2) -> `prompts/patches/single/task1/facts_v2/severity-3-or-4_AGENTRISK-634.txt`
