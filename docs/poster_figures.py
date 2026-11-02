"""
Charts and the QR code for the poster (docs/build_poster.py), drawn from the
figures the final report states and docs/verify_claims.py checks.

    python docs/poster_figures.py
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import qrcode

OUT = Path(__file__).resolve().parent / "deliverables" / "poster"
REPO = "https://github.com/shivanshjindal28/api-exorcist"

RED = "#BC312C"
INK = "#1C1F26"
MUTED = "#6B7280"
LIGHT = "#E3E6EB"
GREEN = "#08744A"
AMBER = "#C2410C"

plt.rcParams.update({
    "font.family": "Calibri",
    "font.size": 19,
    "axes.edgecolor": LIGHT,
    "axes.labelcolor": INK,
    "xtick.color": INK,
    "ytick.color": INK,
    "axes.spines.top": False,
    "axes.spines.right": False,
})


def zombies_caught() -> Path:
    """The comparative benchmark: zombies found, by which sources were used."""
    labels = ["Gateway registry only", "OpenAPI spec only", "Gateway + spec\n(conventional)",
              "All six sources,\ncorrelated"]
    found = [0, 0, 2, 8]
    fig, ax = plt.subplots(figsize=(7.2, 4.0), dpi=200)
    colours = [LIGHT, LIGHT, MUTED, RED]
    bars = ax.barh(labels, [8] * 4, color="#F3F4F6", height=0.62)
    bars = ax.barh(labels, found, color=colours, height=0.62)
    for b, v in zip(bars, found, strict=True):
        ax.text(max(v, 0) + 0.15, b.get_y() + b.get_height() / 2, f"{v} of 8",
                va="center", fontsize=21, fontweight="bold", color=RED if v == 8 else INK)
    ax.set_xlim(0, 9.8)
    ax.invert_yaxis()
    ax.set_xticks([])
    ax.spines["bottom"].set_visible(False)
    ax.tick_params(axis="y", length=0, labelsize=18)
    fig.tight_layout()
    return _save(fig, "chart_zombies.png")


def safe_kill_sweep() -> Path:
    """Outages and refused requests, by how the removal is made (120 estates)."""
    labels = ["Gate\nonly", "Canary,\nno shadow", "3-day\nshadow", "7-day\nshadow", "30-day\nshadow",
              "90-day\nshadow"]
    outages = [49, 0, 3, 6, 4, 0]
    refused = [0, 67, 43, 12, 0, 1]
    x = range(len(labels))
    fig, ax = plt.subplots(figsize=(7.2, 4.6), dpi=200)
    w = 0.38
    b1 = ax.bar([i - w / 2 for i in x], outages, w, color=RED, label="Outages (live endpoints removed)")
    b2 = ax.bar([i + w / 2 for i in x], refused, w, color=AMBER, alpha=0.75, label="Real requests refused")
    for bars in (b1, b2):
        for b in bars:
            h = b.get_height()
            if bars is b2 and b is b2[0]:
                continue  # the gate alone refuses nothing: it has no canary
            ax.text(b.get_x() + b.get_width() / 2, h + 1.2, f"{int(h)}", ha="center", fontsize=16,
                    color=INK)
    ax.set_xticks(list(x), labels, fontsize=15)
    ax.set_yticks([])
    ax.spines["left"].set_visible(False)
    ax.set_ylim(0, 84)
    ax.legend(frameon=False, fontsize=15, loc="upper right")
    # The arrow stops above the bar's "0", so the label stays readable.
    ax.annotate("Safe Kill:\n0 outages", xy=(5 - w / 2, 6), xytext=(4.25, 40), fontsize=18,
                fontweight="bold", color=GREEN, ha="center",
                arrowprops={"arrowstyle": "->", "color": GREEN, "lw": 1.6})
    fig.tight_layout()
    return _save(fig, "chart_safekill.png")


def estate_breakdown() -> Path:
    """The simulated bank's 25 endpoints, by the label the engine gave them."""
    labels = ["Active", "Zombie", "Deprecated", "Orphaned"]
    values = [13, 8, 2, 2]
    colours = [GREEN, RED, "#1D5FC4", AMBER]
    fig, ax = plt.subplots(figsize=(4.4, 4.4), dpi=200)
    wedges, _ = ax.pie(values, colors=colours, startangle=90, counterclock=False,
                       wedgeprops={"width": 0.36, "edgecolor": "white", "linewidth": 2})
    ax.text(0, 0.08, "25", ha="center", va="center", fontsize=34, fontweight="bold", color=INK)
    ax.text(0, -0.2, "endpoints", ha="center", va="center", fontsize=13, color=MUTED)
    ax.legend(wedges, [f"{lab}  {v}" for lab, v in zip(labels, values, strict=True)],
              loc="center left", bbox_to_anchor=(0.95, 0.5), frameon=False, fontsize=14)
    fig.tight_layout()
    return _save(fig, "chart_estate.png")


def safe_kill_pipelines() -> Path:
    """The two Safe Kill pipelines in the committed console screenshot: one stopped
    at approval (callers cannot be identified), one retired through all five stages."""
    from PIL import Image

    shot = Path(__file__).resolve().parent / "diagrams" / "screen-sk-anonymous.png"
    with Image.open(shot) as im:
        stopped = im.crop((290, 630, 1400, 735))
        retired = im.crop((290, 1770, 1400, 1900))
    sheet = Image.new("RGB", (stopped.width, stopped.height + retired.height + 24), "white")
    sheet.paste(stopped, (0, 0))
    sheet.paste(retired, (0, stopped.height + 24))
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / "pipelines.png"
    sheet.save(target)
    return target


def repo_qr() -> Path:
    img = qrcode.make(REPO, box_size=12, border=2)
    target = OUT / "qr_repo.png"
    img.save(target)
    return target


def _save(fig, name: str) -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / name
    fig.savefig(target, transparent=False, facecolor="white")
    plt.close(fig)
    return target


def build_all() -> list[Path]:
    OUT.mkdir(parents=True, exist_ok=True)
    return [zombies_caught(), safe_kill_sweep(), estate_breakdown(), safe_kill_pipelines(), repo_qr()]


if __name__ == "__main__":
    for p in build_all():
        print(f"  wrote {p.name}")
