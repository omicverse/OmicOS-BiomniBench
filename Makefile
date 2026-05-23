SHELL := /bin/bash
PYTHON ?= python

.PHONY: help fetch run compare cost radar smoke clean-traj

help:
	@echo "OmicOS-BiomniBench targets"
	@echo "  fetch                              - pull BiomniBench-DA task fixtures from HF"
	@echo "  run PROV=<provider> MOD=<id> LBL=<label>"
	@echo "                                     - full 50-task sweep under one model"
	@echo "  compare LABELS='<a> <b> ...'       - aggregate / compare finished runs"
	@echo "  cost LABELS='<a> <b> ...'          - naive + cache-adjusted cost per task"
	@echo "  radar                              - regenerate analysis/omicos_radar.png"
	@echo "  smoke                              - 1-task sanity check (default agent)"
	@echo "  clean-traj LBL=<label>             - remove runs/<label>/ (results stay)"

fetch:
	uv run omicos-biomnibench fetch

run:
	@if [ -z "$(PROV)" ] || [ -z "$(MOD)" ] || [ -z "$(LBL)" ]; then \
	  echo "usage: make run PROV=<provider> MOD=<model-id> LBL=<label>"; exit 1; fi
	bash scripts/bench_model.sh $(PROV) $(MOD) $(LBL)

compare:
	@if [ -z "$(LABELS)" ]; then echo "usage: make compare LABELS='label1 label2 ...'"; exit 1; fi
	$(PYTHON) scripts/bench_compare.py $(LABELS)

cost:
	@if [ -z "$(LABELS)" ]; then echo "usage: make cost LABELS='label1 label2 ...'"; exit 1; fi
	$(PYTHON) scripts/bench_cost.py $(LABELS)

radar:
	$(PYTHON) scripts/bench_radar.py

smoke:
	uv run omicos-biomnibench smoke

clean-traj:
	@if [ -z "$(LBL)" ]; then echo "usage: make clean-traj LBL=<label>"; exit 1; fi
	rm -rf runs/$(LBL)
