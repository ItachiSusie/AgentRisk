"""v20 Med synthetic executor fixes.

Rationale (see docs/medsec-v20-executor-fixes.md):
  1. one JSON action per turn, with parse-failure feedback + bounded retries
     instead of terminating the episode on the first unparseable response;
  2. strip internal provenance (attack_id, hashes, source_episode) from the
     memory rows shown to the model so the attack is not self-revealing;
  3. a non-echo "judgment" memory task family so memory-poisoning ASR measures
     whether the agent is actually fooled, not whether it copies text.

v08 modules are imported unchanged so that frozen v08/v12/v17 runs keep
recomputing; nothing here edits src/medsec/v08/.
"""
