"""Select the primary specification among the candidates, by the protocol fixed before fitting.

    python -m mmm.select   ->  outputs/model_selection.{json,md}

1. Candidates that did not converge are excluded.
2. The candidate with the highest ELPD-LOO is the provisional winner.
3. A simpler candidate (earlier in config order) whose ELPD is within 2 standard errors of the
   difference from the winner is preferred; the simplest such candidate wins.
The SE of a difference uses pointwise ELPD: sqrt(n * var(elpd_i(a) - elpd_i(b))).
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from .config import OUTPUTS, load_config

SE_MULTIPLIER = 2.0


def main() -> None:
    cfg = load_config()
    order = list(cfg["specs"])  # config order = simplest first
    rows, pointwise = [], {}
    for s in order:
        d = OUTPUTS / "specs" / s
        if not (d / "metrics.json").exists():
            rows.append({"spec": s, "status": "not fitted"})
            continue
        m = json.loads((d / "metrics.json").read_text())
        if m.get("status") != "converged":
            rows.append({"spec": s, "status": "not converged", "reason": "; ".join(m.get("convergence_failures", []))})
            continue
        pointwise[s] = pd.read_csv(d / "elpd_pointwise.csv").set_index(["date", "geo"])["elpd_i"]
        rows.append({"spec": s, "status": "converged", "elpd_loo": m["loo"]["elpd_loo"], "elpd_loo_se": m["loo"]["elpd_loo_se"]})

    if not pointwise:
        raise SystemExit("no converged candidate")
    best = max(pointwise, key=lambda s: pointwise[s].sum())
    for r in rows:
        if r["spec"] in pointwise:
            diff = pointwise[best] - pointwise[r["spec"]].reindex(pointwise[best].index)
            r["elpd_diff_from_best"] = float(diff.sum())
            r["se_diff"] = float(np.sqrt(len(diff) * diff.var(ddof=1))) if r["spec"] != best else 0.0
            r["within_2se_of_best"] = r["elpd_diff_from_best"] <= SE_MULTIPLIER * r["se_diff"]
    eligible = [r["spec"] for r in rows if r.get("within_2se_of_best")]
    selected = min(eligible, key=order.index)
    out = {"best_elpd": best, "selected": selected, "rule": f"simplest candidate within {SE_MULTIPLIER:g} SE of the best ELPD",
           "candidates": rows}
    (OUTPUTS / "model_selection.json").write_text(json.dumps(out, indent=2))

    lines = ["# Model selection", "", f"Rule: {out['rule']} (non-converged candidates excluded).", "",
             "| Candidate | Status | ELPD-LOO (SE) | ELPD difference from best (SE) | Within 2 SE |", "|---|---|---|---|---|"]
    for r in rows:
        if r["status"] == "converged":
            lines.append(f"| `{r['spec']}` | converged | {r['elpd_loo']:.1f} ({r['elpd_loo_se']:.1f}) | "
                         f"{-r['elpd_diff_from_best']:.1f} ({r['se_diff']:.1f}) | {'yes' if r['within_2se_of_best'] else 'no'} |")
        else:
            lines.append(f"| `{r['spec']}` | {r['status']} | n/a | n/a | n/a |")
    lines += ["", f"**Highest ELPD:** `{best}`. **Selected:** `{selected}`."]
    (OUTPUTS / "model_selection.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
