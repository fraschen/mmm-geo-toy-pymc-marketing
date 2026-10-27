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
