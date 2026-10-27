"""Load, validate and shape the Meridian geo dataset for pymc-marketing."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .config import ROOT


@dataclass
class ModelData:
    df: pd.DataFrame            # long panel: date, geo, channel spend, controls, target
    channel_columns: list[str]  # spend columns fed to the model
    control_columns: list[str]
    date_column: str
    geo_column: str
    target_column: str
    revenue_per_kpi: float

    @property
    def X(self) -> pd.DataFrame:
        return self.df.drop(columns=[self.target_column])

    @property
    def y(self) -> pd.Series:
        return self.df[self.target_column]

    def split(self, horizon: int, train_weeks: int | None = None) -> tuple["ModelData", "ModelData"]:
        """Train on the first `train_weeks` weeks (default: all but the last `horizon`),
        test on the `horizon` weeks that follow."""
        dates = np.sort(self.df[self.date_column].unique())
        n_train = len(dates) - horizon if train_weeks is None else train_weeks
        train_dates, test_dates = dates[:n_train], dates[n_train:n_train + horizon]
        train = self.df[self.df[self.date_column].isin(train_dates)].reset_index(drop=True)
        test = self.df[self.df[self.date_column].isin(test_dates)].reset_index(drop=True)
        return (
            ModelData(train, **self._meta()),
            ModelData(test, **self._meta()),
        )

    def _meta(self) -> dict:
        return dict(
            channel_columns=self.channel_columns,
            control_columns=self.control_columns,
            date_column=self.date_column,
            geo_column=self.geo_column,
            target_column=self.target_column,
            revenue_per_kpi=self.revenue_per_kpi,
        )


def validate_raw(raw: pd.DataFrame, cfg: dict) -> dict:
    """Hard data checks. Returns a dict consumed by the data gate."""
    d = cfg["data"]
    date, geo = d["date_column"], d["geo_column"]
    spend_cols = [f"{c}_spend" for c in d["channels"]]
    raw_controls = [c for c in d["controls"] if c != "trend"]
    required = [date, geo, d["kpi_column"], d["revenue_per_kpi_column"], *spend_cols, *raw_controls]

    dates = pd.to_datetime(raw[date])
    n_dates, n_geos = dates.nunique(), raw[geo].nunique()
    gaps = dates.drop_duplicates().sort_values().diff().dropna().dt.days
    rpk = raw[d["revenue_per_kpi_column"]]
    return {
        "missing_columns": sorted(set(required) - set(raw.columns)),
        "n_rows": int(len(raw)),
        "n_geos": int(n_geos),
        "n_weeks": int(n_dates),
        "balanced_panel": bool(len(raw) == n_dates * n_geos and not raw.duplicated([date, geo]).any()),
        "weekly_contiguous": bool((gaps == 7).all()),
        "n_missing_values": int(raw[[c for c in required if c in raw]].isna().sum().sum()),
        "negative_spend_cells": int((raw[spend_cols] < 0).sum().sum()),
        "negative_kpi_cells": int((raw[d["kpi_column"]] < 0).sum()),
        "revenue_per_kpi_cv": float(rpk.std() / rpk.mean()),
        "channel_zero_spend_share": {c: float((raw[f"{c}_spend"] == 0).mean()) for c in d["channels"]},
        "date_min": str(dates.min().date()),
        "date_max": str(dates.max().date()),
    }


def load(cfg: dict) -> tuple[ModelData, dict]:
    d = cfg["data"]
    raw = pd.read_csv(ROOT / d["path"], index_col=0)
    checks = validate_raw(raw, cfg)

    date, geo = d["date_column"], d["geo_column"]
    df = pd.DataFrame({date: pd.to_datetime(raw[date]), geo: raw[geo]})
    # Spend (not impressions) so that contribution / spend is an ROI. In this
    # dataset spend = impressions x a constant CPM per channel, so nothing is lost.
    for c in d["channels"]:
        df[c] = raw[f"{c}_spend"].astype(float)

    # pymc-marketing max-scales channels and target but passes controls through
    # untouched, so put controls on an O(1) scale here.
    for c in d["controls"]:
        if c == "trend":
            t = (df[date] - df[date].min()).dt.days
            df[c] = t / t.max()
        elif c.startswith("Organic"):
            # count variable that scales with geo size -> per-geo max scaling, like media
            df[c] = raw[c] / raw.groupby(geo)[c].transform("max").replace(0, 1)
        elif c == "Promo":
            df[c] = raw[c] / raw[c].max()
        else:
            # competitor / sentiment are already centred, unit-variance indices
            df[c] = raw[c].astype(float)

    df[d["target_column"]] = raw[d["kpi_column"]] * raw[d["revenue_per_kpi_column"]]
    df = df.sort_values([date, geo]).reset_index(drop=True)

    md = ModelData(
        df=df,
        channel_columns=list(d["channels"]),
        control_columns=list(d["controls"]),
        date_column=date,
        geo_column=geo,
        target_column=d["target_column"],
        revenue_per_kpi=float(raw[d["revenue_per_kpi_column"]].mean()),
    )
    return md, checks
