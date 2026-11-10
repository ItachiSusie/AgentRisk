# Evolve: implementation spec

Status: design, not implemented. Date: 2026-11-09.
Companion document: [eval.md](eval.md) (how we decide whether the algorithm works).
Background: [research report](../../reports/AgentRisk%20提示词蒸馏优化.md), and the
post-mortem of the Trace2Skill round in `docs/single-task/01..03-*.md` (gate I tables).

## 1. Goal and scope

Improve the **zero-shot, reason-lineage** instruction of one single-task predictor
(`task1`, `task2a` or `task2b`) using only `train_evolve`, by repeatedly proposing small
edits to the prompt text and keeping an edit only if it helps on data it was not derived from.

In scope: one task per run, deepseek-flash as both predictor and proposer, temperature-0
prediction, zero-shot only. Out of scope for v1: few-shot retrieval inside the loop (tested
after export, see eval.md), multi-task prompts, Task 3, other models.

What it fixes relative to the previous Trace2Skill round:

| Previous round | Evolve |
|---|---|
| Lessons from failures only | Each proposal sees wrong items **and** similar items the model got right |
| One lesson per error (869 calls), then LLM merge | One batch per round, the proposer returns complete candidate edits; no merge step |
| Rules appended as "TRIGGER → assign X" | Local edits to the existing text (rewrite, insert, delete) |
| Analyst sees gold first | Blind re-read of the evidence first, gold revealed second |
| All rules inserted, checked once at the end | Each edit checked alone, on ~370 unseen items, with a flip ledger |

## 2. Terms

- **Fold** — one of the 5 scenario-group folds of `train_evolve` in
  `data/splits/train_evolve_folds.json` (built by `src/make_folds.py`; 91–95 rows each).
- **Proposing fold** `F_k` — the fold a round draws its examples from. Rotates `k = round mod 5`.
- **Evaluation folds** — the other four folds (~370 rows). Acceptance is decided only here.
- **Champion** — the current best prompt. Starts as a seed prompt.
- **Candidate** — the champion with one edit applied.
- **Target cell** — the error type a round tries to fix (e.g. Task 1 gold 3 → predicted 4;
  Task 2b gold `Authorization / Consent Failure` → predicted `Scope / Safeguard Failure`).
- **Per-item loss** — Task 1: `|pred − gold|`; Task 2a/2b: `1 − Jaccard(pred, gold)`. Same
  definitions as `src/paired_bootstrap.py:per_sample`.
- **Flip ledger** — per item, compare champion loss and candidate loss:
  *improved* (loss went down), *worsened* (went up), *right→wrong* (loss 0 → >0),
  *wrong→right* (>0 → 0). Net flips = improved − worsened.
- **Noise floor τ** — number of items whose prediction differs between two identical runs of
  the champion (temperature 0 is not guaranteed deterministic).

## 3. Data roles (hard rules)

| Data | Used for | Never used for |
|---|---|---|
| `F_k` (proposing fold) | target selection, contrast batch, proposer input | accepting its own round's edits |
| other 4 folds | quick gate, full gate | proposer input in that round |
| `train_val` (107) | one confirmation run per exported prompt (eval.md) | anything inside the loop |
| `dev` (143) | one final run (eval.md) | anything inside the loop |

The code must refuse to start if `data/splits/train_evolve_folds.json` fails
`make_folds.py --check`, and must assert that no proposer payload contains an id outside `F_k`.

## 4. Algorithm

```
init:
    seeds = [reason-v1 prompt (+ optional extra seeds)]
    for s in seeds: predict s on all 461 items              # cached by (prompt_sha, id)
    predict seeds[0] a second time on all 461 → τ
    champion = seed with the lowest mean loss over 461

for round t = 1 .. max_rounds:
    k = t mod 5
    cell = pick_target(champion predictions on F_k, skip cells that failed twice in a row)
    if cell has < min_wrong items in F_k: try next cell; if none: skip round
    batch = contrast_batch(F_k, cell)                         # m_wrong wrong + m_right right
    blind = proposer_blind(batch without gold)                # call 1
    edits = proposer_edit(champion prompt, blind, gold)       # call 2 → n_candidates edits
    candidates = [apply(champion, e) for e in edits if valid(e)]
    quick = [c for c in candidates if quick_gate(c, quick_set(t))]
    full  = [c for c in quick[:max_full] if full_gate(c, eval_folds(k))]
    if full:
        champion = best(full by net flips, then mean loss)
        predict champion on F_k                                # so it has all 461 predictions
        patience = 0
    else:
        patience += 1
    if patience == max_patience: stop

export champion → prompts/single/<task>/zero_shot_reason_v<N>.txt  (+ CHANGELOG)
```

### 4.1 Target selection (`pick_target`)

Computed on the champion's predictions **for `F_k` only**.

- Task 1: cells `(gold g, pred p)`, `g ≠ p`, cost = count × |g − p|.
- Task 2a/2b: cells `(missing gold label A, extra predicted label B)` from
  `triage.confusion_pairs`, plus pure FN `(A, ∅)` and pure FP `(∅, B)` cells; cost = count.

Pick the highest-cost cell that has at least `min_wrong` items in `F_k` and has not been
targeted unsuccessfully in the last 2 rounds that targeted it.

### 4.2 Contrast batch (`contrast_batch`)

- **Wrong**: up to `m_wrong` items of `F_k` in the target cell.
- **Right**: up to `m_right` items of `F_k` with loss 0 whose gold sits on either side of the
  boundary (Task 1: gold ∈ {g, p}; Task 2: gold contains A or B), chosen as BM25 nearest
  neighbours of the wrong items (reuse `analyst.build_pool` / `analyst.neighbours`).
- Item order is shuffled with a seed derived from the round number; wrong/right is **not**
  marked in the blind call.

Each item carries: `example_id`, `formatted_interaction`, `proposed_action`, the champion's
prediction and stated reasoning. Long trajectories are truncated with the same rule as
`analyst.dossier` (keep the end, which holds the proposed action).

### 4.3 Proposer call 1: blind re-read

Prompt file: `prompts/evolve/proposer_blind_v1.txt` (frozen once used).
Input: task definition (the label section of the champion prompt), the batch, no gold.
Output JSON, per item: the facts that decide this boundary, each with a verbatim quote
from the trajectory, and whether the model's reasoning misread or missed any of them.

### 4.4 Proposer call 2: reveal and edit

Prompt file: `prompts/evolve/proposer_edit_v1.txt` (frozen once used).
Input: champion prompt text, call-1 output, gold labels, which items are wrong.
Output JSON:

```json
{
  "faults": [{"example_id": "...", "fault": "misread_evidence|missed_evidence|wrong_rule|sound_but_wrong"}],
  "edits": [
    {
      "edit_type": "definition | pre_check | conditional | delete",
      "op": "replace | insert_after | delete",
      "anchor": "exact text that occurs once in the current prompt",
      "new_text": "replacement or inserted text ('' for delete)",
      "rationale": "one sentence",
      "fixes": [{"example_id": "...", "quote": "verbatim trajectory text"}],
      "must_not_change": ["example_id of a right item this edit must leave alone"]
    }
  ]
}
```

Rules given to the proposer:
- exactly `n_candidates` edits, **one per edit type** (forces diversity);
- `pre_check` is preferred when most faults are evidence faults, `definition` /
  `conditional` when most are `wrong_rule`;
- if most wrong items are `sound_but_wrong`, return no edits (likely label noise) — the round
  is then logged as skipped, not failed;
- no entity names, ids or quotes from the batch inside `new_text`.

### 4.5 Edit validation (`valid`, `apply`)

An edit is dropped (logged with the reason) if any check fails:
1. `anchor` occurs exactly once in the champion prompt.
2. Every `fixes[].quote` is found in that item's trajectory (reuse `analyst.quote_in_text`),
   and at least 2 distinct items are cited.
3. Protected text survives byte-for-byte: every label name of the task (from `common.py`
   `DOMAINS` / `DRIVERS` / severity scale lines) and the output-format tail (from the first
   anchor in `assemble_instruction.ANCHORS` to the end).
4. `new_text` is ≤ `max_edit_words`, and the candidate is ≤ seed length + `max_growth_words`.
5. `new_text` contains no token sequence ≥ 4 words copied from any batch trajectory, and no
   `AGENTRISK-` id.
6. The candidate is not identical (after whitespace normalisation) to any prompt already tried
   in this run.

### 4.6 Quick gate

Quick set: `quick_n` items from the four evaluation folds, fixed per round (seeded):
half from the target boundary (gold on either side of it, including items the champion gets
right), half stratified random. Reject a candidate if right→wrong ≥ `quick_max_rw` or
net flips ≤ 0. Pass at most `max_full` candidates (best net flips first) to the full gate.

### 4.7 Full gate

Run on all items of the four evaluation folds (~370). Accept only if **all** hold:

| Gate | Condition (defaults) |
|---|---|
| G1 gain | net flips ≥ max(`min_net`, 2·τ_scaled) and P(better) ≥ `p_better` from `paired_bootstrap.bootstrap` (3000 iterations) |
| G2 no damage | right→wrong ≤ `max_rw_frac` × champion-correct items; Task 1: items with gold 1 that become wrong ≤ `max_gold1_loss` |
| G3 no shifting | Task 1: per-gold-level mean signed error does not grow in absolute value by more than 0.05 for any level with ≥ 10 items; Task 2: mean predicted label count moves ≤ 0.1, and no label has FP down while FN up with FP+FN not lower |
| G4 size | already enforced in 4.5 |
| G5 stability | loss difference has the accepted sign in ≥ 3 of the 4 evaluation folds |
| G6 validity | invalid-output count not higher than the champion's |

τ_scaled = τ × (eval items / 461). Invalid outputs (after `MAX_ATTEMPTS` retries) count as
loss 1 (Task 2) or 4 (Task 1, worst case) for gating, and are reported separately.

### 4.8 Stopping

Stop when `max_patience` consecutive rounds accept nothing (skipped rounds do not count),
or `max_rounds` is reached, or the token budget is exhausted (checked before every API batch;
the run stops cleanly and stays resumable).

## 5. Parameters (defaults)

| Name | Default | Note |
|---|---|---|
| `k_folds` | 5 | read from the folds file |
| `max_rounds` | 8 | ProTeGi peaks around step 3 (report §APO); 8 leaves room for rotation |
| `max_patience` | 2 | |
| `n_candidates` | 4 | one per edit type; revisit after the pilot (similar candidates → 4 separate calls) |
| `m_wrong` / `m_right` | 8 / 8 | |
| `min_wrong` | 4 | |
| `quick_n` | 40 | |
| `quick_max_rw` | 2 | |
| `max_full` | 2 | |
| `min_net` | 5 | |
| `p_better` | 0.9 | deliberately looser than "CI excludes 0"; the cumulative gain is tested in eval.md |
| `max_rw_frac` | 0.03 | |
| `max_gold1_loss` | 2 | Task 1 only |
| `max_edit_words` | 60 | |
| `max_growth_words` | 150 | |
| `proposer_temperature` | 0.7 | responses are persisted, so reruns replay them |
| `budget_tokens` | 30M input tokens per run | |

All parameters are written to `config.json`; changing one means a new run.

## 6. Code layout

New file `src/evolve.py` (CLI) plus small helpers; reuse instead of copying:

| Need | Reuse |
|---|---|
| request, retries, JSON parse, PARAMS | `run.py` (`request`, `parse`, `RETRYABLE`, `PARAMS`, `zero_shot_messages`) |
| label validation, reasoning unpacking | `common.unpack_prediction`, `common.validate_prediction` |
| per-item loss, bootstrap | `paired_bootstrap.per_sample`, `paired_bootstrap.bootstrap` |
| confusion pairs | `triage.confusion_pairs` |
| BM25 neighbours, quote check, truncation | `analyst.build_pool`, `analyst.neighbours`, `analyst.quote_in_text`, `analyst.dossier` |
| output-format anchors | `assemble_instruction.ANCHORS` |

If a helper is private or entangled with argparse, move it into `common.py` rather than
duplicating it (keep behaviour identical; existing runs must still re-score the same).

Suggested internal modules (functions in `evolve.py` are fine for v1):
`Predictor` (cached concurrent prediction), `Ledger` (flip ledger and gate metrics),
`pick_target`, `contrast_batch`, `Proposer` (two calls), `apply_edit` / `validate_edit`,
`quick_gate`, `full_gate`, `State` (load/save, resume).

### 6.1 CLI

```bash
python src/evolve.py init     --task task2b --seed prompts/single/task2b/zero_shot_reason_v1.txt \
                              [--seed <extra seed>] [--param name=value ...]
python src/evolve.py baseline --run-dir <dir>          # seeds on 461 + noise repeat
python src/evolve.py step     --run-dir <dir> [--rounds N]
python src/evolve.py status   --run-dir <dir>          # champion, rounds, tokens, gates
python src/evolve.py export   --run-dir <dir> --version reason-v3
```

Global flags: `--concurrency`, `--limit-per-fold N` (pilot: use only N items per fold),
`--dry-run` (fake predictor/proposer, no API; used by tests).

`export` writes `prompts/single/<task>/zero_shot_<version>.txt` and
`prompts/evolve/<task>/<version>.CHANGELOG.md` (edits in order, with round, gate numbers
and evolve run_id). It refuses to overwrite an existing prompt file (prompt freeze rule).
The exported prompt is then run with the normal `src/run.py` on `train_val` and `dev`, so
those scores come from standard run directories and are recomputed by `src/evaluate.py`.

### 6.2 Run directory

```
results/evolve/<task>/<run_id>/
  config.json            params, seed prompt shas, data / folds / manifest shas, code git sha
  state.json             round, champion id, patience, failed cells, tokens used
  prompts/<cand_id>.txt  every prompt tried (s0, s1 seeds; r03c2 = round 3 candidate 2)
  predictions/<cand_id>.jsonl   labels per item (committed)
  cache/                 raw responses, reasoning, proposer raw output (gitignored)
  rounds/round_03/
    target.json  batch.json  proposer_blind.json  proposer_edit.json
    candidates.json  quick_gate.json  full_gate.json  decision.json
  lineage.md             human-readable log: per round the cell, the edit diff, gate table, decision
```

Add `results/evolve/**/cache/` to `.gitignore`. Prediction cache key:
`(sha256(prompt text), example_id, attempt policy)`; a rerun with the same prompt reuses it.
`step` is resumable at any point: every API result is on disk before it is used.

## 7. Cost estimate (per task, deepseek-flash)

Zero-shot reason ≈ 2.3k input tokens per item (`results/SUMMARY.md` token appendix,
Task 1 107 items ≈ 0.25M).

| Phase | Calls | Input tokens |
|---|---|---|
| baseline: 1 seed × 461 × 2 | ~920 | ~2.1M |
| per round: 2 proposer calls | 2 | ~0.1M |
| per round: quick gate 4 × 40 | 160 | ~0.4M |
| per round: full gate ≤ 2 × ~370 | ≤ 740 | ≤ 1.7M |
| per round: champion on F_k | 92 | ~0.2M |
| 8 rounds | ~8k | ~19M |
| **total** | **~9k** | **~21M** |

## 8. Tests (before any API call)

In `tests/test_evolve.py`, all with `--dry-run` fakes:
- `apply_edit`: anchor missing / duplicated / protected label removed / output tail changed → rejected.
- quote check, copied-text check, id check.
- flip ledger and every gate on hand-made champion/candidate loss vectors (including a
  synthetic "swap" case like the Task 2b Authorization↔Scope one, which G3 must reject).
- data-role assertion: a batch containing an id outside `F_k` raises.
- resume: kill after the quick gate, rerun `step`, no prediction is requested twice.

## 9. Milestones

1. Helpers moved/reused, `evolve.py init/baseline` with cache; `make validate` still passes.
2. Proposer prompts v1 + `step` with `--limit-per-fold 10`, one round on Task 2b, read the
   batch, both proposer outputs and the gate table by hand.
3. Pilot check: are the 4 candidates really different? does anything pass the quick gate?
   Adjust parameters **before** the full run (a new run_id, old pilot kept).
4. Full Task 2b run → export → train_val → dev (eval.md protocol).
5. Task 2a, then Task 1 (Task 1 adds a hand-written structured seed; see eval.md).
