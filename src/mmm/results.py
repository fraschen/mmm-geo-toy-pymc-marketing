"""Assemble the client-facing channel results file from the primary spec + gates.

    python -m mmm.results   ->  outputs/channel_results.csv, outputs/channel_results_metadata.json,
                                outputs/figures/roi.png
"""

from __future__ import annotations

import json
from importlib.metadata import version

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from .config import OUTPUTS, load_config  # noqa: E402

ROI_COLOR = "#2a78d6"  # categorical slot 1


def roi_figure(ch: pd.DataFrame, spec: str, path) -> None:
    d = ch.set_index("channel")
    channels = d.index.tolist()
    y = range(len(channels))
    fig, ax = plt.subplots(figsize=(7.5, 3.8), dpi=150)
    ax.hlines(y, d.roi_hdi94_low, d.roi_hdi94_high, color=ROI_COLOR, lw=2)
    ax.plot(d.roi_median, y, "o", ms=7, color=ROI_COLOR, mec="white", mew=1.5)
    ax.axvline(1.0, color="#8a8a85", lw=1, ls="--")
    ax.text(1.0, -0.6, " break-even", color="#5f5e5a", fontsize=8, va="bottom")
    ax.set_yticks(list(y), channels)
    ax.invert_yaxis()
    ax.set_xlabel("ROI (incremental revenue per $1 spend), median and 94% HDI")
    ax.grid(axis="x", color="#e6e5e0", lw=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.tick_params(axis="y", length=0)
    ax.set_title(f"Channel ROI ({spec})", loc="left", fontsize=11, pad=16)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def main() -> None:
    cfg = load_config()
    primary = cfg["primary_spec"]
    specs_dir = OUTPUTS / "specs"
    ch = pd.read_csv(specs_dir / primary / "channel_metrics.csv")
    gate = json.loads((OUTPUTS / "gate_report.json").read_text())
    m = json.loads((specs_dir / primary / "metrics.json").read_text())

    res = ch.drop(columns="spec").copy()
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
            "roi_median_{min,max}_across_cv_folds": "range of posterior-median ROI over rolling-origin CV fits (training windows ending at weeks 104, 117, 130, 143)",
            "channel_gate_status": "worst automated-gate status among the checks specific to this channel",
            "cost_per_incremental_conversion_median": "derived from revenue, not separately modeled: spend / (median incremental revenue / revenue_per_conversion) = revenue_per_conversion / ROI, because revenue per conversion is constant",
        },
    }
    (OUTPUTS / "channel_results_metadata.json").write_text(json.dumps(meta, indent=2, default=float))

    (OUTPUTS / "figures").mkdir(exist_ok=True)
    roi_figure(ch, primary, OUTPUTS / "figures" / "roi.png")
    print(res[lead[:8]].round(3).to_string(index=False))


if __name__ == "__main__":
    main()
