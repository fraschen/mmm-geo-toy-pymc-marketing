"""Create the HYPOTHETICAL lift test used to demonstrate calibration.

    python -m mmm.lift_test   ->  data/lift_tests/hypothetical_channel4.csv

No real experiment exists for this dataset. The test below is invented to show how a lift test enters the
model and moves its estimates; its numbers must not be read as evidence about Channel4.

Design (hypothetical): Channel4 spend raised 50% above each test geo's average weekly spend over the last
52 weeks, in 10 geos spread across sizes (every 4th geo by population). Measured result: the extra spend
returned 0.6x its cost in weekly revenue, with a per-geo standard error of 50% of the measured lift.
Units follow pymc-marketing: x and delta_x are weekly spend, delta_y is weekly revenue, per geo.
"""

from __future__ import annotations

import pandas as pd

from . import data
from .config import ROOT, load_config

CHANNEL = "Channel4"
SPEND_INCREASE = 0.5      # +50% of the geo's average weekly spend
TEST_MARGINAL_ROI = 0.6   # hypothetical measured return on the extra spend
REL_SE = 0.5              # per-geo standard error, as a share of the measured lift
OUT = ROOT / "data" / "lift_tests" / "hypothetical_channel4.csv"


def main() -> None:
    md, _ = data.load(load_config())
    geo, date = md.geo_column, md.date_column
    last = md.df[md.df[date] >= sorted(md.df[date].unique())[-52]]
    geos = md.population.sort_values().index[::4]          # 10 geos across the size range
    x = last.groupby(geo)[CHANNEL].mean().loc[geos]
    dx = SPEND_INCREASE * x
    dy = TEST_MARGINAL_ROI * dx
    df = pd.DataFrame({geo: geos, "channel": CHANNEL, "x": x.values, "delta_x": dx.values,
                       "delta_y": dy.values, "sigma": REL_SE * dy.values})
    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT, index=False, float_format="%.2f")
    print(df.round(1).to_string(index=False))


if __name__ == "__main__":
    main()
