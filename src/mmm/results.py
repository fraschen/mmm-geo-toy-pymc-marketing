"""Assemble the client-facing channel results file from the primary spec + gates.

    python -m mmm.results   ->  outputs/channel_results.csv, outputs/channel_results_metadata.json,
                                outputs/figures/roi_by_spec.png
"""

from __future__ import annotations

import json
from importlib.metadata import version

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from .config import OUTPUTS, load_config  # noqa: E402

SPEC_COLORS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]  # categorical slots 1-4, fixed order


def roi_figure(chans: dict[str, pd.DataFrame], path, excluded: set[str] = frozenset()) -> None:
    channels = next(iter(chans.values()))["channel"].tolist()
    fig, ax = plt.subplots(figsize=(7.5, 5.0), dpi=150)
    n = len(chans)
    for i, (spec, df) in enumerate(chans.items()):
        d = df.set_index("channel").loc[channels]
        y = [k + (i - (n - 1) / 2) * 0.19 for k in range(len(channels))]
        ax.hlines(y, d.roi_hdi94_low, d.roi_hdi94_high, color=SPEC_COLORS[i], lw=2)
        ax.plot(d.roi_median, y, "o", ms=7, color=SPEC_COLORS[i], mec="white", mew=1.5,
                label=f"{spec} (excluded: not converged)" if spec in excluded else spec)
    ax.axvline(1.0, color="#8a8a85", lw=1, ls="--")
    ax.text(1.0, -0.55, " break-even", color="#5f5e5a", fontsize=8, va="bottom")
    ax.set_yticks(range(len(channels)), channels)
    ax.invert_yaxis()
    ax.set_xlabel("ROI (incremental revenue per $1 spend), median and 94% HDI")
    ax.grid(axis="x", color="#e6e5e0", lw=0.8)
    ax.set_axisbelow(True)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.tick_params(axis="y", length=0)
    ax.legend(frameon=False, fontsize=8, loc="lower right", title="specification", title_fontsize=8)
    ax.set_title("Channel ROI by model specification", loc="left", fontsize=11, pad=16)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def main() -> None:
    cfg = load_config()
    primary = cfg["primary_spec"]
    specs_dir = OUTPUTS / "specs"
    chans = {s: pd.read_csv(specs_dir / s / "channel_metrics.csv")
             for s in cfg["specs"] if (specs_dir / s / "channel_metrics.csv").exists()}
    gate = json.loads((OUTPUTS / "gate_report.json").read_text())
    m = json.loads((specs_dir / primary / "metrics.json").read_text())

    res = chans[primary].drop(columns="spec").copy()
    roi = pd.DataFrame({s: df.set_index("channel")["roi_median"] for s, df in chans.items()})
    res["roi_median_min_across_specs"] = res.channel.map(roi.min(axis=1))
    res["roi_median_max_across_specs"] = res.channel.map(roi.max(axis=1))
    folds = [specs_dir / f"{primary}__cv{n}" for n in cfg["data"].get("cv_train_weeks", [])]
    folds.append(specs_dir / f"{primary}__holdout")
    fold_roi = pd.DataFrame({p.name: pd.read_csv(p / "channel_metrics.csv").set_index("channel")["roi_median"]
                             for p in folds if (p / "channel_metrics.csv").exists()})
    if not fold_roi.empty:
        res["roi_median_min_across_cv_folds"] = res.channel.map(fold_roi.min(axis=1))
        res["roi_median_max_across_cv_folds"] = res.channel.map(fold_roi.max(axis=1))
    res["roi_rank"] = res.roi_median.rank(ascending=False).astype(int)

    # per-channel gate status: worst status among checks that name this channel
    order = {"PASS": 0, "WARN": 1, "FAIL": 2}
    checks = [r for rs in gate["sections"].values() for r in rs]
    def channel_status(c):
        named = [r for r in checks if r["check"].endswith(f": {c}")]
        return max((r["status"] for r in named), key=order.get, default="PASS")
    res["channel_gate_status"] = res.channel.map(channel_status)
    res["model_gate_verdict"] = gate["verdict"]
    res["model_spec"] = primary
    res["period_start"] = m["data_checks"]["date_min"]
    res["period_end"] = m["data_checks"]["date_max"]
    res["currency_units"] = "same units as *_spend columns; revenue = conversions x revenue_per_conversion"

    lead = ["channel", "roi_rank", "roi_median", "roi_hdi94_low", "roi_hdi94_high", "prob_roi_gt_1",
            "mroi_median", "mroi_hdi94_low", "mroi_hdi94_high",
            "contribution_median", "contribution_hdi94_low", "contribution_hdi94_high",
            "contribution_share_of_revenue_mean", "spend", "spend_share",
            "channel_gate_status", "model_gate_verdict"]
    res = res[lead + [c for c in res.columns if c not in lead]]
    res.to_csv(OUTPUTS / "channel_results.csv", index=False, float_format="%.6g")

    meta = {
        "model_spec": primary,
        "spec_config": cfg["specs"][primary],
        "gate_verdict": gate["verdict"],
        "gate_counts": {k: gate[k] for k in ("n_pass", "n_warn", "n_fail")},
        "period": [m["data_checks"]["date_min"], m["data_checks"]["date_max"]],
        "n_geos": m["data_checks"]["n_geos"], "n_weeks": m["data_checks"]["n_weeks"],
        "sampler": m["sampler"],
        "fit": m["fit"], "convergence": {k: v for k, v in m["convergence"].items() if not k.endswith("_by_var")},
        "versions": {p: version(p) for p in ("pymc-marketing", "pymc", "pytensor", "arviz", "numpyro", "jax")},
        "column_definitions": {
            "roi_*": "total incremental revenue over the period (zero-spend counterfactual, incl. adstock carryover) / total spend",
            "mroi_*": "incremental revenue from the next 1% of spend / that 1% of spend, at the observed spend pattern",
            "contribution_*": "incremental revenue attributed to the channel over the full period",
            "prob_roi_gt_1": "posterior probability the channel returns more revenue than it costs",
            "*_hdi94_*": "94% highest density interval of the posterior",
            "roi_prior_*": "same quantity under the prior only; compare with posterior to see how much the data moved it",
            "roi_prior_contraction": "1 - posterior sd / prior sd; near 0 = result is mostly prior",
            "roi_median_{min,max}_across_specs": "range of posterior-median ROI over the alternative specifications",
            "roi_median_{min,max}_across_cv_folds": "range of posterior-median ROI over rolling-origin CV fits (training windows ending at weeks 104, 117, 130, 143)",
            "channel_gate_status": "worst automated-gate status among the checks specific to this channel",
            "cost_per_incremental_conversion_median": "spend / median incremental conversions",
        },
    }
    (OUTPUTS / "channel_results_metadata.json").write_text(json.dumps(meta, indent=2, default=float))

    (OUTPUTS / "figures").mkdir(exist_ok=True)
    excluded = {r["check"].split(":")[0] for r in checks if r["status"] == "SKIP"}
    roi_figure(chans, OUTPUTS / "figures" / "roi_by_spec.png", excluded)
    print(res[lead[:8]].round(3).to_string(index=False))


if __name__ == "__main__":
    main()
