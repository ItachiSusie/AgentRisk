# AgentRisk — one entry point per stage. Run `make` for the list.
PY       := .venv/bin/python
RUN      ?= results/_smoke/multitask/zero-shot-v1/20261027-233542
TRIAGE   := $(RUN)/triage/triage.jsonl
WORKLIST := $(RUN)/worklist.jsonl
ANALYSIS := results/analysis/multitask/$(notdir $(RUN))
LIMIT    ?=

.PHONY: audit repair merge-boundary regress help validate splits baseline triage worklist analyze cluster merge compare dev-final \
	single-prompts single-dev single-compare summary

help:
	@echo 'make validate   offline: compile src, check split drift, dry-run dev + train_val'
	@echo 'make splits     rebuild data/splits from metadata/split_manifest.jsonl'
	@echo 'make baseline   run zero-shot v1 on train_evolve (LIMIT=5 for a probe)'
	@echo 'make triage     error triage for RUN (default: the current train_evolve run)'
	@echo 'make worklist   failures of RUN -> worklist.jsonl'
	@echo 'make analyze    explain+patch each failure (LIMIT=5 first!)'
	@echo 'make cluster    group lessons by theme, show support counts'
	@echo 'make merge      consolidate themes into prompts/patches/v2/'
	@echo 'make compare    regenerate results/comparison.md AND comparison.html'
	@echo 'make dev-final  run the frozen dev test ONCE (not for tuning)'
	@echo ''
	@echo 'single-task (TASK=task1|task2a|task2b, docs/single-task/):'
	@echo 'make single-prompts  generate that task'"'"'s answer-v1 / reason-v1 prompts from zero_shot_v1.txt'
	@echo 'make single-dev      run its 14 dev cells (zero-shot + bm25/random k=3/5/10, both lineages)'
	@echo 'make single-compare  regenerate results/comparison-<task>.md'
	@echo 'make summary         regenerate results/SUMMARY.md (the three main tables)'
	@echo ''
	@echo 'agentic round (docs/agentic-distill/):'
	@echo 'make audit   blind audit + classification of AUDIT_RUN failures (PAIRS=3:4, LIMIT=20)'
	@echo 'make repair  patch + regression loop over the audit (train_evolve only)'
	@echo 'make merge-boundary INSTRUCTION=... OUT_DIR=...   merge kept repairs by boundary'
	@echo 'make regress BASE=<run> NEW=<run>   per-class accuracy change between two runs'

validate:
	$(PY) -m compileall -q src
	$(PY) src/make_splits.py --check
	$(PY) src/run.py --strategy zero-shot --version v1 --dry-run | head -1
	$(PY) src/run.py --strategy few-shot --selection bm25 --k 10 --version v1 --split train_val \
		--data-file data/splits/train_val.jsonl --dry-run | head -1

splits:
	$(PY) src/fetch_split_manifest.py
	$(PY) src/make_splits.py --target-val 100

baseline:
	$(PY) src/run.py --strategy zero-shot --version v1 --split train_evolve \
		--data-file data/splits/train_evolve.jsonl $(if $(LIMIT),--limit $(LIMIT),)

triage:
	$(PY) src/triage.py $(RUN)

worklist:
	$(PY) src/analyst.py worklist $(TRIAGE)

analyze:
	$(PY) src/analyst.py run --triage $(TRIAGE) --worklist $(WORKLIST) \
		$(if $(LIMIT),--limit $(LIMIT),)

cluster:
	$(PY) src/merge_lessons.py cluster --lessons $(ANALYSIS)/lessons.jsonl

merge:
	$(PY) src/merge_lessons.py merge --lessons $(ANALYSIS)/lessons.jsonl --out-dir prompts/patches/v2

compare:
	$(PY) src/compare.py
	$(PY) src/compare_html.py

dev-final:
	@echo 'WARNING: dev is the frozen final test — run it once, then never tune on it.'
	$(PY) src/run.py --strategy zero-shot --version v2 $(if $(LIMIT),--limit $(LIMIT),)

# ---- single-task (docs/single-task/) -------------------------------------------------
TASK ?= task1
CONC ?= 8

single-prompts:
	$(PY) src/make_single_prompts.py --task $(TASK)
	$(PY) src/make_single_prompts.py --task $(TASK) --check

single-dev:
	@test -n "$$DEEPSEEK_API_KEY" || { echo 'load the key first: set -a; . ./.env; set +a'; exit 1; }
	for V in answer-v1 reason-v1; do \
	  $(PY) src/run.py --task $(TASK) --version $$V --strategy zero-shot --concurrency $(CONC); \
	  for K in 3 5 10; do \
	    $(PY) src/run.py --task $(TASK) --version $$V --strategy few-shot --selection bm25 --k $$K --concurrency $(CONC); \
	    $(PY) src/run.py --task $(TASK) --version $$V --strategy few-shot --selection random --seed 0 --k $$K --concurrency $(CONC); \
	  done; \
	done
	for d in results/deepseek-flash/$(TASK)/*/*/; do $(PY) src/evaluate.py $$d > /dev/null; done
	$(MAKE) single-compare

single-compare:
	$(PY) src/compare.py --task $(TASK)

summary:
	$(PY) src/make_summary.py

# ---- agentic distillation, round three (docs/agentic-distill/) -----------------------
AUDIT_RUN ?= results/_smoke/task1/zero-shot-reason-v1/20261104-082558
PAIRS     ?= 3:4
AUDIT_DIR := results/analysis/$(TASK)/$(notdir $(AUDIT_RUN))-audit-v3

audit:
	$(PY) src/agentic.py audit --triage $(AUDIT_RUN)/triage/triage.jsonl \
		$(if $(PAIRS),--pairs $(PAIRS),) $(if $(LIMIT),--limit $(LIMIT),) --spot-check 10 --concurrency $(CONC)

repair:
	$(PY) src/agentic.py repair --audit $(AUDIT_DIR)/audit.jsonl $(if $(LIMIT),--limit $(LIMIT),)

merge-boundary:
	$(PY) src/merge_lessons.py merge --boundary --lessons $(AUDIT_DIR)/repair.jsonl \
		--instruction $(INSTRUCTION) --out-dir $(OUT_DIR)

regress:
	$(PY) src/regress.py compare $(BASE) $(NEW)
