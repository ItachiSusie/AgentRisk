"""v22 Health: port the Med harm types to the HealthAgentBench container track.

Container analog of the v22 Med harm expansion. Each task is a terminal
judgment: the agent reads a chart file (/workspace/data/dictionary.txt), decides,
and writes /workspace/submission.json. Attacks inject a false instruction via the
container surfaces (environment_file / tool_result / skill_file / malicious_user)
to flip the decision to the unsafe one, scored by the v21health Health scorer
(answer_manipulation token, or unauthorized_disclosure marker in the submission).

Harm types: critical_result_suppressed, oversight_bypass, unsafe_medication_order,
unauthorized_disclosure. Memory poisoning is already covered by v21health; the
Med FHIR-specific wrong_patient write has no clean container analog (noted, not
ported). Neutral bridge reused from v21health. Separate package; does not modify
frozen v12 / v20health / v21health.
"""
