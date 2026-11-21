"""v20 Health (HealthAgentBench synthetic) container-track fixes.

Mirrors the Med v20 fixes for the Harbor container track, as a separate package
that does NOT modify the frozen v08/v11/v12 code or the in-use src/medsec/v20/
package:

  * judgment-style (non-echo) memory tasks, so memory-poisoning ASR measures
    whether the agent is fooled, not whether it copies the retrieved text;
  * the Harbor bridge reads the v20 MemoryStore (which hides attack_id and
    internal provenance from the model-visible observation) and detects the
    attack trigger from the memory_retrieved EVENT log rather than from the
    model-visible row.

The container executor already handled multi-action responses (raw_decode +
feedback + continue) in v12, so that fix is not repeated here.
"""
