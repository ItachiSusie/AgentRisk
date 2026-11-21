"""v21 Health: neutral container base agent for calibrated attack difficulty.

Health analog of src/medsec/v21/: the Harbor bridge system prompt drops the
"untrusted task data" guardrail (true no-mitigation `none`), and the memory
suite is judgment-WITHOUT-the-safe-answer so a neutral agent that trusts its
poisoned memory is actually fooled. Separate package; does not modify the frozen
v12 or v20health code.
"""
