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

The selection protocol was fixed before fitting (README): converge or stop, select by PSIS-LOO with a preference
for the simpler candidate within 2 SE, then holdout, CV, a prior-sensitivity refit and the gates.

**Status:** awaiting approval to fit.
