# On macOS, keep the machine from sleeping while a fit runs (no-op elsewhere)
KEEPAWAKE := $(shell command -v caffeinate >/dev/null 2>&1 && echo caffeinate -i -s)
PY := PYTHONPATH=src $(KEEPAWAKE) .venv/bin/python -u -W ignore
SPECS := pooled geo_hierarchical prior_sensitivity
PRIMARY := geo_hierarchical

.PHONY: all setup data fit holdout cv fit-all gates results clean

all: setup fit-all holdout cv gates results

setup: data
	uv venv --python 3.12 .venv && uv pip install --python .venv/bin/python -r requirements.lock

data:
	./scripts/fetch_data.sh

fit:            ## make fit SPEC=pooled
	$(PY) -m mmm.run_spec --spec $(SPEC) 2>&1 | tee outputs/logs/$(SPEC).log

holdout:
	$(PY) -m mmm.run_spec --spec $(PRIMARY) --holdout 2>&1 | tee outputs/logs/$(PRIMARY)__holdout.log

cv:             ## rolling-origin folds for the primary spec (cutoffs in config: data.cv_train_weeks)
	@for n in 104 117 130; do $(PY) -m mmm.run_spec --spec $(PRIMARY) --train-weeks $$n 2>&1 | tee outputs/logs/$(PRIMARY)__cv$$n.log; done

fit-all:
	@for s in $(SPECS); do $(MAKE) fit SPEC=$$s; done

gates:          ## exits 1 if any blocking check fails
	$(PY) -m mmm.gates

results:
	$(PY) -m mmm.results

clean:
	rm -rf outputs/specs artifacts
