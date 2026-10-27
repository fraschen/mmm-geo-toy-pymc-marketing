# Gate report: **PASS_WITH_WARNINGS**

96 pass, 19 warn, 0 fail, 0 skipped. Primary spec: `geo_hierarchical`.

## geo_hierarchical

| status | check | value | threshold | detail |
|---|---|---|---|---|
| PASS | data: required columns present | [] |  |  |
| PASS | data: balanced weekly panel, no missing values | {'balanced_panel': True, 'weekly_contiguous': True, 'n_missing_values': 0} |  |  |
| PASS | data: no negative spend or KPI | 0 |  |  |
| PASS | prior predictive coverage | 1.0 | [0.5, 1.0] |  |
| PASS | R-hat max | 1.005 | 1.01 |  |
| PASS | ESS bulk min | 840 | 400 |  |
| PASS | ESS tail min | 1273 | 400 |  |
| PASS | divergences | 0 | 0 |  |
| PASS | E-BFMI min | 0.792 | 0.3 |  |
| PASS | in-sample R2 | 0.7239 | 0.6 |  |
| WARN | within-geo R2 (signal strength) | 0.1402 | 0.2 | share of week-to-week variance within a geo the model explains; low = weak media signal |
| PASS | 94% PPC interval coverage | 0.946 | [0.85, 0.99] |  |
| PASS | residual lag-1 autocorrelation (median |acf1| across geos) | 0.045 | 0.3 |  |
| PASS | PSIS-LOO Pareto k > 0.7 share | 0.0 | 0.01 |  |
| PASS | ROI identified by data, not prior: Channel0 | 0.896 | 0.3 | 1 - posterior sd / prior sd of ROI |
| WARN | ROI clearly above or below break-even: Channel0 | 0.47 | [0.1, 0.9] | P(ROI > 1); in between = cannot say whether the channel pays back |
| PASS | ROI identified by data, not prior: Channel1 | 0.909 | 0.3 | 1 - posterior sd / prior sd of ROI |
| WARN | ROI clearly above or below break-even: Channel1 | 0.195 | [0.1, 0.9] | P(ROI > 1); in between = cannot say whether the channel pays back |
| PASS | ROI identified by data, not prior: Channel2 | 0.654 | 0.3 | 1 - posterior sd / prior sd of ROI |
| PASS | ROI clearly above or below break-even: Channel2 | 0.976 | [0.1, 0.9] | P(ROI > 1); in between = cannot say whether the channel pays back |
| PASS | ROI identified by data, not prior: Channel3 | 0.969 | 0.3 | 1 - posterior sd / prior sd of ROI |
| WARN | ROI clearly above or below break-even: Channel3 | 0.513 | [0.1, 0.9] | P(ROI > 1); in between = cannot say whether the channel pays back |
| PASS | ROI identified by data, not prior: Channel4 | 0.978 | 0.3 | 1 - posterior sd / prior sd of ROI |
| PASS | ROI clearly above or below break-even: Channel4 | 0.042 | [0.1, 0.9] | P(ROI > 1); in between = cannot say whether the channel pays back |

## pooled

| status | check | value | threshold | detail |
|---|---|---|---|---|
| PASS | data: required columns present | [] |  |  |
| PASS | data: balanced weekly panel, no missing values | {'balanced_panel': True, 'weekly_contiguous': True, 'n_missing_values': 0} |  |  |
| PASS | data: no negative spend or KPI | 0 |  |  |
| PASS | prior predictive coverage | 1.0 | [0.5, 1.0] |  |
| PASS | R-hat max | 1.0058 | 1.01 |  |
| WARN | ESS bulk min | 297 | 400 |  |
| WARN | ESS tail min | 346 | 400 |  |
| PASS | divergences | 0 | 0 |  |
| PASS | E-BFMI min | 0.951 | 0.3 |  |
| WARN | converged: results withheld | False |  | ESS bulk min 297 < 400; ESS tail min 346 < 400 |

## prior_sensitivity

| status | check | value | threshold | detail |
|---|---|---|---|---|
| PASS | data: required columns present | [] |  |  |
| PASS | data: balanced weekly panel, no missing values | {'balanced_panel': True, 'weekly_contiguous': True, 'n_missing_values': 0} |  |  |
| PASS | data: no negative spend or KPI | 0 |  |  |
| PASS | prior predictive coverage | 1.0 | [0.5, 1.0] |  |
| PASS | R-hat max | 1.0071 | 1.01 |  |
| PASS | ESS bulk min | 454 | 400 |  |
| PASS | ESS tail min | 563 | 400 |  |
| PASS | divergences | 0 | 0 |  |
| PASS | E-BFMI min | 0.986 | 0.3 |  |
| PASS | in-sample R2 | 0.6994 | 0.6 |  |
| WARN | within-geo R2 (signal strength) | 0.0642 | 0.2 | share of week-to-week variance within a geo the model explains; low = weak media signal |
| PASS | 94% PPC interval coverage | 0.943 | [0.85, 0.99] |  |
| PASS | residual lag-1 autocorrelation (median |acf1| across geos) | 0.057 | 0.3 |  |
| PASS | PSIS-LOO Pareto k > 0.7 share | 0.0 | 0.01 |  |
| PASS | ROI identified by data, not prior: Channel0 | 0.724 | 0.3 | 1 - posterior sd / prior sd of ROI |
| WARN | ROI clearly above or below break-even: Channel0 | 0.844 | [0.1, 0.9] | P(ROI > 1); in between = cannot say whether the channel pays back |
| PASS | ROI identified by data, not prior: Channel1 | 0.819 | 0.3 | 1 - posterior sd / prior sd of ROI |
| WARN | ROI clearly above or below break-even: Channel1 | 0.194 | [0.1, 0.9] | P(ROI > 1); in between = cannot say whether the channel pays back |
| PASS | ROI identified by data, not prior: Channel2 | 0.842 | 0.3 | 1 - posterior sd / prior sd of ROI |
| WARN | ROI clearly above or below break-even: Channel2 | 0.155 | [0.1, 0.9] | P(ROI > 1); in between = cannot say whether the channel pays back |
| PASS | ROI identified by data, not prior: Channel3 | 0.871 | 0.3 | 1 - posterior sd / prior sd of ROI |
| PASS | ROI clearly above or below break-even: Channel3 | 0.003 | [0.1, 0.9] | P(ROI > 1); in between = cannot say whether the channel pays back |
| PASS | ROI identified by data, not prior: Channel4 | 0.83 | 0.3 | 1 - posterior sd / prior sd of ROI |
| PASS | ROI clearly above or below break-even: Channel4 | 0.083 | [0.1, 0.9] | P(ROI > 1); in between = cannot say whether the channel pays back |

## hierarchical_prior_sensitivity

| status | check | value | threshold | detail |
|---|---|---|---|---|
| PASS | data: required columns present | [] |  |  |
| PASS | data: balanced weekly panel, no missing values | {'balanced_panel': True, 'weekly_contiguous': True, 'n_missing_values': 0} |  |  |
| PASS | data: no negative spend or KPI | 0 |  |  |
| PASS | prior predictive coverage | 1.0 | [0.5, 1.0] |  |
| PASS | R-hat max | 1.0054 | 1.01 |  |
| PASS | ESS bulk min | 1241 | 400 |  |
| PASS | ESS tail min | 1270 | 400 |  |
| PASS | divergences | 0 | 0 |  |
| PASS | E-BFMI min | 0.739 | 0.3 |  |
| PASS | in-sample R2 | 0.7233 | 0.6 |  |
| WARN | within-geo R2 (signal strength) | 0.1386 | 0.2 | share of week-to-week variance within a geo the model explains; low = weak media signal |
| PASS | 94% PPC interval coverage | 0.947 | [0.85, 0.99] |  |
| PASS | residual lag-1 autocorrelation (median |acf1| across geos) | 0.048 | 0.3 |  |
| PASS | PSIS-LOO Pareto k > 0.7 share | 0.0 | 0.01 |  |
| PASS | ROI identified by data, not prior: Channel0 | 0.892 | 0.3 | 1 - posterior sd / prior sd of ROI |
| WARN | ROI clearly above or below break-even: Channel0 | 0.654 | [0.1, 0.9] | P(ROI > 1); in between = cannot say whether the channel pays back |
| PASS | ROI identified by data, not prior: Channel1 | 0.912 | 0.3 | 1 - posterior sd / prior sd of ROI |
| WARN | ROI clearly above or below break-even: Channel1 | 0.218 | [0.1, 0.9] | P(ROI > 1); in between = cannot say whether the channel pays back |
| PASS | ROI identified by data, not prior: Channel2 | 0.906 | 0.3 | 1 - posterior sd / prior sd of ROI |
| PASS | ROI clearly above or below break-even: Channel2 | 0.981 | [0.1, 0.9] | P(ROI > 1); in between = cannot say whether the channel pays back |
| PASS | ROI identified by data, not prior: Channel3 | 0.925 | 0.3 | 1 - posterior sd / prior sd of ROI |
| WARN | ROI clearly above or below break-even: Channel3 | 0.521 | [0.1, 0.9] | P(ROI > 1); in between = cannot say whether the channel pays back |
| PASS | ROI identified by data, not prior: Channel4 | 0.952 | 0.3 | 1 - posterior sd / prior sd of ROI |
| PASS | ROI clearly above or below break-even: Channel4 | 0.022 | [0.1, 0.9] | P(ROI > 1); in between = cannot say whether the channel pays back |

## geo_hierarchical (time holdout)

| status | check | value | threshold | detail |
|---|---|---|---|---|
| PASS | holdout geo-week MAPE vs in-sample (no degradation) | 1.062 | 1.25 | holdout 0.310 vs in-sample 0.292 |
| PASS | holdout national weekly MAPE | 0.0417 | 0.1 |  |
| PASS | holdout 94% interval coverage | 0.917 | 0.8 |  |
| PASS | holdout fit converged (R-hat) | 1.0065 | 1.01 |  |

## geo_hierarchical (rolling-origin CV)

| status | check | value | threshold | detail |
|---|---|---|---|---|
| PASS | train 1-104: geo-week MAPE vs in-sample (no degradation) | 1.011 | 1.25 | holdout 0.296 vs in-sample 0.293 |
| PASS | train 1-104: national weekly MAPE | 0.0529 | 0.1 |  |
| PASS | train 1-104: 94% interval coverage | 0.944 | 0.8 |  |
| PASS | train 1-104: fit converged (R-hat) | 1.0074 | 1.01 |  |
| PASS | train 1-117: geo-week MAPE vs in-sample (no degradation) | 1.034 | 1.25 | holdout 0.301 vs in-sample 0.291 |
| PASS | train 1-117: national weekly MAPE | 0.0367 | 0.1 |  |
| PASS | train 1-117: 94% interval coverage | 0.94 | 0.8 |  |
| PASS | train 1-117: fit converged (R-hat) | 1.0077 | 1.01 |  |
| PASS | train 1-130: geo-week MAPE vs in-sample (no degradation) | 1.099 | 1.25 | holdout 0.320 vs in-sample 0.291 |
| PASS | train 1-130: national weekly MAPE | 0.0346 | 0.1 |  |
| PASS | train 1-130: 94% interval coverage | 0.931 | 0.8 |  |
| PASS | train 1-130: fit converged (R-hat) | 1.0046 | 1.01 |  |
| PASS | ROI stable across CV folds: Channel0 | 1.52 | [2.0, 5.0] | full=0.95, cv104=1.16, cv117=0.80, cv130=0.84, cv143=0.76 |
| PASS | ROI stable across CV folds: Channel1 | 1.26 | [2.0, 5.0] | full=0.64, cv104=0.56, cv117=0.58, cv130=0.70, cv143=0.70 |
| PASS | ROI stable across CV folds: Channel2 | 1.5 | [2.0, 5.0] | full=1.81, cv104=1.38, cv117=1.54, cv130=1.48, cv143=2.07 |
| PASS | ROI stable across CV folds: Channel3 | 1.1 | [2.0, 5.0] | full=1.00, cv104=1.08, cv117=1.06, cv130=1.10, cv143=1.05 |
| PASS | ROI stable across CV folds: Channel4 | 1.15 | [2.0, 5.0] | full=0.75, cv104=0.76, cv117=0.82, cv130=0.76, cv143=0.71 |

## cross-specification agreement

| status | check | value | threshold | detail |
|---|---|---|---|---|
| PASS | prior_sensitivity: ROI agrees with primary: Channel0 | 1.81 | [2.0, 5.0] | geo_hierarchical=0.95, prior_sensitivity=1.73; primary ELPD +177 |
| PASS | prior_sensitivity: ROI agrees with primary: Channel1 | 1.02 | [2.0, 5.0] | geo_hierarchical=0.64, prior_sensitivity=0.62; primary ELPD +177 |
| WARN | prior_sensitivity: ROI agrees with primary: Channel2 | 3.57 | [2.0, 5.0] | geo_hierarchical=1.81, prior_sensitivity=0.51; primary ELPD +177 |
| WARN | prior_sensitivity: ROI agrees with primary: Channel3 | 4.78 | [2.0, 5.0] | geo_hierarchical=1.00, prior_sensitivity=0.21; primary ELPD +177 |
| WARN | prior_sensitivity: ROI agrees with primary: Channel4 | 2.53 | [2.0, 5.0] | geo_hierarchical=0.75, prior_sensitivity=0.30; primary ELPD +177 |
| WARN | prior_sensitivity: ROI ranking agrees with primary | -0.3 | 0.6 |  |
| PASS | hierarchical_prior_sensitivity: ROI agrees with primary: Channel0 | 1.24 | [2.0, 5.0] | geo_hierarchical=0.95, hierarchical_prior_sensitivity=1.18; primary ELPD +1 |
| PASS | hierarchical_prior_sensitivity: ROI agrees with primary: Channel1 | 1.12 | [2.0, 5.0] | geo_hierarchical=0.64, hierarchical_prior_sensitivity=0.72; primary ELPD +1 |
| PASS | hierarchical_prior_sensitivity: ROI agrees with primary: Channel2 | 1.0 | [2.0, 5.0] | geo_hierarchical=1.81, hierarchical_prior_sensitivity=1.82; primary ELPD +1 |
| PASS | hierarchical_prior_sensitivity: ROI agrees with primary: Channel3 | 1.01 | [2.0, 5.0] | geo_hierarchical=1.00, hierarchical_prior_sensitivity=1.01; primary ELPD +1 |
| PASS | hierarchical_prior_sensitivity: ROI agrees with primary: Channel4 | 1.01 | [2.0, 5.0] | geo_hierarchical=0.75, hierarchical_prior_sensitivity=0.75; primary ELPD +1 |
| PASS | hierarchical_prior_sensitivity: ROI ranking agrees with primary | 0.9 | 0.6 |  |
