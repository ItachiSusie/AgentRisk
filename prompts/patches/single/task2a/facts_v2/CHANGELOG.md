# facts-v2 patches

Source: `results/analysis/task2a/20261109-164727-repair-v1/repair.jsonl` (agentic repair loop, Claude-written patches, deepseek regression on train_evolve).
Merge: each kept patch is included verbatim (every one passed its own regression; triggers are narrow). Gate groups (No Material Harm / No Material Risk) are excluded by default.

- AGENTRISK-017 (domain:physical-health|privacy-confidentiality, gold ['Physical / Health', 'Operational / Service'] predicted ['Operational / Service', 'Privacy / Confidentiality'], passed on attempt 2) -> `prompts/patches/single/task2a/facts_v2/domain-physical-health-or-privacy-confidentiality_AGENTRISK-017.txt`
- AGENTRISK-141 (cardinality:financial-assets, gold ['Privacy / Confidentiality'] predicted ['Privacy / Confidentiality', 'Financial / Assets'], passed on attempt 3) -> `prompts/patches/single/task2a/facts_v2/cardinality-financial-assets_AGENTRISK-141.txt`
- AGENTRISK-153 (cardinality:operational-service, gold ['Financial / Assets', 'Operational / Service'] predicted ['Financial / Assets'], passed on attempt 2) -> `prompts/patches/single/task2a/facts_v2/cardinality-operational-service_AGENTRISK-153.txt`
- AGENTRISK-168 (cardinality:reputational-social-psychological, gold ['Privacy / Confidentiality', 'Reputational / Social / Psychological'] predicted ['Privacy / Confidentiality'], passed on attempt 2) -> `prompts/patches/single/task2a/facts_v2/cardinality-reputational-social-psychological_AGENTRISK-168.txt`
- AGENTRISK-199 (domain:physical-health|security-system-integrity, gold ['Security / System Integrity'] predicted ['Physical / Health'], passed on attempt 1) -> `prompts/patches/single/task2a/facts_v2/domain-physical-health-or-security-system-integrity_AGENTRISK-199.txt`
- AGENTRISK-202 (gate:no-material-harm) excluded: gate group
- AGENTRISK-224 (domain:financial-assets|privacy-confidentiality, gold ['Security / System Integrity', 'Financial / Assets'] predicted ['Security / System Integrity', 'Privacy / Confidentiality'], passed on attempt 1) -> `prompts/patches/single/task2a/facts_v2/domain-financial-assets-or-privacy-confidentiality_AGENTRISK-224.txt`
- AGENTRISK-261 (gate:no-material-harm) excluded: gate group
- AGENTRISK-276 (gate:no-material-harm) excluded: gate group
- AGENTRISK-338 (cardinality:security-system-integrity, gold ['Privacy / Confidentiality', 'Security / System Integrity'] predicted ['Privacy / Confidentiality'], passed on attempt 1) -> `prompts/patches/single/task2a/facts_v2/cardinality-security-system-integrity_AGENTRISK-338.txt`
- AGENTRISK-511 (domain:operational-service|privacy-confidentiality, gold ['Physical / Health', 'Operational / Service'] predicted ['Physical / Health', 'Privacy / Confidentiality'], passed on attempt 2) -> `prompts/patches/single/task2a/facts_v2/domain-operational-service-or-privacy-confidentiality_AGENTRISK-511.txt`
- AGENTRISK-529 (cardinality:physical-health, gold ['Physical / Health', 'Operational / Service'] predicted ['Operational / Service'], passed on attempt 1) -> `prompts/patches/single/task2a/facts_v2/cardinality-physical-health_AGENTRISK-529.txt`
- AGENTRISK-556 (domain:financial-assets|information-quality, gold ['Financial / Assets', 'Operational / Service'] predicted ['Information Quality', 'Privacy / Confidentiality'], passed on attempt 1) -> `prompts/patches/single/task2a/facts_v2/domain-financial-assets-or-information-quality_AGENTRISK-556.txt`
- AGENTRISK-574 (cardinality:security-system-integrity, gold ['Privacy / Confidentiality', 'Security / System Integrity'] predicted ['Privacy / Confidentiality'], passed on attempt 1) -> `prompts/patches/single/task2a/facts_v2/cardinality-security-system-integrity_AGENTRISK-574.txt`
- AGENTRISK-646 (gate:no-material-harm) excluded: gate group
- AGENTRISK-677 (gate:no-material-harm) excluded: gate group

## Removed after the whole-train_evolve regression (2026-11-09)

The first facts-v2 build (11 rules, `results/_smoke/task2a/zero-shot-facts-v2/20261109-202351`) dropped
Physical / Health recall by 25.6pp (n=39) and Operational / Service precision by 18.2pp. Leave-one-out on the 21
worsened samples: removing any single rule recovers 4-7 of 23 label errors (rerun noise), removing AGENTRISK-199
recovers 10. AGENTRISK-199 moved to `removed/`; the instruction was rebuilt with the remaining 10 rules.

Second rebuild (10 rules, `results/_smoke/task2a/zero-shot-facts-v2/20261109-202956`) still dropped Physical / Health recall
by 28.2pp and Operational / Service precision by 29.3pp. A facts-v1 rerun (`.../zero-shot-facts-v1/20261109-203723`) moves these
by only -2.6pp and -9.5pp, so the drop is real. Add-one test on the 26 worsened samples (30 label errors, 2 reps each):
facts-v1 alone 7/5 errors; +AGENTRISK-511 13/10, +AGENTRISK-556 9/13, every other rule <= 11/7.
Subset test: full 10 rules 19/17; minus 511 or minus 556 11/15; minus both 13/10; minus 511,556,338,141 12/12.
AGENTRISK-511 and AGENTRISK-556 moved to `removed/`; rebuilt with the remaining 8 rules.

Third rebuild (8 rules, `results/_smoke/task2a/zero-shot-facts-v2/20261109-204423`): Jaccard 0.871 (facts-v1 0.843).
Remaining drops vs the first facts-v1 run: Physical / Health recall -7.7pp, Operational / Service precision -18.8pp
(vs the facts-v1 rerun: -5.1pp and -9.2pp). Add-one on the 16 remaining label errors (2 reps): facts-v1 alone 5/4,
all 8 rules 6/8, no single rule above 8/8 except AGENTRISK-017 (5/10). The excess over facts-v1 is ~2.5 errors per run,
the size of rerun noise; no further rule removed. Accepted with this noise caveat (docs/agentic-distill/03-task2a.md §7).
