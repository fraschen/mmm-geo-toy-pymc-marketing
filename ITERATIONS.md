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

**What could be done, and was not (protocol: no reruns):** C with partial pooling for competitor and sentiment
only, or with centered control effects. A with more draws.

**Next:** validate `hier_media` (13-week holdout, 3 rolling-origin CV folds), then the gates. Awaiting
approval.

## 2. Protocol change: candidate C2 added after the first fits (user approved)

**Why:** C failed to sample, but its premise is supported by the data: competitor and sentiment effects vary
by geo (I² 0.94, 0.88), and both are confounders of spend. The selected B shares them across geos. C2 tests that
premise with a model built to sample. It uses only *where* C's sampling failed (a diagnostic), not any result.

**C2 `hier_media_hetero_controls`:** as B, plus competitor and sentiment effects partially pooled across geos
(spread prior 0.25 × the typical scaled week). Promo, organic and trend get a 100× tighter spread prior, which
keeps them effectively shared, matching the EDA (no significant heterogeneity). Centered parameterization,
because the geo-varying effects are strongly identified.

**Rule unchanged:** if C2 converges, B and C2 are compared by PSIS-LOO and the simpler (B) wins unless C2 is
better by more than 2 SE of the difference. If C2 does not converge, B stands. No reruns.

## 3. C2 fitted: not converged; `hier_media` stands

| Candidate | Status | R-hat max | ESS bulk / tail | Divergences | E-BFMI min |
|---|---|---|---|---|---|
| C2. `hier_media_hetero_controls` | not converged | 1.5209 | 7 / 9 | 357 | 0.078 |

Sampling took 29 minutes (B: 14). The failure sits in `gamma_control_sigma`, the cross-geo spread of the control
effects: a funnel. The centered parameterization was the wrong choice. For the three controls with a very tight
spread prior, the geo effects have to squeeze into a narrow neck as the spread shrinks, which centered sampling
cannot traverse.

**Selection (`make select`):** `hier_media` remains the only converged candidate and is selected.

**What could be done, and was not (protocol: no reruns):** C2 non-centered, or geo-varying effects for
competitor and sentiment only, with the other controls in a separate shared term (pymc-marketing applies one
prior to all controls, so this needs a custom additive effect).

**Limitation carried forward:** the selected model shares control effects across geos, although competitor and
sentiment effects vary by geo in the data (I² 0.94, 0.88). Both are confounders of spend, so geo-specific control
effects not captured by the model can bias media ROI.

**Next:** validate `hier_media` (13-week holdout, 3 rolling-origin CV folds), then the gates. Awaiting approval.
