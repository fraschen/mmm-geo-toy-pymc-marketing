"""Paths and config loading."""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
OUTPUTS = ROOT / "outputs"
ARTIFACTS = ROOT / "artifacts"  # large, regenerable (idata); git-ignored


def load_config(path: Path | str = ROOT / "config" / "pipeline.yaml") -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def spec_config(cfg: dict, name: str) -> dict:
    """A model spec by name: a candidate from `specs`, or a calibration run (its base spec + lift test)."""
    if name in cfg["specs"]:
        return cfg["specs"][name]
    cal = cfg.get("calibration_specs", {})[name]
    return {**cfg["specs"][cal["base"]], "lift_test": cal["lift_test"],
            "description": f"{cal['base']} calibrated with {cal['lift_test']}"}
