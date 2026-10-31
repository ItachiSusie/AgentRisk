# AgentRisk — one entry point per stage. Run `make` for the list.
PY       := .venv/bin/python
RUN      ?= results/_smoke/zero-shot-v1/20261027-233542
TRIAGE   := $(RUN)/triage/triage.jsonl
WORKLIST := $(RUN)/worklist.jsonl
ANALYSIS := results/analysis/$(notdir $(RUN))
LIMIT    ?=

.PHONY: help validate splits baseline triage worklist analyze cluster merge compare dev-final

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
