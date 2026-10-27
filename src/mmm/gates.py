"""Automated acceptance gates: decide whether the fit is client-ready without looking at plots.

    python -m mmm.gates            # reads outputs/specs/*/metrics.json, writes outputs/gate_report.{json,md}

Every check is PASS / WARN / FAIL. Exit code is 1 if any blocking check FAILs,
so CI can refuse to publish results.
"""

from __future__ import annotations

import json
import sys
from itertools import combinations

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from .config import OUTPUTS, load_config


def _check(name, value, ok, *, warn=False, blocking=True, threshold=None, detail=""):
    status = "PASS" if ok else ("WARN" if warn or not blocking else "FAIL")
    return {"check": name, "status": status, "value": value, "threshold": threshold,
            "blocking": blocking and not warn, "detail": detail}


def spec_checks(m: dict, ch: pd.DataFrame, g: dict) -> list[dict]:
    d, c, f, lo = m["data_checks"], m["convergence"], m["fit"], m["loo"]
    out = [
        _check("data: required columns present", d["missing_columns"], not d["missing_columns"]),
        _check("data: balanced weekly panel, no missing values",
               {k: d[k] for k in ("balanced_panel", "weekly_contiguous", "n_missing_values")},
               d["balanced_panel"] and d["weekly_contiguous"] and d["n_missing_values"] == 0),
        _check("data: no negative spend or KPI", d["negative_spend_cells"] + d["negative_kpi_cells"],
               d["negative_spend_cells"] + d["negative_kpi_cells"] == 0),
        _check("prior predictive coverage", round(m["prior_predictive_coverage"], 3),
               g["prior_predictive_coverage_min"] <= m["prior_predictive_coverage"] <= g["prior_predictive_coverage_max"],
               threshold=[g["prior_predictive_coverage_min"], g["prior_predictive_coverage_max"]]),
        _check("R-hat max", round(c["rhat_max"], 4), c["rhat_max"] <= g["rhat_max"], threshold=g["rhat_max"]),
        _check("ESS bulk min", round(c["ess_bulk_min"]), c["ess_bulk_min"] >= g["ess_bulk_min"], threshold=g["ess_bulk_min"]),
        _check("ESS tail min", round(c["ess_tail_min"]), c["ess_tail_min"] >= g["ess_tail_min"], threshold=g["ess_tail_min"]),
        _check("divergences", c["divergences"], c["divergences"] <= g["divergences_max"], threshold=g["divergences_max"]),
        _check("E-BFMI min", round(c["bfmi_min"], 3), c["bfmi_min"] >= g["bfmi_min"], threshold=g["bfmi_min"]),
        _check("in-sample R2", round(f["r2"], 4), f["r2"] >= g["in_sample_r2_min"], threshold=g["in_sample_r2_min"]),
        _check("within-geo R2 (signal strength)", round(f["within_geo_r2"], 4), f["within_geo_r2"] >= g["within_geo_r2_min"],
               threshold=g["within_geo_r2_min"], warn=True,
               detail="share of week-to-week variance within a geo the model explains; low = weak media signal"),
        _check("94% PPC interval coverage", round(f["ppc_interval_coverage"], 3),
               g["ppc_interval_coverage_min"] <= f["ppc_interval_coverage"] <= g["ppc_interval_coverage_max"],
               threshold=[g["ppc_interval_coverage_min"], g["ppc_interval_coverage_max"]]),
        _check("residual lag-1 autocorrelation (median |acf1| across geos)", round(f["residual_acf1_median_abs"], 3),
               f["residual_acf1_median_abs"] <= g["residual_acf1_max"], threshold=g["residual_acf1_max"], warn=True),
        _check("PSIS-LOO Pareto k > 0.7 share", round(lo["pareto_k_bad_share"], 4),
               lo["pareto_k_bad_share"] <= g["pareto_k_bad_share_max"], threshold=g["pareto_k_bad_share_max"], warn=True),
    ]
    for _, r in ch.iterrows():
        out.append(_check(f"ROI identified by data, not prior: {r.channel}", round(r.roi_prior_contraction, 3),
                          r.roi_prior_contraction >= g["roi_prior_contraction_min"],
                          threshold=g["roi_prior_contraction_min"], warn=True,
                          detail="1 - posterior sd / prior sd of ROI"))
        p = r.prob_roi_gt_1
        decided = p >= g["roi_breakeven_prob"] or p <= 1 - g["roi_breakeven_prob"]
        out.append(_check(f"ROI clearly above or below break-even: {r.channel}", round(p, 3), decided,
                          threshold=[round(1 - g["roi_breakeven_prob"], 3), g["roi_breakeven_prob"]], warn=True,
                          detail="P(ROI > 1); in between = cannot say whether the channel pays back"))
    return out


def holdout_checks(m: dict, g: dict) -> list[dict]:
    h, f = m["holdout_scores"], m["fit"]
    ratio = h["holdout_mape"] / f["mape"]
    return [
        _check("holdout geo-week MAPE vs in-sample (no degradation)", round(ratio, 3),
               ratio <= g["holdout_mape_degradation_max"], threshold=g["holdout_mape_degradation_max"],
               detail=f"holdout {h['holdout_mape']:.3f} vs in-sample {f['mape']:.3f}"),
        _check("holdout national weekly MAPE", round(h["holdout_national_mape"], 4),
               h["holdout_national_mape"] <= g["holdout_national_mape_max"], threshold=g["holdout_national_mape_max"]),
        _check("holdout 94% interval coverage", round(h["holdout_interval_coverage"], 3),
               h["holdout_interval_coverage"] >= g["holdout_interval_coverage_min"],
               threshold=g["holdout_interval_coverage_min"]),
        _check("holdout fit converged (R-hat)", round(m["convergence"]["rhat_max"], 4),
               m["convergence"]["rhat_max"] <= g["rhat_max"], threshold=g["rhat_max"]),
    ]


def cv_checks(folds: dict[str, dict], full_ch: pd.DataFrame, fold_ch: dict[str, pd.DataFrame], g: dict) -> list[dict]:
    """Rolling-origin CV: every fold must forecast as well as the holdout, and ROI must be stable over time."""
    out = []
    for name, m in folds.items():
        for r in holdout_checks(m, g):
            r["check"] = f"{name}: {r['check'].replace('holdout ', '')}"
            out.append(r)
    roi = pd.DataFrame({"full": full_ch.set_index("channel")["roi_median"],
                        **{k: v.set_index("channel")["roi_median"] for k, v in fold_ch.items()}})
    for c, row in roi.iterrows():
        ratio = float(row.max() / max(row.min(), 1e-9))
        conflict = ratio > g["cv_roi_ratio_fail"]
        out.append(_check(f"ROI stable across CV folds: {c}", round(ratio, 2), ratio <= g["cv_roi_ratio_warn"],
                          warn=not conflict, threshold=[g["cv_roi_ratio_warn"], g["cv_roi_ratio_fail"]],
                          detail=", ".join(f"{k}={v:.2f}" for k, v in row.items())))
    return out


def cross_spec_checks(chans: dict[str, pd.DataFrame], g: dict) -> list[dict]:
    """Robustness: reasonable alternative specifications must agree on ROI."""
    roi = pd.DataFrame({s: df.set_index("channel")["roi_median"] for s, df in chans.items()})
    out = []
    for c, row in roi.iterrows():
        ratio = float(row.max() / max(row.min(), 1e-9))
        status_ok = ratio <= g["cross_spec_roi_ratio_warn"]
        conflict = ratio > g["cross_spec_roi_ratio_fail"]
        out.append(_check(f"ROI stable across specs: {c}", round(ratio, 2), status_ok,
                          warn=not conflict, threshold=[g["cross_spec_roi_ratio_warn"], g["cross_spec_roi_ratio_fail"]],
                          detail=", ".join(f"{s}={v:.2f}" for s, v in row.items())))
    for a, b in combinations(roi.columns, 2):
        rho = float(spearmanr(roi[a], roi[b]).statistic)
        out.append(_check(f"ROI ranking agrees: {a} vs {b}", round(rho, 2), rho >= g["cross_spec_rank_agreement_min"],
                          threshold=g["cross_spec_rank_agreement_min"], warn=True))
    return out


def main() -> int:
    cfg = load_config()
    g = cfg["gates"]
    primary = cfg["primary_spec"]
    specs_dir = OUTPUTS / "specs"

    sections, chans = {}, {}
    for s in sorted(cfg["specs"], key=lambda k: k != primary):  # primary first
        p = specs_dir / s
        if not (p / "metrics.json").exists():
            sections[s] = [_check("fit exists", None, False, detail=f"run `make fit SPEC={s}`")]
            continue
        m = json.loads((p / "metrics.json").read_text())
        chans[s] = pd.read_csv(p / "channel_metrics.csv")
        sections[s] = spec_checks(m, chans[s], g)
        # non-primary specs are evidence for robustness; their own failures are not blocking
        if s != primary:
            for r in sections[s]:
                if r["status"] == "FAIL":
                    r["status"], r["blocking"] = "WARN", False

    hp = specs_dir / f"{primary}__holdout" / "metrics.json"
    sections[f"{primary} (time holdout)"] = (
        holdout_checks(json.loads(hp.read_text()), g) if hp.exists()
        else [_check("holdout fit exists", None, False, detail="run `make holdout`")]
    )
    # rolling-origin CV folds (the holdout is the last fold)
    folds, fold_ch = {}, {}
    for n in cfg["data"].get("cv_train_weeks", []):
        p = specs_dir / f"{primary}__cv{n}"
        if (p / "metrics.json").exists():
            folds[f"train 1-{n}"] = json.loads((p / "metrics.json").read_text())
            fold_ch[f"cv{n}"] = pd.read_csv(p / "channel_metrics.csv")
    if hp.exists():
        fold_ch["cv143"] = pd.read_csv(hp.parent / "channel_metrics.csv")
    if folds and primary in chans:
        sections[f"{primary} (rolling-origin CV)"] = cv_checks(folds, chans[primary], fold_ch, g)

    if len(chans) >= 2:
        sections["cross-specification agreement"] = cross_spec_checks(chans, g)

    flat = [r for rs in sections.values() for r in rs]
    n_fail = sum(r["status"] == "FAIL" for r in flat)
    n_warn = sum(r["status"] == "WARN" for r in flat)
    verdict = "FAIL" if n_fail else ("PASS_WITH_WARNINGS" if n_warn else "PASS")
    report = {"verdict": verdict, "primary_spec": primary, "n_fail": n_fail, "n_warn": n_warn,
              "n_pass": len(flat) - n_fail - n_warn, "sections": sections}
    (OUTPUTS / "gate_report.json").write_text(json.dumps(report, indent=2, default=lambda o: o.item() if hasattr(o, "item") else str(o)))

    lines = [f"# Gate report: **{verdict}**", "",
             f"{report['n_pass']} pass, {n_warn} warn, {n_fail} fail. Primary spec: `{primary}`.", ""]
    for sec, rs in sections.items():
        lines += [f"## {sec}", "", "| status | check | value | threshold | detail |", "|---|---|---|---|---|"]
        lines += [f"| {r['status']} | {r['check']} | {r['value']} | {r['threshold'] if r['threshold'] is not None else ''} | {r['detail']} |" for r in rs]
        lines.append("")
    (OUTPUTS / "gate_report.md").write_text("\n".join(lines))
    print("\n".join(lines))
    return 1 if n_fail else 0


if __name__ == "__main__":
    sys.exit(main())
