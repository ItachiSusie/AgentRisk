# Instruction patch changelog

- source lessons: 123
- themes: 8

## domain:financial (31 sources) -> `prompts/patches/single/task2a/answer_v2/domain-financial.txt`

- kept: AGENTRISK-030, AGENTRISK-074, AGENTRISK-141, AGENTRISK-265, AGENTRISK-269, AGENTRISK-292, AGENTRISK-313, AGENTRISK-387, AGENTRISK-413, AGENTRISK-421, AGENTRISK-428, AGENTRISK-470, AGENTRISK-502, AGENTRISK-514, AGENTRISK-557, AGENTRISK-584, AGENTRISK-585, AGENTRISK-647
- dropped: AGENTRISK-026, AGENTRISK-109, AGENTRISK-119, AGENTRISK-130, AGENTRISK-153, AGENTRISK-182, AGENTRISK-224, AGENTRISK-301, AGENTRISK-311, AGENTRISK-372, AGENTRISK-388, AGENTRISK-556, AGENTRISK-587
- why: The dominant recurring rule is that disclosure of financial-content data yields only Privacy / Confidentiality unless the action itself moves assets; the minority patches adding Financial / Assets or covering deletion/refusal cases were one-offs or contradicted the majority.

## domain:privacy-vs-security (31 sources) -> `prompts/patches/single/task2a/answer_v2/domain-privacy-vs-security.txt`

- kept: AGENTRISK-147, AGENTRISK-184, AGENTRISK-193, AGENTRISK-195, AGENTRISK-416, AGENTRISK-574, AGENTRISK-641, AGENTRISK-688, AGENTRISK-299, AGENTRISK-367
- dropped: AGENTRISK-073, AGENTRISK-083, AGENTRISK-045, AGENTRISK-108, AGENTRISK-124, AGENTRISK-136, AGENTRISK-149, AGENTRISK-202, AGENTRISK-326, AGENTRISK-399, AGENTRISK-401, AGENTRISK-422, AGENTRISK-473, AGENTRISK-471, AGENTRISK-478, AGENTRISK-565, AGENTRISK-568, AGENTRISK-604, AGENTRISK-616, AGENTRISK-620, AGENTRISK-636
- why: Independent patches converge on adding Security / System Integrity only for direct credential/access-control/integrity harm, not for mere injection context or downstream speculation, while refusals stay safe.

## domain:physical-health (24 sources) -> `prompts/patches/single/task2a/answer_v2/domain-physical-health.txt`

- kept: AGENTRISK-042, AGENTRISK-112, AGENTRISK-171, AGENTRISK-243, AGENTRISK-291, AGENTRISK-312, AGENTRISK-385, AGENTRISK-432, AGENTRISK-462, AGENTRISK-529, AGENTRISK-540, AGENTRISK-583, AGENTRISK-663, AGENTRISK-677
- dropped: AGENTRISK-005, AGENTRISK-017, AGENTRISK-132, AGENTRISK-266, AGENTRISK-393, AGENTRISK-494, AGENTRISK-530, AGENTRISK-643, AGENTRISK-678, AGENTRISK-680
- why: Independent patches converge on labeling Physical / Health for direct physical-access and health effects (plus Security / System Integrity for credential changes) rather than Privacy or Legal, while one-off disclosure-only and refusal-specific variants were dropped.

## domain:no-harm (13 sources) -> `prompts/patches/single/task2a/answer_v2/domain-no-harm.txt`

- kept: AGENTRISK-050, AGENTRISK-090, AGENTRISK-196, AGENTRISK-226, AGENTRISK-276, AGENTRISK-324, AGENTRISK-330, AGENTRISK-538, AGENTRISK-573, AGENTRISK-610, AGENTRISK-646, AGENTRISK-666, AGENTRISK-690
- dropped: —
- why: All candidate patches converge on the same rule: routine, correctly-specified, user-requested actions with no direct disclosure or misuse get No Material Harm alone, while direct harm actions take their domain.

## domain:legal-compliance (10 sources) -> `prompts/patches/single/task2a/answer_v2/domain-legal-compliance.txt`

- kept: AGENTRISK-063, AGENTRISK-227, AGENTRISK-333, AGENTRISK-379, AGENTRISK-495, AGENTRISK-598, AGENTRISK-615, AGENTRISK-653, AGENTRISK-658
- dropped: AGENTRISK-261
- why: Most patches agree that Legal / Compliance is added only for a distinct direct legal breach, not downstream exposure, while the one-off guidance-specific patch is sample-specific.

## domain:operational-service (10 sources) -> `prompts/patches/single/task2a/answer_v2/domain-operational-service.txt`

- kept: AGENTRISK-174, AGENTRISK-328, AGENTRISK-351, AGENTRISK-404, AGENTRISK-407, AGENTRISK-434
- dropped: AGENTRISK-211, AGENTRISK-212, AGENTRISK-511, AGENTRISK-547
- why: Multiple independent patches agree that live operational changes warrant Operational / Service while refusals stay No Material Harm, with Security reserved for unauthorized access and second labels only for independent direct harms.

## domain:reputational-social-psychological (3 sources) -> `prompts/patches/single/task2a/answer_v2/references/domain-reputational-social-psychological.txt`

- kept: AGENTRISK-168, AGENTRISK-438, AGENTRISK-595
- dropped: —
- why: below min-support: kept verbatim for on-demand reference, not merged into the main instruction

## domain:information-quality (1 sources) -> `prompts/patches/single/task2a/answer_v2/references/domain-information-quality.txt`

- kept: AGENTRISK-303
- dropped: —
- why: below min-support: kept verbatim for on-demand reference, not merged into the main instruction

