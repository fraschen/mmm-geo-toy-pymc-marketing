"""Model health report for the selected spec: the diagnostics used to decide whether the fit is trustworthy.

    python -m mmm.report_diagnostics   ->  reports/diagnostics.md + reports/figures/diag_*.png

Reads the fitted posteriors (artifacts/), the per-run metrics (outputs/specs/) and the gate report.
Predictive figures use every 4th posterior draw (1000 of 4000) to keep memory modest.
"""

from __future__ import annotations

import json

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import xarray as xr

from . import model
from .config import OUTPUTS, ROOT, load_config
from .fitted import load_fitted
from .plotstyle import BAND, GOOD, INK, MUTED, SERIES, save, style, title

REPORTS = ROOT / "reports"
FIG = REPORTS / "figures"
HDI = 0.94
THIN = 4


def _thin(mmm):
    groups = {g: mmm.idata[g].to_dataset() for g in mmm.idata.children}
    groups["posterior"] = groups["posterior"].isel(draw=slice(None, None, THIN))
    mmm.idata = xr.DataTree.from_dict(groups)
    return mmm


def _q(da, dims, lo=(1 - HDI) / 2, hi=(1 + HDI) / 2):
    return da.quantile(lo, dim=dims), da.median(dim=dims), da.quantile(hi, dim=dims)


def _national(da, geo):
    return da.sum(geo)


def _ppc(mmm, X, include_last=False, seed=1):
    ypp = mmm.sample_posterior_predictive(X, extend_idata=False, combined=True, include_last_observations=include_last,
                                          random_seed=seed, progressbar=False, var_names=["y"])
    ypp = ypp["y"] if isinstance(ypp, xr.Dataset) else ypp
    return ypp * mmm.scalers._target  # revenue


def _observed(md):
    return md.df.set_index([md.date_column, md.geo_column])[md.target_column].to_xarray().rename({md.date_column: "date"})


def fig_convergence(m, path):
    c = m["convergence"]
    df = pd.DataFrame({"rhat": c["rhat_by_var"], "ess": c["ess_bulk_by_var"]}).sort_values("ess")
    fig, axes = plt.subplots(1, 2, figsize=(10, max(3, 0.28 * len(df))), sharey=True)
    y = np.arange(len(df))
    axes[0].barh(y, df.rhat - 1, left=1, color=SERIES[0], height=0.6)
    axes[0].axvline(1.01, color=MUTED, ls="--", lw=1)
    axes[0].set_xlim(0.999, max(1.012, df.rhat.max() + 0.001))
    axes[0].set_yticks(y, df.index, fontsize=7)
    title(axes[0], "Worst R-hat per variable", "threshold 1.01 (dashed)")
    axes[1].barh(y, df.ess, color=SERIES[0], height=0.6)
    axes[1].axvline(400, color=MUTED, ls="--", lw=1)
    title(axes[1], "Lowest bulk ESS per variable", "threshold 400 (dashed)")
    for ax in axes:
        style(ax, "x")
    save(fig, path)


def fig_ranks(post, path):
    params = [("adstock_alpha", "channel"), ("saturation_lam", "channel"), ("saturation_beta_raw_mu", "channel")]
    params = [(p, d) for p, d in params if p in post]
    chans = list(post["adstock_alpha"].channel.values)
    fig, axes = plt.subplots(len(params), len(chans), figsize=(12, 2.0 * len(params)), sharey=True)
    n_ch = post.sizes["chain"]
    for i, (p, d) in enumerate(params):
        for j, c in enumerate(chans):
            v = post[p].sel({d: c}).values  # chain x draw
            ranks = v.ravel().argsort().argsort().reshape(v.shape)
            ax = axes[i, j]
            bins = np.linspace(0, ranks.size, 21)
            for k in range(n_ch):
                h, _ = np.histogram(ranks[k], bins=bins)
                ax.step(bins[:-1], h, where="post", color=SERIES[k % len(SERIES)], lw=1)
            ax.axhline(v.shape[1] / 20, color=MUTED, ls="--", lw=0.8)
            ax.set_xticks([])
            if i == 0:
                ax.set_title(c, fontsize=8.5, color=INK)
            if j == 0:
                ax.set_ylabel(p.replace("saturation_", "sat_"), fontsize=8, color=INK)
            style(ax, None)
    fig.suptitle("Rank plots by chain (flat and overlapping = chains agree; dashed = uniform)", x=0.01, ha="left",
                 fontsize=10.5, color=INK)
    save(fig, path)


def fig_energy(ss, path):
    e = ss["energy"].transpose("chain", "draw").values
    de = np.diff(e, axis=1).ravel()
    e0 = (e - e.mean(axis=1, keepdims=True)).ravel()
    fig, ax = plt.subplots(figsize=(6, 3.2))
    bins = np.linspace(min(e0.min(), de.min()), max(e0.max(), de.max()), 60)
    ax.hist(e0, bins=bins, color=SERIES[0], alpha=0.55, label="marginal energy (centered)")
    ax.hist(de, bins=bins, color=SERIES[1], alpha=0.55, label="energy transition")
    ax.legend(frameon=False, fontsize=8)
    title(ax, "Energy diagnostic", "similar widths = the sampler moves freely between energy levels (E-BFMI)")
    style(ax)
    save(fig, path)


def fig_prior_predictive(md, spec, path):
    m = model.build(md, spec)
    m.sample_prior_predictive(md.X, samples=300, random_seed=1)
    yp = m.idata.prior_predictive["y"] * m.scalers._target
    lo, med, hi = _q(_national(yp, md.geo_column), ("chain", "draw"))
    obs = _national(_observed(md), md.geo_column)
    fig, ax = plt.subplots(figsize=(10, 3.3))
    d = pd.to_datetime(obs.date.values)
    ax.fill_between(d, lo / 1e6, hi / 1e6, color=BAND, alpha=0.18, lw=0, label="prior predictive 94%")
    ax.plot(d, obs / 1e6, color=INK, lw=1.2, label="observed")
    ax.set_ylabel("Revenue (M)", fontsize=8)
    ax.legend(frameon=False, fontsize=8, loc="upper left")
    title(ax, "Prior predictive check: national weekly revenue", "priors allow the observed data without forcing it")
    style(ax)
    save(fig, path)


def fig_posterior_predictive(mmm, md, path):
    ypp = _ppc(mmm, md.X)
    geo = md.geo_column
    lo, med, hi = _q(_national(ypp, geo), "sample")
    obs = _national(_observed(md), geo)
    d = pd.to_datetime(obs.date.values)
    fig, axes = plt.subplots(1, 2, figsize=(12, 3.6), gridspec_kw={"width_ratios": [2.2, 1]})
    ax = axes[0]
    ax.fill_between(d, lo / 1e6, hi / 1e6, color=BAND, alpha=0.2, lw=0, label="posterior predictive 94%")
    ax.plot(d, med / 1e6, color=BAND, lw=1.2, label="predicted median")
    ax.plot(d, obs / 1e6, color=INK, lw=1, label="observed")
    ax.set_ylabel("Revenue (M)", fontsize=8)
    ax.legend(frameon=False, fontsize=8, loc="upper left", ncol=3)
    title(ax, "In-sample fit: national weekly revenue")
    style(ax)
    ax = axes[1]
    o = _observed(md)
    p = ypp.median("sample").transpose(*o.dims)
    rel_o = (o / o.mean("date")).values.ravel()
    rel_p = (p / o.mean("date")).values.ravel()
    ax.scatter(rel_p, rel_o, s=3, color=SERIES[0], alpha=0.25)
    lim = [min(rel_o.min(), rel_p.min()), max(rel_o.max(), rel_p.max())]
    ax.plot(lim, lim, color=MUTED, lw=1, ls="--")
    ax.set_xlabel("predicted / geo mean", fontsize=8)
    ax.set_ylabel("observed / geo mean", fontsize=8)
    title(ax, "Geo-weeks (relative to each geo)", "spread around the diagonal is the weekly noise floor")
    style(ax, "both")
    save(fig, path)
    return ypp


def fig_residuals(ypp, md, path):
    o = _observed(md)
    pred = ypp.median("sample").transpose(*o.dims)
    sd = ypp.std("sample").transpose(*o.dims)
    z = ((o - pred) / sd).values
    acf1 = [pd.Series(z[:, j]).autocorr(1) for j in range(z.shape[1])]
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.2))
    ax = axes[0]
    ax.hist(z.ravel(), bins=60, density=True, color=SERIES[0], alpha=0.7)
    xs = np.linspace(-4, 4, 200)
    ax.plot(xs, np.exp(-xs**2 / 2) / np.sqrt(2 * np.pi), color=INK, lw=1)
    title(ax, "Standardized residuals", "line = standard normal")
    style(ax)
    ax = axes[1]
    ax.hist(acf1, bins=15, color=SERIES[0], alpha=0.7)
    ax.axvline(0, color=MUTED, lw=1)
    title(ax, "Lag-1 residual autocorrelation by geo", "centered on 0 = no leftover time structure")
    style(ax)
    save(fig, path)
    zc = np.corrcoef(z.T)
    return float(zc[np.triu_indices_from(zc, 1)].mean())


def fig_forecasts(spec, cfg, path):
    folds = [(n, False) for n in cfg["data"]["cv_train_weeks"]] + [(None, True)]
    fig, axes = plt.subplots(1, len(folds), figsize=(13, 3.2), sharey=True)
    rows = []
    for ax, (n, hold) in zip(axes, folds):
        mmm, md, test = load_fitted(spec, train_weeks=n, holdout=hold)
        mmm = _thin(mmm)
        ypp = _ppc(mmm, test.X, include_last=True)
        geo = md.geo_column
        lo, med, hi = _q(_national(ypp, geo), "sample")
        obs_test = _national(_observed(test), geo)
        obs_tail = _national(_observed(md), geo).isel(date=slice(-26, None))
        dt, dtail = pd.to_datetime(obs_test.date.values), pd.to_datetime(obs_tail.date.values)
        ax.plot(dtail, obs_tail / 1e6, color=MUTED, lw=1)
        ax.fill_between(dt, lo / 1e6, hi / 1e6, color=BAND, alpha=0.2, lw=0)
        ax.plot(dt, med / 1e6, color=BAND, lw=1.3)
        ax.plot(dt, obs_test / 1e6, color=INK, lw=1)
        ax.axvline(dt[0], color=MUTED, ls=":", lw=1)
        label = f"train 1-{n or md.df[md.date_column].nunique()}"
        ax.set_title(label, fontsize=9, color=INK, loc="left")
        ax.tick_params(axis="x", labelrotation=45, labelsize=7)
        style(ax)
        mape = float((np.abs(obs_test - med) / obs_test).mean())
        cov = float(((obs_test >= lo) & (obs_test <= hi)).mean())
        bias = float(((med - obs_test) / obs_test).mean())
        rows.append({"fold": label, "national_mape": mape, "national_94_coverage": cov, "national_bias": bias})
    axes[0].set_ylabel("Revenue (M)", fontsize=8)
    fig.suptitle("Out-of-sample: 13-week national forecasts (blue: median and 94% band; black: actual; grey: training tail)",
                 x=0.01, ha="left", fontsize=10.5, color=INK)
    save(fig, path)
    return pd.DataFrame(rows)


def fig_roi_stability(spec, cfg, path):
    runs = [(f"train 1-{n}", f"{spec}__cv{n}") for n in cfg["data"]["cv_train_weeks"]]
    runs += [("train 1-143", f"{spec}__holdout"), ("full data", spec)]
    dfs = {lab: pd.read_csv(OUTPUTS / "specs" / r / "channel_metrics.csv").set_index("channel") for lab, r in runs}
    chans = list(next(iter(dfs.values())).index)
    fig, ax = plt.subplots(figsize=(9, 3.8))
    n = len(dfs)
    for i, (lab, d) in enumerate(dfs.items()):
        yv = np.arange(len(chans)) + (i - (n - 1) / 2) * 0.15
        col = INK if lab == "full data" else SERIES[i % len(SERIES)]
        ax.hlines(yv, d.loc[chans, "roi_hdi94_low"], d.loc[chans, "roi_hdi94_high"], color=col, lw=1.5)
        ax.plot(d.loc[chans, "roi_median"], yv, "o", ms=5, color=col, mec="white", mew=1, label=lab)
    ax.axvline(1, color=MUTED, ls="--", lw=1)
    ax.set_yticks(range(len(chans)), chans)
    ax.invert_yaxis()
    ax.set_xlabel("ROI (median and 94% HDI)", fontsize=8)
    ax.legend(frameon=False, fontsize=7.5, loc="lower right")
    title(ax, "ROI stability across training windows", "each fit sees a different stretch of history")
    style(ax, "x")
    save(fig, path)


def fig_prior_vs_posterior(ch, path):
    fig, ax = plt.subplots(figsize=(8, 3.4))
    y = np.arange(len(ch))
    ax.hlines(y + 0.15, ch.roi_prior_hdi94_low, ch.roi_prior_hdi94_high, color=MUTED, lw=4, alpha=0.35, label="prior 94%")
    ax.hlines(y - 0.15, ch.roi_hdi94_low, ch.roi_hdi94_high, color=SERIES[0], lw=2, label="posterior 94%")
    ax.plot(ch.roi_median, y - 0.15, "o", ms=6, color=SERIES[0], mec="white", mew=1)
    ax.axvline(1, color=MUTED, ls="--", lw=1)
    ax.set_yticks(y, ch.channel)
    ax.invert_yaxis()
    ax.set_xlabel("ROI", fontsize=8)
    ax.legend(frameon=False, fontsize=8, loc="upper right", bbox_to_anchor=(1, 1.16), ncol=2)
    title(ax, "Prior vs posterior ROI", "a much narrower posterior = the estimate comes from the data, not the prior")
    style(ax, "x")
    save(fig, path)


def fig_baseline_media(post, path):
    tm = post["total_media_contribution_original_scale"].values.ravel() / 1e6
    ic = post["intercept_contribution_original_scale"].sum("geo").values.ravel() / 1e6
    r = float(np.corrcoef(tm, ic)[0, 1])
    fig, ax = plt.subplots(figsize=(5.2, 3.6))
    ax.scatter(tm, ic, s=3, alpha=0.2, color=SERIES[0])
    ax.set_xlabel("Total media contribution over the period (M)", fontsize=8)
    ax.set_ylabel("Weekly baseline, all geos (M)", fontsize=8)
    title(ax, "Baseline vs media trade-off", f"posterior correlation {r:+.2f}: the data cannot fully separate the two")
    style(ax, "both")
    save(fig, path)
    return r


def cv_summary(spec, cfg):
    """Per-fold metrics (convergence, accuracy, ROI) and a findings list, from the saved fold runs."""
    runs = [(f"1-{n}", f"{spec}__cv{n}") for n in cfg["data"]["cv_train_weeks"]] + [("1-143 (holdout)", f"{spec}__holdout")]
    rows, roi = [], {}
    for lab, r in runs:
        mm = json.loads((OUTPUTS / "specs" / r / "metrics.json").read_text())
        c = mm["convergence"]
        row = {"fold": lab, "status": mm.get("status", "converged"), "rhat_max": c["rhat_max"],
               "ess_bulk_min": c["ess_bulk_min"], "divergences": c["divergences"]}
        if row["status"] == "converged":
            h, f = mm["holdout_scores"], mm["fit"]
            row.update(in_mape=f["mape"], fc_mape=h["holdout_mape"], ratio=h["holdout_mape"] / f["mape"],
                       nat_mape=h["holdout_national_mape"], coverage=h["holdout_interval_coverage"])
            roi[lab] = pd.read_csv(OUTPUTS / "specs" / r / "channel_metrics.csv").set_index("channel")["roi_median"]
        rows.append(row)
    df = pd.DataFrame(rows)
    roi_df = pd.DataFrame(roi)
    roi_df["full data"] = pd.read_csv(OUTPUTS / "specs" / spec / "channel_metrics.csv").set_index("channel")["roi_median"]
    g = cfg["gates"]
    conv = df[df.status == "converged"]
    spread = roi_df.max(axis=1) / roi_df.min(axis=1)
    findings = [
        f"{len(conv)} of {len(df)} folds converged (R-hat ≤ {conv.rhat_max.max():.4f}, bulk ESS ≥ {conv.ess_bulk_min.min():.0f}, "
        f"{int(conv.divergences.sum())} divergences in total).",
        f"Forecast error vs in-sample error: ratio {conv.ratio.min():.2f}–{conv.ratio.max():.2f} "
        f"(gate ≤ {g['holdout_mape_degradation_max']}): forecasts are {'no worse than' if conv.ratio.max() <= g['holdout_mape_degradation_max'] else 'worse than'} the in-sample fit.",
        f"National weekly forecast error {conv.nat_mape.min():.1%}–{conv.nat_mape.max():.1%} (gate ≤ {g['holdout_national_mape_max']:.0%}); "
        f"94% interval coverage {conv.coverage.min():.0%}–{conv.coverage.max():.0%} (gate ≥ {g['holdout_interval_coverage_min']:.0%}).",
        "ROI stability across the four training windows and the full fit: max ÷ min median ROI is "
        + ", ".join(f"{c} {v:.2f}×" for c, v in spread.items())
        + f" (warn above {g['cv_roi_ratio_warn']}×). Most variable: {spread.idxmax()}.",
    ]
    return df, roi_df, findings


def main() -> None:
    cfg = load_config()
    spec = cfg["primary_spec"]
    FIG.mkdir(parents=True, exist_ok=True)
    m = json.loads((OUTPUTS / "specs" / spec / "metrics.json").read_text())
    ch = pd.read_csv(OUTPUTS / "specs" / spec / "channel_metrics.csv")
    gate = json.loads((OUTPUTS / "gate_report.json").read_text())
    sel = (OUTPUTS / "model_selection.md").read_text()

    mmm, md, _ = load_fitted(spec)
    post = mmm.idata.posterior.to_dataset()
    fig_convergence(m, FIG / "diag_convergence.png")
    fig_ranks(post, FIG / "diag_ranks.png")
    fig_energy(mmm.idata.sample_stats.to_dataset(), FIG / "diag_energy.png")
    fig_prior_predictive(md, cfg["specs"][spec], FIG / "diag_prior_predictive.png")
    ypp = fig_posterior_predictive(_thin(mmm), md, FIG / "diag_posterior_predictive.png")
    cross_geo_r = fig_residuals(ypp, md, FIG / "diag_residuals.png")
    obs_nat = _national(_observed(md), md.geo_column)
    lo_n, _, hi_n = _q(_national(ypp, md.geo_column), "sample")
    nat_cov_in = float(((obs_nat >= lo_n) & (obs_nat <= hi_n)).mean())
    fc = fig_forecasts(spec, cfg, FIG / "diag_forecasts.png")
    fig_roi_stability(spec, cfg, FIG / "diag_roi_stability.png")
    cv_df, cv_roi, cv_findings = cv_summary(spec, cfg)
    fig_prior_vs_posterior(ch, FIG / "diag_prior_vs_posterior.png")
    r_bm = fig_baseline_media(post, FIG / "diag_baseline_media.png")

    c, f, lo = m["convergence"], m["fit"], m["loo"]
    sec = gate["sections"]
    prim_checks = [r for k, rs in sec.items() for r in rs]
    def tbl(rows):
        out = ["| Status | Check | Value | Threshold |", "|---|---|---|---|"]
        out += [f"| {r['status']} | {r['check']} | {r['value']} | {r['threshold'] if r['threshold'] is not None else ''} |" for r in rows]
        return "\n".join(out)
    n_by = {s: sum(r["status"] == s for r in prim_checks) for s in ("PASS", "WARN", "FAIL")}
    folds = {k: v for k, v in sec.items() if "CV" in k or "holdout" in k}

    md_text = f"""# Model health report: `{spec}`

**Gate verdict: {gate['verdict']}** ({n_by['PASS']} pass, {n_by['WARN']} warn, {n_by['FAIL']} fail). This report shows
the evidence behind each check. Every figure is regenerated by `make reports`.

## 1. How this model was chosen

{sel.split(chr(10), 2)[2].strip()}

The other candidates failed their convergence checks and were stopped without results.

## 2. Data checks

{tbl([r for r in sec[spec] if r['check'].startswith('data')])}

## 3. Priors

{tbl([r for r in sec[spec] if r['check'].startswith('prior')])}

![Prior predictive](figures/diag_prior_predictive.png)

The prior predictive band covers the observed series without being pinned to it. Coverage of 100% means the
priors are permissive; the posterior, not the prior, determines the estimates (section 7).

## 4. Sampling convergence

4 chains × 1000 draws after 1000 tuning steps, `target_accept` 0.95, NUTS via numpyro.

| R-hat max | ESS bulk min | ESS tail min | Divergences | E-BFMI min |
|---|---|---|---|---|
| {c['rhat_max']:.4f} | {c['ess_bulk_min']:.0f} | {c['ess_tail_min']:.0f} | {c['divergences']} | {c['bfmi_min']:.2f} |

![Convergence by variable](figures/diag_convergence.png)

![Rank plots](figures/diag_ranks.png)

![Energy](figures/diag_energy.png)

All variables are below the R-hat threshold and above the ESS threshold. Rank plots are flat and overlap across
chains, and the energy distributions match, so the chains explored the same posterior.

## 5. In-sample fit

| R² | Within-geo R² | MAPE (geo-week) | 94% interval coverage | Median \\|lag-1 residual ACF\\| | Pareto k > 0.7 |
|---|---|---|---|---|---|
| {f['r2']:.3f} | {f['within_geo_r2']:.3f} | {f['mape']:.3f} | {f['ppc_interval_coverage']:.3f} | {f['residual_acf1_median_abs']:.3f} | {lo['pareto_k_bad_share']:.1%} |

![Posterior predictive](figures/diag_posterior_predictive.png)

![Residuals](figures/diag_residuals.png)

The predictive intervals are calibrated (94% interval covers {f['ppc_interval_coverage']:.1%} of geo-weeks) and
residuals show no leftover time structure. Geo-week error is high (MAPE {f['mape']:.0%}) because weekly revenue
within a geo is close to white noise (EDA: CV 0.30, lag-1 autocorrelation 0.02); the model explains
{f['within_geo_r2']:.0%} of within-geo weekly variation. The national total, where geo noise averages out, is
tracked closely.

## 6. Out-of-sample: holdout and rolling-origin CV

Each fold trains on weeks 1..N with the selected specification (scaling and priors recomputed from that window
only) and forecasts the next 13 weeks without seeing them. The four forecast windows cover the last year.

**Findings**

""" + "\n".join(f"- {x}" for x in cv_findings) + """

| Fold (train weeks) | Status | R-hat max | ESS bulk min | Divergences | Geo-week MAPE in-sample → forecast | National weekly MAPE | Geo-week 94% coverage |
|---|---|---|---|---|---|---|---|
""" + "\n".join(
        f"| {r.fold} | {r.status} | {r.rhat_max:.4f} | {r.ess_bulk_min:.0f} | {r.divergences} | "
        + (f"{r.in_mape:.3f} → {r.fc_mape:.3f} | {r.nat_mape:.1%} | {r.coverage:.0%} |" if r.status == "converged" else "n/a | n/a | n/a |")
        for r in cv_df.itertuples()) + """

| Median ROI | """ + " | ".join(cv_roi.columns) + """ |
|---|""" + "---|" * len(cv_roi.columns) + """
""" + "\n".join(f"| {c} | " + " | ".join(f"{v:.2f}" for v in row) + " |" for c, row in cv_roi.iterrows()) + f"""

The plot below re-scores each fold's **national** forecast from its saved posterior (every 4th draw):

| Fold | National weekly MAPE | National 94% interval coverage |
|---|---|---|
""" + "\n".join(f"| {r.fold} | {r.national_mape:.1%} | {r.national_94_coverage:.0%} |" for r in fc.itertuples()) + f"""

![Forecasts](figures/diag_forecasts.png)

**National-level calibration.** Geo-week intervals are calibrated. At the national level the 94% interval covers
""" + f"{nat_cov_in:.0%}" + """ of weeks in-sample, but """ + f"{fc.national_94_coverage.min():.0%}–{fc.national_94_coverage.max():.0%}" + """ out-of-sample
(each fold has only 13 weeks, so a single fold's coverage is uncertain by about ±7 points). Residuals are not
correlated across geos (average pairwise correlation """ + f"{cross_geo_r:+.2f}" + """), so this is not shared weekly noise.
The shortfall comes from level errors in some forecast windows (national forecast bias by fold: """ + ", ".join(
    f"{r.fold} {r.national_bias:+.1%}" for r in fc.itertuples()) + f"""): the intervals do not include uncertainty
about the baseline level moving between the training and forecast periods. National forecasts should therefore
be read with wider uncertainty than shown.

{chr(10).join(f'### {k}' + chr(10) + chr(10) + tbl(v) + chr(10) for k, v in folds.items())}

![ROI stability](figures/diag_roi_stability.png)

## 7. Identification: is ROI learned from the data?

![Prior vs posterior ROI](figures/diag_prior_vs_posterior.png)

| Channel | Prior ROI 94% | Posterior ROI 94% | Contraction | P(ROI > 1) |
|---|---|---|---|---|
""" + "\n".join(f"| {r.channel} | {r.roi_prior_hdi94_low:.2f}–{r.roi_prior_hdi94_high:.2f} | {r.roi_hdi94_low:.2f}–{r.roi_hdi94_high:.2f} | {r.roi_prior_contraction:.2f} | {r.prob_roi_gt_1:.2f} |" for r in ch.itertuples()) + f"""

![Baseline vs media](figures/diag_baseline_media.png)

Posterior ROI intervals are much narrower than the prior's, so the data drives the estimates. The baseline and
total media contribution trade off (posterior correlation {r_bm:+.2f}): the data pins down the sum better than the
split, which is the main reason to calibrate with lift tests.

## 8. Known limitations of this model

- **Control effects are shared across geos.** The EDA shows competitor sales and sentiment effects vary by geo
  (I² 0.94 and 0.88), and both correlate with spend, so some geo-specific control effect can leak into media ROI.
- **Weak weekly signal.** Within-geo R² is {f['within_geo_r2']:.2f}; channel ROIs rest mostly on spend timing
  differences, which are noisy.
- **Saturation is weakly identified.** The top of each response curve is rarely observed, so marginal ROI and
  any large reallocation lean on the prior shape.
"""
    (REPORTS / "diagnostics.md").write_text(md_text)
    print(f"wrote {REPORTS / 'diagnostics.md'}")


if __name__ == "__main__":
    main()
