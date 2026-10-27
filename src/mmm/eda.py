"""Exploratory data analysis, following the pymc-labs `mmm-modeling` skill's EDA checklist.

    python -m mmm.eda   ->  outputs/eda/eda_summary.json + figures

Each section answers a question that bears on the model specification or priors:
data sufficiency, target trend/seasonality, spend mix, channel-target and channel-channel
correlation (identification), carryover (lagged correlation), saturation range, geo
heterogeneity (pooling / scaling) and controls.
"""

from __future__ import annotations

import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from statsmodels.stats.outliers_influence import variance_inflation_factor  # noqa: E402

from . import data  # noqa: E402
from .config import OUTPUTS, ROOT, load_config  # noqa: E402

OUT = OUTPUTS / "eda"
CH_COLORS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"]  # categorical slots 1-5
INK, MUTED, GRID = "#1f1f1e", "#5f5e5a", "#e6e5e0"


def _style(ax):
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.grid(axis="y", color=GRID, lw=0.8)
    ax.set_axisbelow(True)


def _demean(df: pd.DataFrame, cols, geo) -> pd.DataFrame:
    return df[cols] - df.groupby(geo)[cols].transform("mean")


def main() -> None:
    cfg = load_config()
    md, checks = data.load(cfg)
    raw = pd.read_csv(ROOT / cfg["data"]["path"], index_col=0)
    df, geo, date, y = md.df, md.geo_column, md.date_column, md.target_column
    ch = md.channel_columns
    df = df.assign(population=raw.set_index([raw[date].map(pd.Timestamp), raw[geo]])["population"]
                   .reindex(pd.MultiIndex.from_frame(df[[date, geo]])).to_numpy())
    OUT.mkdir(parents=True, exist_ok=True)
    S: dict = {}

    # 1. data sufficiency (skill: weekly >= ~100, recommended 150+ per geo)
    S["data"] = {"n_geos": checks["n_geos"], "n_weeks_per_geo": checks["n_weeks"],
                 "meets_recommended_150_weeks": checks["n_weeks"] >= 150,
                 "balanced_panel": checks["balanced_panel"], "missing_values": checks["n_missing_values"]}

    # 2. target over time: trend and yearly seasonality strength (national)
    nat = df.groupby(date)[[y, *ch]].sum()
    t = np.arange(len(nat))
    slope, icpt = np.polyfit(t, nat[y], 1)
    detr = nat[y] - (icpt + slope * t)
    woy = nat.index.isocalendar().week.to_numpy()
    seas = detr.groupby(woy).transform("mean")
    acf = lambda x, k: float(pd.Series(x).autocorr(k))  # noqa: E731
    S["target"] = {
        "national_trend_pct_over_period": float(slope * (len(t) - 1) / (icpt + slope * len(t) / 2) * 100),
        "national_cv": float(nat[y].std() / nat[y].mean()),
        "national_acf_lag1": acf(nat[y], 1), "national_acf_lag52": acf(nat[y], 52),
        "share_of_detrended_national_variance_explained_by_week_of_year": float(seas.var() / detr.var()),
        "within_geo_cv_median": float((df.groupby(geo)[y].std() / df.groupby(geo)[y].mean()).median()),
        "within_geo_acf_lag1_median": float(df.groupby(geo)[y].apply(lambda s: s.autocorr(1)).median()),
    }

    # 3. spend mix and variation
    tot = df[ch].sum()
    S["spend"] = {
        "share": (tot / tot.sum()).round(4).to_dict(),
        "zero_spend_share_geo_weeks": {c: float((df[c] == 0).mean()) for c in ch},
        "national_weekly_cv": (nat[ch].std() / nat[ch].mean()).round(3).to_dict(),
        "within_geo_cv_median": {c: float((df.groupby(geo)[c].std() / df.groupby(geo)[c].mean()).median()) for c in ch},
        # how much of the spend range the data covers, relative to each geo's max (saturation identifiability)
        "geo_week_spend_over_geo_max_p10_p50_p90": {
            c: [float(v) for v in (df[c] / df.groupby(geo)[c].transform("max")).quantile([.1, .5, .9])] for c in ch},
    }

    # 4. channel-target correlation: national and within-geo (identification signal)
    dm = _demean(df, [y, *ch], geo)
    S["channel_target_corr"] = {
        "national": {c: float(nat[c].corr(nat[y])) for c in ch},
        "within_geo": {c: float(dm[c].corr(dm[y])) for c in ch},
        "between_geo_totals": {c: float(df.groupby(geo)[c].sum().corr(df.groupby(geo)[y].sum())) for c in ch},
    }

    # 5. carryover: within-geo correlation of target with spend lagged 0..8 weeks
    lags = range(0, 9)
    lagc = {}
    for c in ch:
        sh = df.sort_values([geo, date]).copy()
        res = []
        for k in lags:
            sh["lag"] = sh.groupby(geo)[c].shift(k)
            sub = sh.dropna(subset=["lag"])
            a = sub["lag"] - sub.groupby(geo)["lag"].transform("mean")
            b = sub[y] - sub.groupby(geo)[y].transform("mean")
            res.append(float(np.corrcoef(a, b)[0, 1]))
        lagc[c] = res
    S["lagged_within_geo_corr"] = {c: [round(v, 4) for v in r] for c, r in lagc.items()}

    # 6. channel-channel correlation and VIF (national and within-geo)
    S["channel_channel_corr"] = {"national": nat[ch].corr().round(3).to_dict(),
                                 "within_geo": dm[ch].corr().round(3).to_dict()}
    Xn = (nat[ch] - nat[ch].mean()) / nat[ch].std()
    S["vif_national"] = {c: float(variance_inflation_factor(Xn.values, i)) for i, c in enumerate(ch)}
    S["vif_within_geo"] = {c: float(variance_inflation_factor(dm[ch].values, i)) for i, c in enumerate(ch)}

    # 7. geo heterogeneity: size, spend intensity, spend mix (pooling / scaling choices)
    g = df.groupby(geo).agg(rev=(y, "sum"), pop=("population", "first"), **{c: (c, "sum") for c in ch})
    g["spend"] = g[ch].sum(axis=1)
    S["geo"] = {
        "revenue_max_over_min": float(g.rev.max() / g.rev.min()),
        "corr_revenue_population": float(g.rev.corr(g["pop"])),
        "corr_spend_population": float(g.spend.corr(g["pop"])),
        "revenue_per_capita_cv": float((g.rev / g["pop"]).std() / (g.rev / g["pop"]).mean()),
        "spend_per_capita_cv": float((g.spend / g["pop"]).std() / (g.spend / g["pop"]).mean()),
        "spend_to_revenue_cv_across_geos": float((g.spend / g.rev).std() / (g.spend / g.rev).mean()),
        "channel_share_cv_across_geos": {c: float((g[c] / g.spend).std() / (g[c] / g.spend).mean()) for c in ch},
        # does spend timing differ across geos? mean pairwise corr of each channel's weekly series between geos
        "cross_geo_timing_corr_mean": {
            c: float(np.nanmean(np.corrcoef(df.pivot(index=date, columns=geo, values=c).T.values)[np.triu_indices(len(g), 1)]))
            for c in ch},
    }

    # 8. controls
    ctrl = md.control_columns
    S["controls"] = {
        "within_geo_corr_with_target": {c: float(_demean(df, [c, y], geo).corr().iloc[0, 1]) for c in ctrl},
        "national_corr_with_target": {c: float(df.groupby(date)[c].mean().corr(nat[y])) for c in ctrl},
        "promo_zero_share": float((raw["Promo"] == 0).mean()),
        "max_abs_corr_with_channels_within_geo": {
            c: float(_demean(df, [c, *ch], geo).corr().loc[c, ch].abs().max()) for c in ctrl},
    }

    (OUT / "eda_summary.json").write_text(json.dumps(S, indent=2))

    # ---- figures
    fig, axes = plt.subplots(2, 1, figsize=(9, 6), sharex=True, dpi=150)
    axes[0].plot(nat.index, nat[y] / 1e6, color=INK, lw=1.5)
    axes[0].plot(nat.index, (icpt + slope * t) / 1e6, color=MUTED, lw=1, ls="--")
    axes[0].set_ylabel("Revenue (M)")
    axes[0].set_title("National revenue and spend by channel", loc="left", fontsize=11)
    for i, c in enumerate(ch):
        axes[1].plot(nat.index, nat[c] / 1e6, color=CH_COLORS[i], lw=1.5, label=c)
    axes[1].set_ylabel("Spend (M)")
    axes[1].legend(frameon=False, fontsize=8, ncol=5, loc="upper left")
    for ax in axes:
        _style(ax)
    fig.tight_layout()
    fig.savefig(OUT / "national_revenue_and_spend.png")
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(9, 3.8), dpi=150)
    for ax, (name, m) in zip(axes, [("National weekly totals", nat[ch].corr()), ("Within geo (demeaned)", dm[ch].corr())]):
        im = ax.imshow(m.values, cmap="RdBu_r", vmin=-1, vmax=1)
        ax.set_xticks(range(len(ch)), [c.replace("Channel", "Ch") for c in ch])
        ax.set_yticks(range(len(ch)), [c.replace("Channel", "Ch") for c in ch])
        for i in range(len(ch)):
            for j in range(len(ch)):
                ax.text(j, i, f"{m.values[i, j]:.2f}", ha="center", va="center", fontsize=8,
                        color="white" if abs(m.values[i, j]) > 0.6 else INK)
        ax.set_title(name, loc="left", fontsize=10)
    fig.suptitle("Channel spend correlation", x=0.02, ha="left", fontsize=11)
    fig.colorbar(im, ax=axes, shrink=0.8)
    fig.savefig(OUT / "channel_correlation.png", bbox_inches="tight")
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(8, 4), dpi=150)
    for i, c in enumerate(ch):
        ax.plot(list(lags), lagc[c], marker="o", ms=4, lw=1.5, color=CH_COLORS[i], label=c)
    ax.axhline(0, color=MUTED, lw=0.8)
    ax.set_xlabel("Lag of spend (weeks)")
    ax.set_ylabel("Correlation with revenue")
    ax.set_title("Within-geo correlation of revenue with lagged spend", loc="left", fontsize=11)
    ax.legend(frameon=False, fontsize=8, ncol=5)
    _style(ax)
    fig.tight_layout()
    fig.savefig(OUT / "lagged_correlation.png")
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(9, 3.6), dpi=150)
    axes[0].scatter(g["pop"] / 1e3, g.rev / 1e6, s=18, color=CH_COLORS[0])
    axes[0].set(xlabel="Population (k)", ylabel="Total revenue (M)")
    axes[0].set_title("Revenue scales with population", loc="left", fontsize=10)
    axes[1].scatter(g["pop"] / 1e3, g.spend / 1e6, s=18, color=CH_COLORS[1])
    axes[1].set(xlabel="Population (k)", ylabel="Total spend (M)")
    axes[1].set_title("So does spend", loc="left", fontsize=10)
    for ax in axes:
        _style(ax)
    fig.tight_layout()
    fig.savefig(OUT / "geo_size.png")
    plt.close(fig)

    print(json.dumps(S, indent=1)[:200], "...")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
