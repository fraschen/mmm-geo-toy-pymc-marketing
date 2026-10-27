"""Measurement report for the selected spec: channel results, contribution decomposition, response curves
and a budget reallocation scenario.

    python -m mmm.report_measurement   ->  reports/measurement.md, reports/figures/meas_*.png,
                                           outputs/budget_scenario.{csv,json}

Scenario: replay the last 52 weeks with a different channel mix. Each channel's spend is multiplied by m_c,
keeping its geo split and weekly timing; total spend is unchanged. Channel response curves R_c(m) come from
pymc-marketing's counterfactual incrementality (adstock carryover included). The model is additive across
channels, so each curve is independent of the others. Multipliers are optimized on the posterior-mean curves
by greedy marginal-ROI equalization; the resulting uplift is then evaluated on every posterior draw.
"""

from __future__ import annotations

import json

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pymc as pm
import xarray as xr

from .config import OUTPUTS, ROOT, load_config
from .fitted import load_fitted
from .plotstyle import BAD, BAND, GOOD, INK, MUTED, SERIES, save, style, title

REPORTS = ROOT / "reports"
FIG = REPORTS / "figures"
WINDOW_WEEKS = 52
N_SAMPLES = 1000
SEED = 7
GRID = [0.0, 0.25, 0.5, 0.6, 0.7, 0.8, 0.85, 0.9, 0.95, 1.05, 1.1, 1.15, 1.2, 1.3, 1.4, 1.5, 1.75, 2.0]
SCENARIOS = {"main (±20% per channel)": (0.8, 1.2), "stress (±50% per channel)": (0.5, 1.5)}


def _stack(da: xr.DataArray) -> xr.DataArray:
    """Collapse all sample dims to `s`, keep `channel`."""
    other = [d for d in da.dims if d != "channel"]
    return da.stack(s=other).transpose("channel", "s")


def response_curves(mmm, start: str) -> tuple[np.ndarray, xr.DataArray]:
    """R[c, m, s]: incremental revenue of channel c over the window when its spend is m x actual."""
    inc = mmm.incrementality
    call = lambda f: _stack(inc.compute_incremental_contribution(  # noqa: E731
        frequency="all_time", start_date=start, num_samples=N_SAMPLES, random_state=SEED,
        counterfactual_spend_factor=f).sum(mmm.dims[0]).squeeze(drop=True))
    r1 = call(0.0)  # contribution at actual spend (vs zero spend)
    grid = sorted(set(GRID) | {1.0})
    curves = []
    for m in grid:
        if m == 0.0:
            curves.append(xr.zeros_like(r1))
        elif m == 1.0:
            curves.append(r1)
        else:  # documented convention: factor < 1 returns the loss from less spend, > 1 the gain from more
            d = call(m)
            curves.append(r1 - d if m < 1 else r1 + d)
    R = xr.concat(curves, dim=xr.DataArray(grid, dims="m", name="m")).transpose("channel", "m", "s")
    return np.array(grid), R


def optimize(grid, Rmean, spend, bounds, step_share: float = 0.002):
    """Budget-neutral reallocation on posterior-mean curves, by greedy marginal-ROI equalization.

    Repeatedly moves `step_share` of total spend from the channel with the lowest marginal return (that can
    still decrease) to the one with the highest (that can still increase), while that move gains revenue.
    Exact for concave (diminishing-returns) curves; total spend is conserved by construction.
    """
    rev = lambda i, m: np.interp(m, grid, Rmean[i])  # noqa: E731
    m = np.ones(len(spend))
    delta = step_share * spend.sum()
    for _ in range(100_000):
        up = [(rev(i, m[i] + delta / spend[i]) - rev(i, m[i]), i) for i in range(len(m)) if m[i] + delta / spend[i] <= bounds[1] + 1e-12]
        down = [(rev(i, m[i]) - rev(i, m[i] - delta / spend[i]), i) for i in range(len(m)) if m[i] - delta / spend[i] >= bounds[0] - 1e-12]
        if not up or not down:
            break
        gain, i_up = max(up)
        loss, i_down = min(down)
        if i_up == i_down or gain <= loss:
            break
        m[i_up] += delta / spend[i_up]
        m[i_down] -= delta / spend[i_down]
    return m


def evaluate(grid, R, m):
    """Per-draw revenue of allocation m and of the current allocation, summed over channels."""
    Rv = R.values  # channel, m, s
    new = np.array([[np.interp(m[c], grid, Rv[c, :, s]) for s in range(Rv.shape[2])] for c in range(Rv.shape[0])])
    cur = Rv[:, list(grid).index(1.0), :]
    return new, cur


def hdi(x, prob=0.94):
    x = np.sort(np.asarray(x).ravel())
    n = int(np.floor(prob * len(x)))
    i = np.argmin(x[n:] - x[: len(x) - n])
    return float(x[i]), float(x[i + n])


def decomposition(mmm):
    """Posterior contributions (every 4th draw): channels (date, channel), controls (date, control), baseline per week."""
    groups = {g: mmm.idata[g].to_dataset() for g in mmm.idata.children}
    post = groups["posterior"].isel(draw=slice(None, None, 4))
    names = ["channel_contribution_original_scale", "control_contribution_original_scale",
             "intercept_contribution_original_scale"]
    det = pm.compute_deterministics(post, var_names=names, model=mmm.model, progressbar=False)
    geo = mmm.dims[0]
    ch = det[names[0]].sum(geo)                      # chain, draw, date, channel
    ctrl = det[names[1]].sum(geo)                    # chain, draw, date, control
    intercept = det[names[2]].sum(geo)               # chain, draw (constant per week) or chain, draw, date
    if "date" not in intercept.dims:
        intercept = intercept.expand_dims(date=ch.date)
    return ch, ctrl, intercept


def fig_fit_with_baseline(ch, ctrl, intercept, md, path):
    baseline = intercept + ctrl.sum("control")
    expected = baseline + ch.sum("channel")
    obs = md.df.groupby(md.date_column)[md.target_column].sum()
    d = pd.to_datetime(expected.date.values)
    fig, ax = plt.subplots(figsize=(10, 3.4))
    for da, col, lab in ((expected, BAND, "expected (model)"), (baseline, SERIES[3], "baseline (no media)")):
        lo, med, hi = (da.quantile(q, ("chain", "draw")) / 1e6 for q in (0.03, 0.5, 0.97))
        ax.fill_between(d, lo, hi, color=col, alpha=0.18, lw=0)
        ax.plot(d, med, color=col, lw=1.4, label=lab)
    ax.plot(d, obs.values / 1e6, color=INK, lw=1, label="actual")
    ax.set_ylabel("Revenue (M)", fontsize=8)
    ax.set_ylim(0, None)
    ax.legend(frameon=False, fontsize=8, ncol=3, loc="lower left")
    title(ax, "Model fit: national weekly revenue, with the baseline the model attributes to non-media drivers",
          "medians and 94% bands; the gap between expected and baseline is media's contribution")
    style(ax)
    save(fig, path)


def fig_waterfall(ch, ctrl, intercept, chans, total_rev, path):
    parts = {"Baseline": intercept.sum("date"), "Controls (net)": ctrl.sum(("date", "control"))}
    parts.update({c: ch.sel(channel=c).sum("date") for c in chans})
    med = {k: float(v.median()) for k, v in parts.items()}
    lo_hi = {k: hdi(v.values) for k, v in parts.items()}
    labels = list(med) + ["Total (model)"]
    fig, ax = plt.subplots(figsize=(10, 3.8))
    cum = 0.0
    colors = [MUTED, MUTED] + SERIES[: len(chans)]
    for i, (k, v) in enumerate(med.items()):
        ax.bar(i, v / 1e6, bottom=cum / 1e6, color=colors[i], width=0.62)
        ax.errorbar(i, (cum + v) / 1e6, yerr=[[(v - lo_hi[k][0]) / 1e6], [(lo_hi[k][1] - v) / 1e6]], fmt="none",
                    ecolor=INK, lw=0.8, capsize=2)
        top = cum + max(v, lo_hi[k][1])
        ax.text(i, top / 1e6 + total_rev * 0.012 / 1e6, f"{v / 1e6:,.0f}M\n{v / total_rev:.1%}",
                ha="center", va="bottom", fontsize=7.5, color=INK)
        cum += v
    ax.bar(len(med), cum / 1e6, color=INK, width=0.62)
    ax.text(len(med), cum / 1e6 + total_rev * 0.012 / 1e6, f"{cum / 1e6:,.0f}M", ha="center", va="bottom", fontsize=7.5, color=INK)
    ax.set_xticks(range(len(labels)), labels, fontsize=8)
    ax.set_ylabel("Revenue over the period (M)", fontsize=8)
    ax.set_ylim(0, cum / 1e6 * 1.12)
    title(ax, "Contribution waterfall: how the model builds total revenue", "medians with 94% HDI per component; labels show revenue and share of actual revenue")
    style(ax)
    save(fig, path)
    return med


def fig_spend_vs_contribution(ch, chans, spend_tot, roi, path):
    tot = ch.sum("date")
    share_c = (tot / tot.sum("channel")).median(("chain", "draw")).to_series().loc[chans]
    share_s = spend_tot / spend_tot.sum()
    fig, ax = plt.subplots(figsize=(9, 3.6))
    x = np.arange(len(chans))
    ax.bar(x - 0.19, share_s.values, width=0.36, color=MUTED, label="share of media spend")
    ax.bar(x + 0.19, share_c.values, width=0.36, color=SERIES[0], label="share of media contribution")
    for i, c in enumerate(chans):
        ax.text(i, max(share_s.iloc[i], share_c.iloc[i]) + 0.012, f"ROI {roi[c]:.2f}", ha="center", fontsize=8, color=INK)
    ax.set_xticks(x, chans)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:.0%}"))
    ax.set_ylim(0, max(share_s.max(), share_c.max()) * 1.2)
    ax.legend(frameon=False, fontsize=8, loc="upper left")
    title(ax, "Spend share vs contribution share", "contribution share above spend share = the channel earns more than its budget weight")
    style(ax)
    save(fig, path)
    return share_s, share_c


def fig_saturation(mmm, md, spec, chans, path):
    post = mmm.idata.posterior.to_dataset()
    lam = post["saturation_lam"]
    pop = md.df[md.geo_column].map(md.population)
    x = np.linspace(0, 1.0, 101)
    logistic = lambda v, l: (1 - np.exp(-l * v)) / (1 + np.exp(-l * v))  # noqa: E731
    pri = spec["saturation_lam"]
    rng = np.random.default_rng(0)
    lam_prior = rng.gamma(pri["alpha"], 1 / pri["beta"], size=2000)
    fig, axes = plt.subplots(2, len(chans), figsize=(14, 4.2), sharex=True, gridspec_kw={"height_ratios": [2.4, 1]})
    for i, c in enumerate(chans):
        lv = lam.sel(channel=c).values.ravel()
        curves = logistic(x[None, :], lv[:, None])
        pc = logistic(x[None, :], lam_prior[:, None])
        ax = axes[0, i]
        ax.fill_between(x, *np.quantile(pc, [0.03, 0.97], axis=0), color=MUTED, alpha=0.15, lw=0, label="prior 94%")
        ax.fill_between(x, *np.quantile(curves, [0.03, 0.97], axis=0), color=SERIES[i], alpha=0.25, lw=0, label="posterior 94%")
        ax.plot(x, np.median(curves, axis=0), color=SERIES[i], lw=1.6)
        ax.set_ylim(0, 1.02)
        ax.set_title(c, fontsize=9, color=INK, loc="left")
        style(ax, "both")
        scaled = (md.df[c] / pop) / (md.df[c] / pop).max()
        ax2 = axes[1, i]
        ax2.hist(scaled[scaled > 0], bins=30, range=(0, 1), color=SERIES[i], alpha=0.7)
        ax2.text(0.98, 0.9, f"{(scaled == 0).mean():.0%} of weeks at 0", transform=ax2.transAxes, ha="right", va="top",
                 fontsize=7, color=MUTED)
        ax2.set_xlabel("Spend per capita, ÷ channel max", fontsize=7.5)
        style(ax2)
    axes[0, 0].set_ylabel("Share of max effect", fontsize=8)
    axes[1, 0].set_ylabel("Geo-weeks", fontsize=8)
    axes[0, 0].legend(frameon=False, fontsize=7, loc="lower right")
    fig.suptitle("Saturation curves (top) and where the data sits on them (bottom): the curve is only learned where spend was observed",
                 x=0.01, ha="left", fontsize=10.5, color=INK)
    save(fig, path)
    pw = np.subtract(*np.quantile(lam_prior, [0.97, 0.03]))
    return {c: float(np.subtract(*np.quantile(lam.sel(channel=c).values.ravel(), [0.97, 0.03])) / pw) for c in chans}


CAL_RUN = "hier_media_lift"


def calibration_section(spec: str, chans: list[str]) -> str:
    """Before/after comparison for the lift-test calibrated refit. Returns markdown ('' if the run is missing)."""
    mpath = OUTPUTS / "specs" / CAL_RUN / "metrics.json"
    if not mpath.exists():
        return ""
    cfg = load_config()
    cal_cfg = cfg["calibration_specs"][CAL_RUN]
    m_cal = json.loads(mpath.read_text())
    if m_cal.get("status") != "converged":
        return (f"## 5. Calibration with a hypothetical lift test\n\nThe calibrated refit did not converge "
                f"({'; '.join(m_cal.get('convergence_failures', []))}), so it has no results.\n")
    lift = pd.read_csv(ROOT / cal_cfg["lift_test"])
    before = pd.read_csv(OUTPUTS / "specs" / spec / "channel_metrics.csv").set_index("channel").loc[chans]
    after = pd.read_csv(OUTPUTS / "specs" / CAL_RUN / "channel_metrics.csv").set_index("channel").loc[chans]

    # model-implied return on the test increment (sum over test geos of delta_y / sum of delta_x), per draw
    var = "lift_measurements_model_estimated_lift_original_scale"
    implied = {}
    for label, run in (("uncalibrated", spec), ("calibrated", CAL_RUN)):
        mmm, md, _ = load_fitted(CAL_RUN)          # model with the lift-test node
        if run != CAL_RUN:                          # ...evaluated with the uncalibrated posterior
            mmm_u, _, _ = load_fitted(spec)
            post = mmm_u.idata.posterior.to_dataset()
        else:
            post = mmm.idata.posterior.to_dataset()
        post = post[[v for v in post.data_vars if v in {rv.name for rv in mmm.model.free_RVs}]]
        det = pm.compute_deterministics(post, var_names=[var], model=mmm.model, progressbar=False)[var]
        other = [d for d in det.dims if d not in ("chain", "draw")]
        implied[label] = (det.sum(other) / lift.delta_x.sum()).values.ravel()
    # per-geo Channel4 ROI in the uncalibrated model: explains what the model expected in the test geos
    mmm_u, md_u, _ = load_fitted(spec)
    post_u = mmm_u.idata.posterior.to_dataset().isel(draw=slice(None, None, 8))
    cc = pm.compute_deterministics(post_u, var_names=["channel_contribution_original_scale"], model=mmm_u.model,
                                   progressbar=False)["channel_contribution_original_scale"]
    ch_test = lift.channel.iloc[0]
    geo_c = cc.sel(channel=ch_test).mean(("chain", "draw")).sum("date").to_series()
    geo_s = md_u.df.groupby(md_u.geo_column)[ch_test].sum()
    geo_roi = geo_c / geo_s
    tg = lift[md_u.geo_column].tolist()
    roi_test_geos = float(geo_c.loc[tg].sum() / geo_s.loc[tg].sum())
    roi_other_geos = float(geo_c.drop(tg).sum() / geo_s.drop(tg).sum())
    test_roi = float(lift.delta_y.sum() / lift.delta_x.sum())
    test_se = float(np.sqrt((lift.sigma ** 2).sum()) / lift.delta_x.sum())

    fig, axes = plt.subplots(1, 2, figsize=(12, 3.8), gridspec_kw={"width_ratios": [1.5, 1]})
    ax = axes[0]
    y = np.arange(len(chans))
    for off, d, col, lab in ((-0.14, before, MUTED, "uncalibrated"), (0.14, after, SERIES[0], "calibrated with lift test")):
        ax.hlines(y + off, d.roi_hdi94_low, d.roi_hdi94_high, color=col, lw=2)
        ax.plot(d.roi_median, y + off, "o", ms=6, color=col, mec="white", mew=1, label=lab)
    ax.axvline(1, color=MUTED, ls="--", lw=1)
    ax.set_yticks(y, chans)
    ax.invert_yaxis()
    ax.set_xlabel("ROI (median and 94% HDI); dashed line = break-even", fontsize=8)
    ax.legend(frameon=False, fontsize=8, loc="lower right")
    title(ax, "Channel ROI before and after calibration", "the HYPOTHETICAL lift test covers Channel4 only")
    style(ax, "x")
    ax = axes[1]
    for i, (lab, v) in enumerate(implied.items()):
        lo_, hi_ = hdi(v)
        ax.hlines(i, lo_, hi_, color=[MUTED, SERIES[0]][i], lw=2)
        ax.plot(np.median(v), i, "o", ms=6, color=[MUTED, SERIES[0]][i], mec="white", mew=1)
    ax.errorbar(test_roi, 2, xerr=1.96 * test_se, fmt="D", color=SERIES[1], ms=6, capsize=3)
    ax.set_yticks([0, 1, 2], ["model, uncalibrated", "model, calibrated", "lift test (hypothetical)"])
    ax.invert_yaxis()
    ax.set_xlabel("Return on the test's extra Channel4 spend (revenue per $1)", fontsize=8)
    title(ax, "What the test measured vs what the model implies", "test: ±1.96 SE; model: 94% HDI")
    style(ax, "x")
    save(fig, FIG / "meas_calibration.png")

    rows = "\n".join(
        f"| {c} | {before.loc[c, 'roi_median']:.2f} ({before.loc[c, 'roi_hdi94_low']:.2f}–{before.loc[c, 'roi_hdi94_high']:.2f}) | "
        f"{after.loc[c, 'roi_median']:.2f} ({after.loc[c, 'roi_hdi94_low']:.2f}–{after.loc[c, 'roi_hdi94_high']:.2f}) | "
        f"{before.loc[c, 'prob_roi_gt_1']:.2f} → {after.loc[c, 'prob_roi_gt_1']:.2f} | "
        f"{before.loc[c, 'mroi_median']:.2f} → {after.loc[c, 'mroi_median']:.2f} |" for c in chans)
    c_cal = m_cal["convergence"]
    u, k = implied["uncalibrated"], implied["calibrated"]
    return f"""## 5. Calibration with a hypothetical lift test

> **The lift test here is invented.** No experiment exists for this dataset. It demonstrates how a real geo test
> would enter the model and what it changes; its numbers are not evidence about Channel4.

**Hypothetical test** ([`{cal_cfg['lift_test']}`](../{cal_cfg['lift_test']}), generated by `src/mmm/lift_test.py`): Channel4 spend
raised 50% above each test geo's average weekly spend, in {len(lift)} geos across the size range. Result: the extra spend
returned **{test_roi:.2f}** per $1 (standard error {test_se:.2f} pooled across geos). Channel4 was chosen because it is
the largest budget whose payback the model could not determine.

**How it enters the model:** pymc-marketing's `add_lift_test_measurements` adds a likelihood term requiring each test
geo's Channel4 saturation curve to reproduce the measured lift between spend `x` and `x + delta_x`. The selected
specification was refitted with this term (`{CAL_RUN}`): R-hat {c_cal['rhat_max']:.4f}, ESS {c_cal['ess_bulk_min']:.0f}, {c_cal['divergences']} divergences.

![Calibration](figures/meas_calibration.png)

| Channel | ROI uncalibrated (94% HDI) | ROI calibrated (94% HDI) | P(ROI > 1) | Marginal ROI |
|---|---|---|---|---|
{rows}

**What changed.** Before calibration the model implied the test increment would return {np.median(u):.2f} per $1
(94% HDI {hdi(u)[0]:.2f}–{hdi(u)[1]:.2f}); the test says {test_roi:.2f}. After calibration the model implies
{np.median(k):.2f} ({hdi(k)[0]:.2f}–{hdi(k)[1]:.2f}): it moves toward the test, weighted by the test's precision
against everything else the data says.

**Why the model expected so much in the test geos.** Under partial pooling, {ch_test}'s ROI varies widely by geo in
the uncalibrated model ({geo_roi.min():.2f} to {geo_roi.max():.2f}; median {geo_roi.median():.2f}). The test geos
happen to include several the model rates highly: spend-weighted ROI {roi_test_geos:.2f} in the test geos vs
{roi_other_geos:.2f} elsewhere. The test pulls those geos down, and through the shared hierarchy it pulls the
channel's national ROI down too. Two lessons:
- **Which geos are tested matters.** A real geo test should randomize or stratify its geo selection; a test in
  other geos would have moved the estimate differently.
- **Geo-level ROIs are not reliable.** With weak weekly signal (within-geo R² about 0.16), a spread this wide is
  most likely the hierarchy fitting noise. Report national channel ROI, not geo-level ROI.

Other channels change only through what they share with {ch_test} (the baseline and the hierarchy). A real test
result goes into the same file format.
"""


def main() -> None:
    cfg = load_config()
    spec = cfg["primary_spec"]
    FIG.mkdir(parents=True, exist_ok=True)
    res = pd.read_csv(OUTPUTS / "channel_results.csv")
    gate = json.loads((OUTPUTS / "gate_report.json").read_text())
    mmm, md, _ = load_fitted(spec)
    chans = md.channel_columns
    dates = np.sort(md.df[md.date_column].unique())
    start = pd.Timestamp(dates[-WINDOW_WEEKS])
    win = md.df[md.df[md.date_column] >= start]
    spend = win[chans].sum().to_numpy()
    total_rev_window = float(win[md.target_column].sum())
    total_rev = float(md.y.sum())

    # ---------------- decomposition, fit with baseline, waterfall, spend vs contribution, saturation
    ch_t, ctrl_t, int_t = decomposition(mmm)
    fig_fit_with_baseline(ch_t, ctrl_t, int_t, md, FIG / "meas_fit_baseline.png")
    wf = fig_waterfall(ch_t, ctrl_t, int_t, chans, total_rev, FIG / "meas_waterfall.png")
    spend_full = md.df[chans].sum()
    roi_med = res.set_index("channel").roi_median
    fig_spend_vs_contribution(ch_t, chans, spend_full, roi_med, FIG / "meas_spend_vs_contribution.png")
    for old in (FIG / "meas_cpik.png",):
        old.unlink(missing_ok=True)
    lam_ratio = fig_saturation(mmm, md, cfg["specs"][spec], chans, FIG / "meas_saturation.png")
    ch_tot = ch_t.sum("date")
    old = FIG / "meas_decomposition.png"
    if old.exists():
        old.unlink()

    wk = ch_t.median(("chain", "draw"))
    fig, ax = plt.subplots(figsize=(10, 3.3))
    d = pd.to_datetime(wk.date.values)
    for i, c in enumerate(chans):
        ax.plot(d, wk.sel(channel=c) / 1e6, color=SERIES[i], lw=1.3, label=c)
    ax.set_ylabel("Revenue (M)", fontsize=8)
    ax.legend(frameon=False, fontsize=8, ncol=5, loc="upper left")
    title(ax, "Weekly incremental revenue by channel (national, posterior median)")
    style(ax)
    save(fig, FIG / "meas_contribution_over_time.png")

    # ---------------- ROI and marginal ROI
    r = res.set_index("channel").loc[chans]
    fig, ax = plt.subplots(figsize=(8, 3.6))
    yv = np.arange(len(chans))
    ax.hlines(yv - 0.12, r.roi_hdi94_low, r.roi_hdi94_high, color=SERIES[0], lw=2)
    ax.plot(r.roi_median, yv - 0.12, "o", ms=6, color=SERIES[0], mec="white", mew=1, label="ROI (average)")
    ax.hlines(yv + 0.12, r.mroi_hdi94_low, r.mroi_hdi94_high, color=SERIES[1], lw=2)
    ax.plot(r.mroi_median, yv + 0.12, "o", ms=6, color=SERIES[1], mec="white", mew=1, label="marginal ROI (next 1%)")
    ax.axvline(1, color=MUTED, ls="--", lw=1)
    ax.set_yticks(yv, [f"{c}  (P(ROI>1) = {p:.2f})" for c, p in zip(chans, r.prob_roi_gt_1)], fontsize=8)
    ax.invert_yaxis()
    ax.set_xlabel("Incremental revenue per $1 of spend (median and 94% HDI); dashed line = break-even", fontsize=8)
    ax.legend(frameon=False, fontsize=8, loc="lower right")
    title(ax, "Channel ROI and marginal ROI")
    style(ax, "x")
    save(fig, FIG / "meas_roi.png")

    # ---------------- response curves + scenarios (last 52 weeks)
    grid, R = response_curves(mmm, str(start.date()))
    Rmean = R.mean("s").values
    lo = R.quantile(0.03, "s").values
    hi = R.quantile(0.97, "s").values
    results, allocs = {}, {}
    for name, b in SCENARIOS.items():
        m = optimize(grid, Rmean, spend, b)
        new, cur = evaluate(grid, R, m)
        upl = new.sum(0) - cur.sum(0)
        allocs[name] = m
        results[name] = {
            "bounds": list(b), "multipliers": dict(zip(chans, map(float, m))),
            "uplift_median": float(np.median(upl)), "uplift_hdi94": hdi(upl), "prob_uplift_gt_0": float((upl > 0).mean()),
            "uplift_pct_of_window_revenue": float(np.median(upl) / total_rev_window),
            "channel_change_median": dict(zip(chans, map(float, np.median(new - cur, axis=1)))),
        }
    main_name = next(iter(SCENARIOS))
    mm = allocs[main_name]
    new, cur = evaluate(grid, R, mm)
    sc = pd.DataFrame({
        "channel": chans, "current_spend": spend, "scenario_spend": spend * mm, "spend_change_pct": (mm - 1) * 100,
        "current_incremental_revenue_median": np.median(cur, 1), "scenario_incremental_revenue_median": np.median(new, 1),
        "incremental_revenue_change_median": np.median(new - cur, 1),
        "marginal_roi_at_current_spend": [(np.interp(1.05, grid, Rmean[i]) - np.interp(0.95, grid, Rmean[i])) / (0.1 * spend[i])
                                          for i in range(len(chans))],
    })
    sc.to_csv(OUTPUTS / "budget_scenario.csv", index=False, float_format="%.6g")
    (OUTPUTS / "budget_scenario.json").write_text(json.dumps({
        "window": [str(start.date()), str(pd.Timestamp(dates[-1]).date())], "total_spend_window": float(spend.sum()),
        "revenue_window": total_rev_window, "posterior_draws": N_SAMPLES, "scenarios": results}, indent=2))

    fig, axes = plt.subplots(1, len(chans), figsize=(14, 3.2), sharey=False)
    for i, (ax, c) in enumerate(zip(axes, chans)):
        x = grid * spend[i] / 1e6
        ax.fill_between(x, lo[i] / 1e6, hi[i] / 1e6, color=SERIES[i], alpha=0.18, lw=0)
        ax.plot(x, Rmean[i] / 1e6, color=SERIES[i], lw=1.6)
        ax.axvspan(0.8 * spend[i] / 1e6, 1.2 * spend[i] / 1e6, color=MUTED, alpha=0.08, lw=0)
        ax.plot(spend[i] / 1e6, np.interp(1, grid, Rmean[i]) / 1e6, "o", color=INK, ms=5, label="current")
        ax.plot(mm[i] * spend[i] / 1e6, np.interp(mm[i], grid, Rmean[i]) / 1e6, "D", color=SERIES[i], mec=INK, ms=5,
                label="scenario")
        ax.plot(x, x, color=MUTED, lw=0.8, ls=":")
        ax.set_title(c, fontsize=9, color=INK, loc="left")
        ax.set_xlabel("Spend over 52 weeks (M)", fontsize=7.5)
        style(ax, "both")
    axes[0].set_ylabel("Incremental revenue (M)", fontsize=8)
    axes[0].legend(frameon=False, fontsize=7, loc="upper left")
    fig.suptitle("Response curves, last 52 weeks (mean and 94% band; dotted = break-even; shaded = ±20% range)",
                 x=0.01, ha="left", fontsize=10.5, color=INK)
    save(fig, FIG / "meas_response_curves.png")

    fig, axes = plt.subplots(1, 2, figsize=(11, 3.4), gridspec_kw={"width_ratios": [1.3, 1]})
    ax = axes[0]
    ax.barh(yv, sc.spend_change_pct, color=[GOOD if v > 0 else BAD for v in sc.spend_change_pct], height=0.55)
    for yy, v, dv in zip(yv, sc.spend_change_pct, sc.incremental_revenue_change_median):
        ax.text(v + (1 if v >= 0 else -1), yy, f"{v:+.0f}%  ({dv / 1e3:+,.0f}k revenue)", va="center",
                ha="left" if v >= 0 else "right", fontsize=7.5, color=INK)
    ax.axvline(0, color=MUTED, lw=0.8)
    ax.set_yticks(yv, chans)
    ax.invert_yaxis()
    ax.set_xlim(-45, 45)
    ax.set_xlabel("Spend change vs last 52 weeks", fontsize=8)
    title(ax, "Main scenario: budget-neutral reallocation (±20% per channel)")
    style(ax, "x")
    ax = axes[1]
    upl = evaluate(grid, R, mm)[0].sum(0) - evaluate(grid, R, mm)[1].sum(0)
    ax.hist(upl / 1e6, bins=50, color=SERIES[0], alpha=0.75)
    ax.axvline(0, color=INK, lw=1)
    title(ax, "Incremental revenue gained (posterior draws)",
          f"median {np.median(upl) / 1e6:+.2f}M; P(gain > 0) = {(upl > 0).mean():.2f}")
    ax.set_xlabel("Revenue change over 52 weeks (M)", fontsize=8)
    style(ax)
    save(fig, FIG / "meas_scenario.png")

    # ---------------- markdown
    def fmt_m(v):
        return f"{v / 1e6:,.2f}M"
    rows = "\n".join(
        f"| {c.channel} | {c.spend_share:.1%} | {c.roi_median:.2f} ({c.roi_hdi94_low:.2f}–{c.roi_hdi94_high:.2f}) | "
        f"{c.prob_roi_gt_1:.2f} | {c.mroi_median:.2f} | {fmt_m(c.contribution_median)} ({fmt_m(c.contribution_hdi94_low)}–"
        f"{fmt_m(c.contribution_hdi94_high)}) | {c.contribution_share_of_revenue_mean:.1%} | "
        f"{c.roi_median_min_across_cv_folds:.2f}–{c.roi_median_max_across_cv_folds:.2f} | {c.channel_gate_status} |"
        for c in res.itertuples())
    srows = "\n".join(
        f"| {s.channel} | {fmt_m(s.current_spend)} | {fmt_m(s.scenario_spend)} | {s.spend_change_pct:+.0f}% | "
        f"{s.marginal_roi_at_current_spend:.2f} | {s.incremental_revenue_change_median / 1e3:+,.0f}k |" for s in sc.itertuples())
    scen_rows = "\n".join(
        f"| {k} | " + ", ".join(f"{c} {v:.2f}×" for c, v in r_["multipliers"].items()) +
        f" | {r_['uplift_median'] / 1e6:+.2f}M ({r_['uplift_hdi94'][0] / 1e6:+.2f} to {r_['uplift_hdi94'][1] / 1e6:+.2f}) | "
        f"{r_['uplift_pct_of_window_revenue']:+.2%} | {r_['prob_uplift_gt_0']:.2f} |" for k, r_ in results.items())
    total_media = float(np.median(ch_tot.sum("channel").values))

    missing = [r["check"] for rs in gate["sections"].values() for r in rs if "exists" in r["check"] and r["status"] == "FAIL"]
    banner = ("> **Preliminary.** Generated before all validation fits finished, so the model-health status below is\n"
              "> incomplete and the CV columns may cover only some folds. Rerun `make gates results reports` when done.\n\n"
              if missing else "")
    text = banner + f"""# Measurement report: `{spec}`

Model health: **{gate['verdict']}** (see [diagnostics.md](diagnostics.md)). Period {res.period_start[0]} to
{res.period_end[0]}, 40 geos. ROI is incremental revenue per unit of spend: revenue with actual spend minus
revenue with the channel switched off, including adstock carryover, divided by spend.

## 1. Channel results

Machine-readable: [`outputs/channel_results.csv`](../outputs/channel_results.csv) (one row per channel; column
definitions in [`outputs/channel_results_metadata.json`](../outputs/channel_results_metadata.json)).

| Channel | Spend share | ROI median (94% HDI) | P(ROI > 1) | Marginal ROI | Incremental revenue (94% HDI) | Share of revenue | ROI range across CV folds | Gate |
|---|---|---|---|---|---|---|---|---|
{rows}

![ROI](figures/meas_roi.png)

![Spend vs contribution](figures/meas_spend_vs_contribution.png)

Paid media drives {total_media / total_rev:.1%} of revenue (posterior median). Marginal ROI below average ROI
means diminishing returns: the next dollar earns less than the average dollar so far.

## 2. Where revenue comes from

![Model fit with baseline](figures/meas_fit_baseline.png)

![Contribution waterfall](figures/meas_waterfall.png)

Baseline is revenue the model attributes to non-media drivers (geo intercepts); controls are competitor sales,
sentiment, promo, organic impressions and trend. Baseline and media trade off in the posterior (correlation
about −0.9; see diagnostics), so channel rankings are firmer than the absolute split.

![Contribution over time](figures/meas_contribution_over_time.png)

## 3. Response curves

![Response curves](figures/meas_response_curves.png)

![Saturation](figures/meas_saturation.png)

Saturation curves (top row, normalized to each channel's maximum effect) show how quickly returns diminish; the
histograms below show where the data actually sits. Where there is little data, the curve follows the prior
(grey band), so spend levels beyond the observed range are an extrapolation.

How much the data narrowed each curve's shape (posterior ÷ prior 94% width of the saturation rate λ; 1.0 = learned
nothing): """ + ", ".join(f"{c} {v:.2f}" for c, v in lam_ratio.items()) + f""". Channels near 1.0 have curve
shapes set mostly by the prior, so their marginal ROI and the reallocation scenario rest more on assumptions than on
data for those channels.

Each response curve shows incremental revenue over the last 52 weeks if that channel's spend were scaled up or down,
keeping its geo split and weekly timing. The flatter the curve at the current point, the less the next dollar
earns. Bands widen away from current spend because the data rarely observed those levels.

## 4. Budget reallocation scenario

**Question:** with the same total budget as the last 52 weeks ({fmt_m(spend.sum())}), how should spend be split
across channels? Each channel's spend is scaled by a multiplier, keeping its geo split and timing; total spend
is held fixed. The multipliers maximize expected incremental revenue on the posterior-mean response curves, and
the gain is then evaluated on {N_SAMPLES} posterior draws.

| Scenario | Spend multipliers | Revenue gain over 52 weeks, median (94% HDI) | % of revenue | P(gain > 0) |
|---|---|---|---|---|
{scen_rows}

Main scenario detail ([`outputs/budget_scenario.csv`](../outputs/budget_scenario.csv)):

| Channel | Current spend | Scenario spend | Change | Marginal ROI at current spend | Revenue change (median) |
|---|---|---|---|---|---|
{srows}

![Scenario](figures/meas_scenario.png)

**How to read this.** Money moves from channels with low marginal ROI to channels with high marginal ROI until
the limit (±20%) binds. The ±50% scenario has a larger expected gain and a wider interval, which includes a small
chance of a loss: that spread is part of the answer, and how much risk to take is a business decision. The ±20%
range stays close to spend levels the data has seen; further out, the intervals also rest on the assumed logistic
shape of the response curve, which they do not include uncertainty about.

## 5. Caveats for using these numbers

- **Undetermined channels.** Channels whose P(ROI > 1) is between 0.1 and 0.9 cannot be called profitable or
  unprofitable; their gate status is WARN.
- **Shared control effects.** The model assumes competitor and sentiment effects are the same in every geo,
  although the data says they differ (I² 0.94, 0.88). Both correlate with spend, so some of their geo-specific
  effect may be attributed to media.
- **No geo-level ROI.** Geo-level effects vary widely in the model and are not reliable individually; use the
  national channel results.
- **Baseline vs media.** The data pins down total revenue better than its split between baseline and media;
  absolute contributions are less certain than channel rankings.
- **Scenario, not forecast.** The reallocation replays last year's conditions. It assumes the response curves
  hold and that competitors and other drivers do not react.
- **Validation.** Lift tests (geo holdouts) on the largest budgets would calibrate these curves and are the most
  direct way to firm up the recommendations.
"""
    cal = calibration_section(spec, chans)
    if cal:
        text = text.replace("## 5. Caveats for using these numbers", cal + "\n## 6. Caveats for using these numbers")
    (REPORTS / "measurement.md").write_text(text)
    print(f"wrote {REPORTS / 'measurement.md'}")
    print(json.dumps({k: {kk: v[kk] for kk in ('uplift_median', 'uplift_hdi94', 'prob_uplift_gt_0')} for k, v in results.items()}, indent=1))


if __name__ == "__main__":
    main()
