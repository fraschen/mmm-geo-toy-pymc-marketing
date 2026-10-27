"""Shared figure style for the reports: one palette, recessive axes, thin marks."""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

# categorical slots in fixed order (validated palette); text stays in ink colors, never series colors
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"]
INK, MUTED, GRID, BAND = "#1f1f1e", "#5f5e5a", "#e6e5e0", "#2a78d6"
GOOD, BAD = "#1baf7a", "#d03b3b"


def style(ax, grid_axis: str = "y"):
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.spines["left"].set_color(MUTED)
    ax.spines["bottom"].set_color(MUTED)
    ax.tick_params(colors=MUTED, labelcolor=INK, labelsize=8)
    if grid_axis:
        ax.grid(axis=grid_axis, color=GRID, lw=0.8)
    ax.set_axisbelow(True)
    return ax


def title(ax, text: str, sub: str | None = None):
    ax.set_title(text, loc="left", fontsize=10.5, color=INK, pad=14 if sub else 8)
    if sub:
        ax.text(0, 1.01, sub, transform=ax.transAxes, fontsize=8, color=MUTED, va="bottom")


def save(fig, path):
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
