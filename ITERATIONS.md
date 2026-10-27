# Modeling iterations

A chronological record of every model run: settings, results, and the modeling decisions that followed. Newest
entries are at the bottom.

Conventions: ESS and R-hat are taken over all posterior variables, including deterministics. ROI is the posterior
median, as incremental revenue per unit of spend. A fit that fails its convergence checks stops without results:
only its convergence diagnostics are recorded.

---

## 0. EDA and candidate specifications (no model fitted yet)

The candidates were designed from the EDA alone (see the README's EDA section and `outputs/eda/`). Choices shared
by all candidates:
- **Population scaling of channels and target** (`FixedScaling` with geo population). Revenue and spend are
  proportional to population (r = 0.97 and 0.997); population is fixed, unlike a noisy per-geo maximum.
- **No yearly seasonality.** It is not detectable above chance (36% of variance vs 33% expected from noise).
- **Linear trend control kept.** +4.4% over 3 years, p = 0.01.
- **Adstock `l_max` 4.** There is no lagged spend–revenue signal beyond 1–2 weeks.
- **Controls kept as confounders.** They correlate 0.41–0.55 with spend.

Candidate C is motivated by a data test: per-geo regressions of relative revenue on the controls show the
competitor and sentiment effects vary across geos far more than noise explains (I² 0.94 and 0.88, p < 0.001).
Promo, organic and trend show no significant heterogeneity.

| Candidate | Media effect size | Control effects |
|---|---|---|
| A. `pooled_media` | shared by all geos | shared by all geos |
| B. `hier_media` | partially pooled across geos | shared by all geos |
| C. `hier_media_controls` | partially pooled across geos | partially pooled across geos |

The selection protocol was fixed before fitting (README): a candidate that fails convergence is dropped (no
reruns with more draws, user decision); select by PSIS-LOO with a preference for the simpler candidate within
2 SE; then holdout, CV and the gates.

**Status:** awaiting approval to fit.

## 1. Candidates fitted: 4 × 1000 draws, tune 1000, `target_accept` 0.95

| Candidate | Status | R-hat max | ESS bulk / tail | Divergences | Where it failed |
|---|---|---|---|---|---|
| A. `pooled_media` | not converged | 1.0117 | 270 / 447 | 0 | total media contribution and geo intercepts |
| B. `hier_media` | **converged** | 1.0054 | 532 / 896 | 0 | n/a |
| C. `hier_media_controls` | not converged | 1.0234 | 224 / 431 | 4 | control-effect hierarchy (`gamma_control_mu`, `_sigma`, `_offset`) |

Prior predictive coverage was 100% for all three.

**Selection (`make select`):** B is the only converged candidate, so it is selected by default. It was not
compared on ELPD against anything. B: ELPD-LOO 4070.7 (SE 55.1), within-geo R² 0.156, MAPE 0.296, 94% interval
coverage 0.948, no observations with Pareto k > 0.7.

**Sampler diagnosis of the dropped candidates (diagnostics only, no results):**
- **A** mixes slowly along total media against the 40 geo intercepts. With one effect size per channel for all
  geos, more media requires every intercept to move down together.
- **C** fails inside the control hierarchy. The EDA found strong cross-geo heterogeneity for competitor and
  sentiment but none for promo, organic and trend. One non-centered hierarchy across controls in such different
  regimes is a known source of poor geometry (non-centering helps weakly identified groups and hurts strongly
  identified ones).

**Caveat carried forward:** C was the candidate motivated by a data test. The selected model shares control
effects across geos even though the competitor and sentiment effects vary by geo (I² 0.94, 0.88). The
validation stage should check whether that shows up in residuals, and the README must state it as a limitation.

**What could be done, and was not (protocol: no reruns):** geo-varying effects for competitor and sentiment only,
with the other controls shared (README, "Next steps"). A with more draws.

## 2. `hier_media` validation: holdout and rolling-origin CV

Four folds, each training on weeks 1..N and forecasting the next 13 (N = 104, 117, 130, 143). Same sampler.

| Fold | Status | R-hat max | ESS bulk min | Geo-week MAPE in → out | National weekly MAPE | Geo-week 94% coverage |
|---|---|---|---|---|---|---|
| 1–104 | converged | 1.0051 | 1297 | 0.293 → 0.314 | 7.0% | 94% |
| 1–117 | converged | 1.0047 | 641 | 0.293 → 0.301 | 4.0% | 94% |
| 1–130 | converged | 1.0065 | 929 | 0.292 → 0.325 | 3.5% | 95% |
| 1–143 | converged | 1.0048 | 972 | 0.293 → 0.309 | 4.6% | 91% |

| Median ROI | 1–104 | 1–117 | 1–130 | 1–143 | full | max ÷ min |
|---|---|---|---|---|---|---|
| Channel0 | 0.51 | 0.67 | 0.76 | 0.82 | 0.79 | 1.59 |
| Channel1 | 0.61 | 0.72 | 0.69 | 0.70 | 0.69 | 1.18 |
| Channel2 | 1.84 | 1.82 | 1.97 | 2.37 | 2.12 | 1.30 |
| Channel3 | 1.67 | 1.65 | 1.74 | 1.65 | 1.67 | 1.05 |
| Channel4 | 1.20 | 1.22 | 1.09 | 1.08 | 1.10 | 1.12 |

**Gate verdict: PASS_WITH_WARNINGS** (41 pass, 4 warn, 0 fail). Warnings: within-geo R² 0.156 (weak weekly
signal); Channel0, Channel1 and Channel4 undetermined around break-even.

**Findings from the reports (`reports/`):**
- National 94% intervals cover 91% of weeks in-sample but 69–92% out-of-sample. Residuals are not correlated
  across geos (+0.01); the shortfall comes from level errors in some forecast windows (bias +6.5% in the first
  fold). National uncertainty is understated.
- The prior predictive is far wider than the data (it allows negative revenue): priors are permissive.
- Channel2's posterior ROI (1.42–2.85) extends past its prior's 94% range (0.02–2.59): the spend-share prior may be
  shrinking small channels.
- Baseline and total media correlate at −0.93 in the posterior.

**Budget scenario (last 52 weeks, budget-neutral):** ±20% per channel moves spend from Channel0, Channel1 and
Channel4 (0.81×, 0.81×, 0.89×) to Channel2 and Channel3 (1.17×, 1.20×): +3.6M revenue (94% HDI +0.8M to +7.1M,
P(gain > 0) = 0.98). ±50%: +7.2M (−0.2M to +16.0M, P = 0.96), extrapolating beyond observed spend.
