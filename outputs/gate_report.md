# Gate report: **PASS_WITH_WARNINGS**

41 pass, 4 warn, 0 fail. Primary spec: `hier_media`.

## hier_media

| status | check | value | threshold | detail |
|---|---|---|---|---|
| PASS | data: required columns present | [] |  |  |
| PASS | data: balanced weekly panel, no missing values | {'balanced_panel': True, 'weekly_contiguous': True, 'n_missing_values': 0} |  |  |
| PASS | data: no negative spend or KPI | 0 |  |  |
| PASS | prior predictive coverage | 1.0 | [0.5, 1.0] |  |
| PASS | R-hat max | 1.0054 | 1.01 |  |
| PASS | ESS bulk min | 532 | 400 |  |
| PASS | ESS tail min | 896 | 400 |  |
| PASS | divergences | 0 | 0 |  |
| PASS | E-BFMI min | 0.846 | 0.3 |  |
| PASS | in-sample R2 | 0.7291 | 0.6 |  |
| WARN | within-geo R2 (signal strength) | 0.1564 | 0.2 | share of week-to-week variance within a geo the model explains; low = weak media signal |
| PASS | 94% PPC interval coverage | 0.948 | [0.85, 0.99] |  |
| PASS | residual lag-1 autocorrelation (median |acf1| across geos) | 0.06 | 0.3 |  |
| PASS | PSIS-LOO Pareto k > 0.7 share | 0.0 | 0.01 |  |
| PASS | ROI identified by data, not prior: Channel0 | 0.928 | 0.3 | 1 - posterior sd / prior sd of ROI |
| WARN | ROI clearly above or below break-even: Channel0 | 0.247 | [0.1, 0.9] | P(ROI > 1); in between = cannot say whether the channel pays back |
| PASS | ROI identified by data, not prior: Channel1 | 0.93 | 0.3 | 1 - posterior sd / prior sd of ROI |
| WARN | ROI clearly above or below break-even: Channel1 | 0.143 | [0.1, 0.9] | P(ROI > 1); in between = cannot say whether the channel pays back |
| PASS | ROI identified by data, not prior: Channel2 | 0.702 | 0.3 | 1 - posterior sd / prior sd of ROI |
| PASS | ROI clearly above or below break-even: Channel2 | 1.0 | [0.1, 0.9] | P(ROI > 1); in between = cannot say whether the channel pays back |
| PASS | ROI identified by data, not prior: Channel3 | 0.928 | 0.3 | 1 - posterior sd / prior sd of ROI |
| PASS | ROI clearly above or below break-even: Channel3 | 0.993 | [0.1, 0.9] | P(ROI > 1); in between = cannot say whether the channel pays back |
| PASS | ROI identified by data, not prior: Channel4 | 0.96 | 0.3 | 1 - posterior sd / prior sd of ROI |
| WARN | ROI clearly above or below break-even: Channel4 | 0.711 | [0.1, 0.9] | P(ROI > 1); in between = cannot say whether the channel pays back |

## hier_media (time holdout)

| status | check | value | threshold | detail |
|---|---|---|---|---|
| PASS | holdout geo-week MAPE vs in-sample (no degradation) | 1.054 | 1.25 | holdout 0.309 vs in-sample 0.293 |
| PASS | holdout national weekly MAPE | 0.0455 | 0.1 |  |
| PASS | holdout 94% interval coverage | 0.91 | 0.8 |  |
| PASS | holdout fit converged (R-hat) | 1.0048 | 1.01 |  |

## hier_media (rolling-origin CV)

| status | check | value | threshold | detail |
|---|---|---|---|---|
| PASS | train 1-104: geo-week MAPE vs in-sample (no degradation) | 1.069 | 1.25 | holdout 0.314 vs in-sample 0.293 |
| PASS | train 1-104: national weekly MAPE | 0.0699 | 0.1 |  |
| PASS | train 1-104: 94% interval coverage | 0.938 | 0.8 |  |
| PASS | train 1-104: fit converged (R-hat) | 1.0051 | 1.01 |  |
| PASS | train 1-117: geo-week MAPE vs in-sample (no degradation) | 1.029 | 1.25 | holdout 0.301 vs in-sample 0.293 |
| PASS | train 1-117: national weekly MAPE | 0.0403 | 0.1 |  |
| PASS | train 1-117: 94% interval coverage | 0.94 | 0.8 |  |
| PASS | train 1-117: fit converged (R-hat) | 1.0047 | 1.01 |  |
| PASS | train 1-130: geo-week MAPE vs in-sample (no degradation) | 1.112 | 1.25 | holdout 0.325 vs in-sample 0.292 |
| PASS | train 1-130: national weekly MAPE | 0.0353 | 0.1 |  |
| PASS | train 1-130: 94% interval coverage | 0.952 | 0.8 |  |
| PASS | train 1-130: fit converged (R-hat) | 1.0065 | 1.01 |  |
| PASS | ROI stable across CV folds: Channel0 | 1.59 | [2.0, 5.0] | full=0.79, cv104=0.51, cv117=0.67, cv130=0.76, cv143=0.82 |
| PASS | ROI stable across CV folds: Channel1 | 1.18 | [2.0, 5.0] | full=0.69, cv104=0.61, cv117=0.72, cv130=0.69, cv143=0.70 |
| PASS | ROI stable across CV folds: Channel2 | 1.3 | [2.0, 5.0] | full=2.12, cv104=1.84, cv117=1.82, cv130=1.97, cv143=2.37 |
| PASS | ROI stable across CV folds: Channel3 | 1.05 | [2.0, 5.0] | full=1.67, cv104=1.67, cv117=1.65, cv130=1.74, cv143=1.65 |
| PASS | ROI stable across CV folds: Channel4 | 1.12 | [2.0, 5.0] | full=1.10, cv104=1.20, cv117=1.22, cv130=1.09, cv143=1.08 |
