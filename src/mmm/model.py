"""Build a pymc-marketing MMM from a spec in config/pipeline.yaml."""

from __future__ import annotations

import numpy as np
import pandas as pd
import xarray as xr
from pymc_extras.prior import Prior
from pymc_marketing.mmm import MMM, GeometricAdstock, LogisticSaturation
from pymc_marketing.mmm.scaling import FixedScaling

from .config import ROOT
from .data import ModelData


def _prior(p: dict, dims) -> Prior:
    p = dict(p)
    return Prior(p.pop("dist"), **p, dims=dims)


def population_scaling(md: ModelData) -> dict:
    """Scale each geo by its population: scale = population x the largest per-capita value.

    The model then works in per-capita terms on a [0, 1] range, while contributions and ROI are still
    returned in revenue. Computed from `md` only, so CV folds see nothing from their forecast window.
    """
    geo, ch, y = md.geo_column, md.channel_columns, md.target_column
    pop = md.population
    p = md.df[geo].map(pop)
    geos = sorted(md.df[geo].unique())
    max_pc_y = float((md.df[y] / p).max())
    max_pc_ch = {c: float((md.df[c] / p).max()) for c in ch}
    target = xr.DataArray([pop[g] * max_pc_y for g in geos], dims=geo, coords={geo: geos})
    channel = xr.DataArray([[pop[g] * max_pc_ch[c] for c in ch] for g in geos],
                           dims=(geo, "channel"), coords={geo: geos, "channel": ch})
    return {"target": FixedScaling(dims=(), value=target), "channel": FixedScaling(dims=(), value=channel)}


def scaled_target_mean(md: ModelData) -> float:
    """Typical value of the population-scaled target (a typical geo-week)."""
    p = md.df[md.geo_column].map(md.population)
    pc = md.df[md.target_column] / p
    return float((pc / pc.max()).mean())


def expected_effect_per_channel(md: ModelData, share: np.ndarray, media_share_of_target: float = 0.3) -> np.ndarray:
    """Prior anchor for saturation_beta, in the model's scaled units.

    Assumes paid media drives ~30% of revenue, split by `share`, and that a logistic curve at typical
    scaled spend sits around 0.4 of its ceiling. The prior SD is 2x this anchor, so it sets a scale
    rather than a value; prior-implied ROI is reported next to the posterior.
    """
    return media_share_of_target * scaled_target_mean(md) * share / 0.4


def build(md: ModelData, spec: dict) -> MMM:
    ch = md.channel_columns
    geo = md.geo_column
    y_bar = scaled_target_mean(md)
    spend = md.df[ch].sum().to_numpy()
    share = spend / spend.sum() if spec["beta_prior"] == "spend_share" else np.full(len(ch), 1 / len(ch))
    expected = expected_effect_per_channel(md, share)

    if spec["beta_pooling"] == "pooled":
        beta = Prior("HalfNormal", sigma=2 * expected, dims="channel")
    elif spec["beta_pooling"] == "hierarchical":
        # log beta[c, g] = mu[c] + tau * z[c, g]; non-centred to avoid funnels
        beta = Prior(
            "Normal",
            mu=Prior("Normal", mu=np.log(expected), sigma=1.0, dims="channel"),
            sigma=Prior("HalfNormal", sigma=0.3),
            dims=("channel", geo),
            centered=False,
            transform="exp",
        )
    else:
        raise ValueError(spec["beta_pooling"])

    if spec["control_pooling"] == "pooled":
        gamma_control = Prior("Normal", mu=0, sigma=y_bar, dims="control")
    elif spec["control_pooling"] == "hierarchical":
        # gamma[g, k] = mu[k] + sigma[k] * z[g, k]; one cross-geo spread per control, so controls
        # without geo heterogeneity shrink toward a shared value
        gamma_control = Prior(
            "Normal",
            mu=Prior("Normal", mu=0, sigma=y_bar, dims="control"),
            sigma=Prior("HalfNormal", sigma=0.25 * y_bar, dims="control"),
            dims=(geo, "control"),
            centered=False,
        )
    else:
        raise ValueError(spec["control_pooling"])

    adstock = GeometricAdstock(l_max=spec["l_max"], priors={"alpha": _prior(spec["adstock_alpha"], "channel")})
    saturation = LogisticSaturation(priors={"lam": _prior(spec["saturation_lam"], "channel"), "beta": beta})

    seasonality = spec.get("yearly_seasonality")
    model_config = {
        "intercept": Prior("Normal", mu=y_bar, sigma=y_bar, dims=geo),
        "likelihood": Prior("Normal", sigma=Prior("HalfNormal", sigma=0.5 * y_bar, dims=geo), dims=("date", geo)),
        "gamma_control": gamma_control,
    }
    if seasonality:
        model_config["gamma_fourier"] = Prior("Laplace", mu=0, b=0.5 * y_bar, dims="fourier_mode")

    mmm = MMM(
        date_column=md.date_column,
        target_column=md.target_column,
        channel_columns=ch,
        control_columns=md.control_columns,
        dims=(geo,),
        adstock=adstock,
        saturation=saturation,
        yearly_seasonality=seasonality,
        scaling=population_scaling(md) if spec.get("scaling") == "population" else None,
        model_config=model_config,
    )
    mmm.build_model(md.X, md.y)
    if spec.get("lift_test"):
        # calibration: each channel's saturation curve must reproduce the measured lift (x -> x + delta_x)
        lift = pd.read_csv(ROOT / spec["lift_test"])
        mmm.add_lift_test_measurements(lift[lift[geo].isin(md.df[geo].unique())])
    # original-scale deterministics used by mmm.summary / mmm.plot (no effect on sampling)
    registered = set(mmm.model.named_vars)
    mmm.add_original_scale_contribution_variable(var=[
        v for v in ("channel_contribution", "control_contribution", "intercept_contribution",
                    "yearly_seasonality_contribution", "y") if v in registered
    ])
    return mmm
