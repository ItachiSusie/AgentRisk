"""v21: neutral base agent for calibrated attack difficulty.

Same executor fixes as v20 (one-action-per-turn + parse-retry, metadata-stripped
memory, OSError-safe tool handling), but the system prompt is a plain, helpful
clinical assistant with NO built-in injection defense ("treat data as untrusted",
"only act on the named patient" are removed). This defines the real `none`
(no-mitigation) baseline so that an injected instruction can actually land; the
`scope` policy remains the mitigation to compare against.

Separate package from src/medsec/v20/ so the frozen v20 runs keep their code
hashes. Used to synthesize and calibrate attacks that genuinely succeed against
the reference model, instead of a benchmark whose ASR is ~0 by construction.
"""
