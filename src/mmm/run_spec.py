"""Fit one model specification and write its diagnostics + channel metrics.

    python -m mmm.run_spec --spec pooled             # full-data fit
    python -m mmm.run_spec --spec pooled --holdout   # fit on all but last N weeks, score the holdout
    python -m mmm.run_spec --spec pooled --train-weeks 104   # CV fold: fit weeks 1-104, score the next N

Writes outputs/specs/<run>/metrics.json, channel_metrics.csv and figures;
the fitted model goes to artifacts/<run>/ (git-ignored, regenerable).
"""

from __future__ import annotations

import os

# one XLA host device per chain so numpyro samples chains in parallel
os.environ.setdefault("XLA_FLAGS", "--xla_force_host_platform_device_count=4")

import argparse
import json
import time
import warnings

import arviz as az
import numpy as np
import pandas as pd
import pymc as pm
import xarray as xr

from . import data, model
from .config import ARTIFACTS, OUTPUTS, load_config

HDI = 0.94
warnings.filterwarnings("ignore", category=FutureWarning)


def _hdi(samples: np.ndarray, prob: float = HDI) -> tuple[float, float]:
    lo, hi = az.hdi(np.asarray(samples).ravel(), prob=prob)
    return float(lo), float(hi)


def _scale_target(mmm, arr: xr.DataArray) -> xr.DataArray:
    """Scaled-space target quantity -> revenue."""
    return arr * mmm.scalers._target


# --------------------------------------------------------------------------- checks


def prior_checks(mmm, md: data.ModelData, n: int, seed: int) -> dict:
    """Per-geo prior predictive coverage + prior-implied ROI (on the scaled scale)."""
    prior = mmm.sample_prior_predictive(md.X, samples=n, random_seed=seed)
    ypp = mmm.idata.prior_predictive["y"]  # scaled (date, geo)
    y_scaled = mmm.xarray_dataset._target / mmm.scalers._target
    lo = ypp.quantile((1 - HDI) / 2, dim=("chain", "draw"))
    hi = ypp.quantile((1 + HDI) / 2, dim=("chain", "draw"))
    inside = ((y_scaled >= lo) & (y_scaled <= hi)).mean().item()

    # prior ROI: sum of prior channel contributions (original scale) / spend
    contrib = _scale_target(mmm, mmm.idata.prior["channel_contribution"]).sum(("date", md.geo_column))
    spend = md.df[md.channel_columns].sum()
    roi_prior = {c: (contrib.sel(channel=c) / spend[c]).values.ravel() for c in md.channel_columns}
    return {
        "prior_predictive_coverage": float(inside),
        "prior_predictive_interval_width_scaled": float((hi - lo).mean()),
        "roi_prior": roi_prior,
    }


def convergence(idata) -> dict:
    post = idata.posterior
    rhat = az.rhat(post)
    ess_b = az.ess(post, method="bulk")
    ess_t = az.ess(post, method="tail")
    flat = lambda ds: np.concatenate([np.atleast_1d(ds[v].values).ravel() for v in ds.data_vars])  # noqa: E731
    worst = lambda ds, f: {v: float(f(ds[v].values)) for v in ds.data_vars}  # noqa: E731
    div = idata.sample_stats["diverging"]
    # E-BFMI per chain (Betancourt 2016), computed directly from the energy trace
    energy = idata.sample_stats["energy"].transpose("chain", "draw").values
    bfmi = (np.diff(energy, axis=1) ** 2).mean(axis=1) / energy.var(axis=1)
    return {
        "rhat_max": float(np.nanmax(flat(rhat))),
        "ess_bulk_min": float(np.nanmin(flat(ess_b))),
        "ess_tail_min": float(np.nanmin(flat(ess_t))),
        "divergences": int(div.sum()),
        "divergence_rate": float(div.mean()),
        "bfmi_min": float(np.min(bfmi)),
        "n_draws_total": int(div.size),
        "rhat_by_var": worst(rhat, np.nanmax),
        "ess_bulk_by_var": worst(ess_b, np.nanmin),
    }


def convergence_failures(c: dict, g: dict) -> list[str]:
    """Blocking convergence checks (same thresholds as the gates). Empty list = converged."""
    fails = []
    if c["rhat_max"] > g["rhat_max"]:
        fails.append(f"R-hat max {c['rhat_max']:.4f} > {g['rhat_max']}")
    if c["ess_bulk_min"] < g["ess_bulk_min"]:
        fails.append(f"ESS bulk min {c['ess_bulk_min']:.0f} < {g['ess_bulk_min']}")
    if c["ess_tail_min"] < g["ess_tail_min"]:
        fails.append(f"ESS tail min {c['ess_tail_min']:.0f} < {g['ess_tail_min']}")
    if c["divergences"] > g["divergences_max"]:
        fails.append(f"{c['divergences']} divergences > {g['divergences_max']}")
    if c["bfmi_min"] < g["bfmi_min"]:
        fails.append(f"E-BFMI min {c['bfmi_min']:.3f} < {g['bfmi_min']}")
    return fails


def save_posterior(mmm, path) -> None:
    # Keep parameter draws, sampler stats and non-time quantities (a few MB). The
    # posterior also holds per-date deterministics (mu, contributions: ~4 GB) and
    # predictive draws; all are regenerable from the parameters with the code.
    groups = {}
    for g in ("posterior", "sample_stats", "prior"):
        if g in mmm.idata.children:
            ds = mmm.idata[g].to_dataset()
            groups[g] = ds[[v for v in ds.data_vars if g == "sample_stats" or "date" not in ds[v].dims]]
    xr.DataTree.from_dict(groups).to_netcdf(path)


def fit_quality(mmm, md: data.ModelData, ypp_scaled: xr.DataArray) -> tuple[dict, pd.DataFrame]:
    """In-sample posterior predictive fit (original scale)."""
    geo = md.geo_column
    ypp = _scale_target(mmm, ypp_scaled)
    y = mmm.xarray_dataset._target
    pred = ypp.mean(("chain", "draw"))
    lo = ypp.quantile((1 - HDI) / 2, dim=("chain", "draw"))
    hi = ypp.quantile((1 + HDI) / 2, dim=("chain", "draw"))
    resid = (y - pred).transpose("date", geo)

    ss_res = float((resid**2).sum())
    r2 = 1 - ss_res / float(((y - y.mean()) ** 2).sum())
    within = 1 - ss_res / float(((y - y.mean("date")) ** 2).sum())
    acf1 = [float(np.corrcoef(r[:-1], r[1:])[0, 1]) for r in resid.values.T]

    per_geo = pd.DataFrame({
        "geo": resid[geo].values,
        "mape": (np.abs(resid) / y).mean("date").values,
        "residual_acf1": acf1,
    })
    return {
        "r2": r2,
        "within_geo_r2": within,
        "mape": float((np.abs(resid) / y).mean()),
        "ppc_interval_coverage": float(((y >= lo) & (y <= hi)).mean()),
        "residual_acf1_median_abs": float(np.median(np.abs(acf1))),
    }, per_geo


def loo(mmm, idata) -> dict:
    with mmm.model:
        pm.compute_log_likelihood(idata, extend_inferencedata=True, progressbar=False)
    res = az.loo(idata, pointwise=True)
    k = np.asarray(res.pareto_k).ravel()
    return {"elpd_loo": float(res.elpd), "elpd_loo_se": float(res.se), "pareto_k_bad_share": float((k > 0.7).mean())}


def channel_metrics(mmm, md: data.ModelData, roi_prior: dict, n_samples: int, seed: int) -> pd.DataFrame:
    geo = md.geo_column
    inc = mmm.incrementality
    contrib = inc.compute_incremental_contribution(
        frequency="all_time", num_samples=n_samples, random_state=seed
    ).sum(geo).squeeze(drop=True)
    plus1 = inc.compute_incremental_contribution(
        frequency="all_time", num_samples=n_samples, random_state=seed, counterfactual_spend_factor=1.01
    ).sum(geo).squeeze(drop=True)
    spend = md.df[md.channel_columns].sum()
    total_revenue = float(md.y.sum())
    post = mmm.idata.posterior

    rows = []
    for c in md.channel_columns:
        x = contrib.sel(channel=c).values.ravel()
        roi = x / spend[c]
        # counterfactual at 1.01x spend returns the revenue gained from +1% spend
        m = plus1.sel(channel=c).values.ravel() / (0.01 * spend[c])
        alpha = post["adstock_alpha"].sel(channel=c).values.ravel()
        lam = post["saturation_lam"].sel(channel=c).values.ravel()
        rp = roi_prior[c]
        rows.append({
            "channel": c,
            "spend": float(spend[c]),
            "spend_share": float(spend[c] / spend.sum()),
            "contribution_mean": float(x.mean()),
            "contribution_median": float(np.median(x)),
            "contribution_hdi94_low": _hdi(x)[0],
            "contribution_hdi94_high": _hdi(x)[1],
            "contribution_share_of_revenue_mean": float(x.mean() / total_revenue),
            "contribution_share_of_revenue_hdi94_low": _hdi(x)[0] / total_revenue,
            "contribution_share_of_revenue_hdi94_high": _hdi(x)[1] / total_revenue,
            "roi_mean": float(roi.mean()),
            "roi_median": float(np.median(roi)),
            "roi_sd": float(roi.std()),
            "roi_hdi94_low": _hdi(roi)[0],
            "roi_hdi94_high": _hdi(roi)[1],
            "roi_hdi80_low": _hdi(roi, 0.8)[0],
            "roi_hdi80_high": _hdi(roi, 0.8)[1],
            "prob_roi_gt_1": float((roi > 1).mean()),
            "mroi_median": float(np.median(m)),
            "mroi_hdi94_low": _hdi(m)[0],
            "mroi_hdi94_high": _hdi(m)[1],
            "cost_per_incremental_conversion_median": float(spend[c] / (np.median(x) / md.revenue_per_kpi)),
            "roi_prior_median": float(np.median(rp)),
            "roi_prior_hdi94_low": _hdi(rp)[0],
            "roi_prior_hdi94_high": _hdi(rp)[1],
            "roi_prior_contraction": float(1 - roi.std() / rp.std()),
            "adstock_alpha_median": float(np.median(alpha)),
            "adstock_half_life_weeks_median": float(np.median(np.log(0.5) / np.log(alpha))),
            "saturation_lam_median": float(np.median(lam)),
        })
    return pd.DataFrame(rows)


def holdout_scores(mmm, test: data.ModelData, seed: int) -> dict:
    geo = test.geo_column
    ypp = mmm.sample_posterior_predictive(
        test.X, include_last_observations=True, extend_idata=False, combined=False,
        random_seed=seed, progressbar=False, var_names=["y"],
    )
    ypp = ypp["y"] if isinstance(ypp, xr.Dataset) else ypp
    ypp = _scale_target(mmm, ypp)
    y = test.df.set_index([test.date_column, geo])[test.target_column].to_xarray().rename({test.date_column: "date"})
    y = y.sel(date=ypp["date"], **{geo: ypp[geo]})
    sample_dims = [d for d in ("chain", "draw", "sample") if d in ypp.dims]
    pred = ypp.mean(sample_dims)
    lo = ypp.quantile((1 - HDI) / 2, dim=sample_dims)
    hi = ypp.quantile((1 + HDI) / 2, dim=sample_dims)
    tot_pred, tot_y = pred.sum(geo), y.sum(geo)
    return {
        "holdout_weeks": int(y.sizes["date"]),
        "holdout_mape": float((np.abs(y - pred) / y).mean()),
        "holdout_r2": float(1 - ((y - pred) ** 2).sum() / ((y - y.mean()) ** 2).sum()),
        "holdout_national_mape": float((np.abs(tot_y - tot_pred) / tot_y).mean()),
        "holdout_interval_coverage": float(((y >= lo) & (y <= hi)).mean()),
    }


# --------------------------------------------------------------------------- main


def main(argv=None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", required=True)
    ap.add_argument("--holdout", action="store_true")
    ap.add_argument("--train-weeks", type=int, help="time-slice CV fold: train on the first N weeks")
    ap.add_argument("--quick", action="store_true", help="tiny sampler run for smoke tests")
    args = ap.parse_args(argv)

    cfg = load_config()
    spec = cfg["specs"][args.spec]
    s = dict(cfg["sampler"])
    if args.quick:
        s.update(chains=2, tune=100, draws=100)
    seed = s.pop("random_seed")
    run = (args.spec + ("__holdout" if args.holdout else "")
           + (f"__cv{args.train_weeks}" if args.train_weeks else "") + ("__quick" if args.quick else ""))
    out, art = OUTPUTS / "specs" / run, ARTIFACTS / run
    out.mkdir(parents=True, exist_ok=True)
    art.mkdir(parents=True, exist_ok=True)

    md, data_checks = data.load(cfg)
    test = None
    if args.holdout or args.train_weeks:
        md, test = md.split(cfg["data"]["holdout_weeks"], train_weeks=args.train_weeks)

    t0 = time.time()
    mmm = model.build(md, spec)
    pri = prior_checks(mmm, md, n=500, seed=seed)
    print(f"[{run}] prior predictive coverage {pri['prior_predictive_coverage']:.2%}")

    mmm.fit(md.X, md.y, random_seed=seed, progressbar=False, **s)
    t_fit = time.time() - t0
    print(f"[{run}] sampled in {t_fit / 60:.1f} min")

    metrics = {
        "run": run, "spec": args.spec, "holdout": args.holdout, "train_weeks": args.train_weeks, "spec_config": spec, "sampler": s,
        "data_checks": data_checks,
        "n_obs_fit": int(len(md.df)),
        "fit_minutes": round(t_fit / 60, 2),
        "prior_predictive_coverage": pri["prior_predictive_coverage"],
        "convergence": convergence(mmm.idata),
    }

    # A fit that fails its convergence checks has not produced valid estimates: record why and stop.
    # No fit metrics, ROI or channel results are computed for it, so none can be reported.
    fails = convergence_failures(metrics["convergence"], cfg["gates"])
    metrics["status"] = "not_converged" if fails else "converged"
    metrics["convergence_failures"] = fails
    if fails:
        with open(out / "metrics.json", "w") as f:
            json.dump(metrics, f, indent=2, default=float)
        save_posterior(mmm, art / "posterior.nc")  # kept for diagnosing the sampler, not for results
        print(f"[{run}] NOT CONVERGED ({'; '.join(fails)}); stopping without results -> {out}")
        return

    ypp = mmm.sample_posterior_predictive(md.X, extend_idata=True, combined=False, random_seed=seed, progressbar=False)
    ypp = ypp["y"] if isinstance(ypp, xr.Dataset) else ypp
    fq, per_geo = fit_quality(mmm, md, ypp)
    metrics["fit"] = fq
    per_geo.to_csv(out / "per_geo_fit.csv", index=False)
    metrics["loo"] = loo(mmm, mmm.idata)

    if test is not None:
        metrics["holdout_scores"] = holdout_scores(mmm, test, seed)
        print(f"[{run}] holdout {metrics['holdout_scores']}")

    ch = channel_metrics(mmm, md, pri["roi_prior"], n_samples=1000, seed=seed)
    ch.insert(0, "spec", args.spec)
    ch.to_csv(out / "channel_metrics.csv", index=False)

    with open(out / "metrics.json", "w") as f:
        json.dump(metrics, f, indent=2, default=float)
    save_posterior(mmm, art / "posterior.nc")
    print(f"[{run}] done in {(time.time() - t0) / 60:.1f} min -> {out}")
    print(ch[["channel", "roi_median", "roi_hdi94_low", "roi_hdi94_high", "mroi_median", "roi_prior_contraction"]].round(2).to_string(index=False))


if __name__ == "__main__":
    main()
