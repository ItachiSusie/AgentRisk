"""v25: a content-level injection guardrail defense for the API base.

`none` and `scope` (the existing defenses) are, respectively, no mitigation and a
patient-identity/scope filter. v25 adds a third, content-level defense: an
API-based guardrail that screens every untrusted observation (tool/record/skill/
memory output and the requester message) through an LLM safety filter that strips
embedded instructions attempting to change the agent's clinical decision, before
the observation reaches the agent. This tests the paper's claim that identity-level
defenses miss content-level harms, with a real content-level control.

Separate package; reuses the frozen v08 primitives and the neutral v21 loop
without editing them (the v25 episode is a copy of v21's with a guardrail hook).
"""
