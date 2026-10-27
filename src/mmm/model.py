"""Build a pymc-marketing MMM from a spec in config/pipeline.yaml."""

from __future__ import annotations

import numpy as np
from pymc_extras.prior import Prior
from pymc_marketing.mmm import MMM, GeometricAdstock, LogisticSaturation

from .data import ModelData


def _prior(p: dict, dims) -> Prior:
    p = dict(p)
    return Prior(p.pop("dist"), **p, dims=dims)


def expected_effect_per_channel(md: ModelData, share: np.ndarray, media_share_of_target: float = 0.3) -> np.ndarray:
    """Prior anchor for saturation_beta.

    Assumes paid media drives ~30% of revenue, split by `share`, and that a
    logistic curve at typical scaled spend sits around 0.4 of its ceiling.
    The prior sigma is 2x this anchor. The anchor is expressed in per-geo scaled
    units (typical week ~0.55); under pymc-marketing's default global scaling
    (typical week ~0.29) that makes the prior ~1.9x wider again -- deliberately
    left loose, and prior-implied ROI is reported next to the posterior.
    """
    g = md.df.groupby(md.geo_column)[md.target_column]
    y_scaled_mean = float((g.transform("mean") / g.transform("max")).mean())
    return media_share_of_target * y_scaled_mean * share / 0.4


def build(md: ModelData, spec: dict) -> MMM:
    ch = md.channel_columns
    geo = md.geo_column
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

    adstock = GeometricAdstock(l_max=spec["l_max"], priors={"alpha": _prior(spec["adstock_alpha"], "channel")})
    saturation = LogisticSaturation(priors={"lam": _prior(spec["saturation_lam"], "channel"), "beta": beta})

    model_config = {
        # target is max-scaled (globally by default), so a typical week sits around 0.3-0.55
        "intercept": Prior("Normal", mu=0.5, sigma=0.5, dims=geo),
        "likelihood": Prior("Normal", sigma=Prior("HalfNormal", sigma=0.2, dims=geo), dims=("date", geo)),
        # controls and seasonality pooled across geos
        "gamma_control": Prior("Normal", mu=0, sigma=0.5, dims="control"),
        "gamma_fourier": Prior("Laplace", mu=0, b=0.2, dims="fourier_mode"),
    }

    mmm = MMM(
        date_column=md.date_column,
        target_column=md.target_column,
        channel_columns=ch,
        control_columns=md.control_columns,
        # default scaling: channels and target max-scaled globally (one max across geos)
        dims=(geo,),
        adstock=adstock,
        saturation=saturation,
        yearly_seasonality=2,
        model_config=model_config,
    )
    mmm.build_model(md.X, md.y)
    # original-scale deterministics used by mmm.summary / mmm.plot (no effect on sampling)
    registered = set(mmm.model.named_vars)
    mmm.add_original_scale_contribution_variable(var=[
        v for v in ("channel_contribution", "control_contribution", "intercept_contribution",
                    "yearly_seasonality_contribution", "y") if v in registered
    ])
    return mmm
