# Evolve: evaluation protocol

Status: design, to be frozen before the first full run. Date: 2026-11-09.
Companion document: [spec.md](spec.md).

This document answers two questions, in this order:
1. **Does an evolved prompt actually predict better?** (outcome, §2–§3)
2. **Does the algorithm work the way we claim?** — i.e. are gains real rather than lucky
   selection, and did we fix the failure modes of the last round? (process, §4–§5)

A run is a success only if both answers are yes. A dev gain from a process that also admits
noise is not a result we can describe as "the algorithm works".

## 1. Why a written protocol

- dev has already been looked at by ~40 configurations (`results/SUMMARY.md`), so any "best
  dev score" is optimistic. Evolve must be judged by a comparison fixed **before** dev is run.
- The last round looked good on train_val and vanished on dev (Task 2b answer line:
  train_val −0.111 [−0.185, −0.040], dev −0.005 [−0.062, +0.051];
  `docs/single-task/03-task2b-risk-driver.md`, gate I table). The protocol therefore checks
  transfer explicitly instead of trusting one held-out number.
- 143 dev items: differences below ~0.03 are noise (`results/SUMMARY.md`). We must not read
  small differences as results.

## 2. What is compared

For each task, the evolve run produces one **exported prompt** (`reason-v<N>`). It is
compared, with the same model and parameters (`run.py` PARAMS, temperature 0), against:

| Id | Configuration | Role |
|---|---|---|
| B0 | zero-shot `reason-v1` (the seed) | **primary baseline** — success is defined against this |
| B1 | zero-shot `reason-v2` (Trace2Skill rules) | shows whether the over-correction problem is fixed |
| B2 | best few-shot of that task in `results/SUMMARY.md` (Task 1: BM25 k=20 reason; 2a: random k=3 reason; 2b: BM25 k=10 answer) | reference ceiling; not required to beat |
| E | exported evolve prompt, zero-shot | the system under test |
| E+R | E with BM25 few-shot (same k as B2) | do evolved instruction and retrieval add up? (secondary) |

Existing dev runs of B0–B2 are reused (run_ids in `results/SUMMARY.md` appendix); E and E+R
get new runs. On train_val, B0 and B1 runs already exist for every task
(`docs/single-task/01..03`, gate I); B2 and E/E+R are run new.

## 3. Outcome criteria

All differences are paired per item, with `src/paired_bootstrap.py` (3000 iterations,
seed 0). Loss = MAE for Task 1 and 1 − Jaccard for Task 2a/2b, so a negative difference
means E is better. All scores are recomputed with `src/evaluate.py` on the run directories.

### 3.1 Pre-registered primary result

Before running dev, write into `results/evolve/<task>/<run_id>/preregistration.md`:
the exported prompt path and sha256, the comparison (E vs B0), the metric, and the
decision rule below. Commit it, then run dev **once**.

| Verdict | Condition on dev (E − B0) |
|---|---|
| **Success** | 95% CI entirely below 0 |
| **Promising** | point estimate ≤ −0.02, CI crosses 0, and train_val point estimate also ≤ −0.02 |
| **No effect** | point estimate in (−0.02, +0.02) |
| **Harmful** | point estimate ≥ +0.02 |

A "Promising" result is reported as such, not rounded up to success.

### 3.2 Required guards (must hold for Success or Promising)

On **both** train_val and dev, versus B0:
- **No damage:** right→wrong ≤ 5% of B0-correct items. Task 1: gold-1 accuracy drops by at
  most 2 items (B0 reason-v1 currently gets 66/66 gold-1 items right on dev).
- **No label swapping (Task 2):** no label whose FP falls while its FN rises by a similar
  amount (the B1 failure: Authorization FP 30→4, FN 5→31 on dev, answer line).
- **No scale drift (Task 1):** predicted level distribution does not move further from the
  gold distribution (compare count of predicted 4s with gold 4s; B0 over-predicts 4).
- **Validity:** 143/143 and 107/107 valid predictions.

### 3.3 Transfer check

Report three estimates of the same gain (E − B0): OOF (out-of-fold, on train_evolve, from
the evolve run), train_val, dev. Define **transfer ratio** = dev gain / OOF gain.
- ≥ 0.5: gains transfer.
- < 0.5 with OOF significant: the loop is still overfitting its selection data; this is a
  process failure even if dev is "Promising".

### 3.4 Secondary outcomes (reported, not decisive)

- E vs B1, E vs B2, E+R vs B2 and E+R vs E, with CIs.
- Task 1: confusion matrix; the gold-3 → predicted-4 cell (22/32 for answer-v1, 10/32 for
  reason-v1 on dev) and the gold-2 row.
- Task 2: per-label FP/FN table; mean predicted label count vs gold (dev gold 1.20 domains,
  1.39 drivers).
- Exact-match after merging the three single tasks (`src/assemble_single.py`) if all three
  tasks have an exported prompt: compare with 79/143 (`results/SUMMARY.md`).
- Cost: input/output tokens of the evolve run and per-item tokens of E vs B0.

## 4. Process criteria (does the algorithm behave as designed?)

Computed from the evolve run directory; each has a target and a meaning if missed.

| Metric | Target | If missed |
|---|---|---|
| Accepted edits | ≥ 1 over the run | the gates or the proposer are too weak; revisit the pilot |
| Quick-gate pass rate | 10–60% of valid candidates | ~0%: proposer not useful; ~100%: quick gate not filtering |
| Candidate diversity | ≥ 3 of 4 candidates per round differ by > 20 words | switch to separate calls per edit type |
| Edit validity | ≥ 75% of proposed edits pass `validate_edit` | fix the proposer prompt (new version) |
| right→wrong per accepted edit | ≤ 3% (gate) and reported | — |
| Prompt growth | ≤ 150 words over the seed | — |
| Per-fold consistency of the final champion vs seed | gain sign agrees in ≥ 4 of 5 folds | gain concentrated in a few scenario groups |
| Fault mix | report share of misread / missed / wrong_rule / sound_but_wrong per round | if `sound_but_wrong` dominates a cell, treat that cell as label noise and stop targeting it |

## 5. Controls (is the gain caused by the data, or by selection?)

Selecting the best of many candidates on the same items can produce gains from noise alone.
Two controls, run on the same folds with the same parameters:

1. **Noise floor.** Run B0 twice on all 461 train_evolve items (the spec's `baseline`
   step). Report τ (items that change) and the loss difference between the two runs. Any
   accepted edit's net flips must exceed 2·τ (built into gate G1).
2. **Placebo evolve (recommended, one run for the first task only).** Identical run, but the
   gold labels shown to the proposer in call 2 are permuted within the batch (the gates still
   use true labels). If the placebo run accepts edits with OOF gains comparable to the real
   run, the gates are admitting noise and the real run's gains are not evidence for the
   method. Expected cost ≈ one evolve run (~21M input tokens, spec §7).

## 6. Ablations (only after a Success or Promising result)

Run on train_val (cheap, 107 items each) and report; dev only for the final row.

| Id | Change | Question |
|---|---|---|
| A1 | revert each accepted edit alone (leave-one-out) | which edits carry the gain? |
| A2 | only the edits of type `pre_check` / only `definition`+`conditional` | which edit type helps which task? |
| A3 | evolve with failures only (no right items in the batch) | is the contrast batch what prevents damage? |
| A4 | gold shown in call 1 (no blind re-read) | does the blind step matter? |
| A5 | E+R vs E | do retrieval and the evolved instruction combine? |

A3 and A4 need their own evolve runs; schedule them only if budget allows.

## 7. Reporting

For each task, one section in `results/evolve/<task>/<run_id>/REPORT.md`:
run_ids of every run used; the preregistration; outcome table (§3) with CIs on OOF,
train_val and dev; transfer ratio; guards; process metrics (§4); controls (§5); the final
prompt diff against the seed; total tokens. Numbers in the report must be reproducible from
the listed run directories with `src/evaluate.py` and `src/paired_bootstrap.py`.

## 8. Decision after each task

| Outcome | Next step |
|---|---|
| Success, transfer ≥ 0.5, placebo clean | keep the method; run the next task with the same parameters |
| Promising | run the next task unchanged; decide after two tasks |
| No effect, process metrics fine | the prompt has little headroom on this task; prefer retrieval (B2 / E+R) for it |
| Overfitting (transfer < 0.5) or placebo also gains | tighten gates (larger `min_net`, `p_better` 0.95) in a new run before trying another task |
| Harmful | stop; inspect the accepted edits and gates before any further run |

Task order: 2b → 2a → 1 (spec §9). Task 1 additionally gets a hand-written structured seed
(action-type gate → evidence fields → level), evaluated as its own baseline B0' before it
enters evolve, so the effect of the seed and the effect of evolve are reported separately.
