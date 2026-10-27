"""Rebuild a fitted model from its spec and saved posterior (artifacts/<run>/posterior.nc)."""

from __future__ import annotations

import xarray as xr

from pymc_marketing.mmm import MMM

from . import data, model
from .config import ARTIFACTS, load_config, spec_config


def load_fitted(spec: str, train_weeks: int | None = None, holdout: bool = False):
    """Return (mmm, md_train, md_test). md_test is None for a full-data fit."""
    cfg = load_config()
    md, _ = data.load(cfg)
    test = None
    if holdout or train_weeks:
        md, test = md.split(cfg["data"]["holdout_weeks"], train_weeks=train_weeks)
    run = spec + ("__holdout" if holdout else "") + (f"__cv{train_weeks}" if train_weeks else "")
    mmm = model.build(md, spec_config(cfg, spec))
    idata = xr.open_datatree(ARTIFACTS / run / "posterior.nc").load()
    groups = {g: idata[g].to_dataset() for g in idata.children}
    # The saved file keeps parameters only; the model's inputs are fully determined by the rebuilt model.
    groups.setdefault("constant_data", constant_data(mmm))
    groups.setdefault("fit_data", mmm.create_fit_data(md.X, md.y))
    mmm.idata = xr.DataTree.from_dict(groups)
    return mmm, md, test


def constant_data(mmm: MMM) -> xr.Dataset:
    """The model's pm.Data containers as an xarray Dataset (what PyMC stores as `constant_data`)."""
    m = mmm.model
    out = {}
    for v in m.data_vars:
        dims = m.named_vars_to_dims.get(v.name)
        val = v.get_value()
        coords = {d: list(m.coords[d]) for d in dims} if dims else None
        out[v.name] = xr.DataArray(val, dims=dims, coords=coords) if dims else xr.DataArray(val)
    return xr.Dataset(out)
