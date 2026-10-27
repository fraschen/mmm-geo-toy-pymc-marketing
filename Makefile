# On macOS, keep the machine from sleeping while a fit runs (no-op elsewhere)
KEEPAWAKE := $(shell command -v caffeinate >/dev/null 2>&1 && echo caffeinate -i -s)
PY := PYTHONPATH=src $(KEEPAWAKE) .venv/bin/python -u -W ignore
SPECS := pooled_media hier_media hier_media_controls
PRIMARY = $(shell .venv/bin/python -c "import yaml;print(yaml.safe_load(open('config/pipeline.yaml'))['primary_spec'])")

.PHONY: all setup data eda fit holdout cv fit-all select calibrate gates results reports docker clean

all: setup eda fit-all select holdout cv calibrate gates results reports

setup: data     ## create .venv from requirements.lock (no-op if it already exists, e.g. inside Docker)
	@[ -x .venv/bin/python ] || (uv venv --python 3.12 .venv && uv pip install --python .venv/bin/python -r requirements.lock)

data:
	./scripts/fetch_data.sh

eda:            ## exploratory analysis -> outputs/eda/
	$(PY) -m mmm.eda

fit:            ## make fit SPEC=pooled
	$(PY) -m mmm.run_spec --spec $(SPEC) 2>&1 | tee outputs/logs/$(SPEC).log

holdout:
	$(PY) -m mmm.run_spec --spec $(PRIMARY) --holdout 2>&1 | tee outputs/logs/$(PRIMARY)__holdout.log

cv:             ## rolling-origin folds for the primary spec (cutoffs in config: data.cv_train_weeks)
	@for n in 104 117 130; do $(PY) -m mmm.run_spec --spec $(PRIMARY) --train-weeks $$n 2>&1 | tee outputs/logs/$(PRIMARY)__cv$$n.log; done

fit-all:
	@for s in $(SPECS); do $(MAKE) fit SPEC=$$s; done

select:         ## compare candidates by PSIS-LOO -> outputs/model_selection.{json,md}
	$(PY) -m mmm.select

calibrate:      ## refit the selected spec with the (hypothetical) lift test
	$(PY) -m mmm.lift_test
	$(PY) -m mmm.run_spec --spec hier_media_lift 2>&1 | tee outputs/logs/hier_media_lift.log

gates:          ## exits 1 if any blocking check fails
	$(PY) -m mmm.gates

results:
	$(PY) -m mmm.results

reports:        ## model health + measurement reports -> reports/ (after gates and results)
	$(PY) -m mmm.report_diagnostics
	$(PY) -m mmm.report_measurement

docker:         ## build the image and run the full pipeline; outputs/ and reports/ are written to the working copy
	docker build -t mmm-geo .
	docker run --rm -v "$(CURDIR)/outputs:/app/outputs" -v "$(CURDIR)/reports:/app/reports" mmm-geo

clean:
	rm -rf outputs/specs artifacts
