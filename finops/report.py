"""Report assembly — the lab's deliverable: baseline vs optimized + savings chart."""
from __future__ import annotations


def build_report(baseline_usd: float, optimized_usd: float, levers: dict,
                 sustainability: dict | None = None, period: str = "monthly") -> str:
    """Return a markdown cost-optimization report."""
    savings = baseline_usd - optimized_usd
    pct = (savings / baseline_usd * 100.0) if baseline_usd > 0 else 0.0
    pct_display = f"{pct:.2f}".rstrip("0").rstrip(".")
    lines = [
        "# NimbusAI — GPU Cost Optimization Report",
        "",
        f"**Period:** {period}",
        "",
        f"**Baseline spend:** ${baseline_usd:,.2f}",
        "",
        f"**Optimized spend:** ${optimized_usd:,.2f}",
        "",
        f"**Projected savings:** ${savings:,.2f}  (**{pct_display}%**)",
        "",
        "## Savings by lever",
        "",
        "| Lever | Savings (USD) |",
        "|---|---|",
    ]
    for name, amount in levers.items():
        lines.append(f"| {name} | ${amount:,.2f} |")
    if sustainability:
        lines += [
            "",
            "## Sustainability",
            "",
            f"- Energy per query: {sustainability.get('wh_per_query', 0):.2f} Wh",
            f"- Carbon per query: {sustainability.get('carbon_g', 0):.3f} gCO2e",
            f"- Cleanest region: {sustainability.get('best_region', 'n/a')}",
            f"- Cheapest electricity region: {sustainability.get('cheapest_region', 'n/a')}",
            f"- Balanced region (equal normalized price/carbon weights): {sustainability.get('balanced_region', 'n/a')}",
        ]
    lines += ["", "_Illustrative June-2026 lab figures; validate prices and assumptions before acting._"]
    return "\n".join(lines)


def savings_waterfall(levers: dict, path: str, baseline_usd: float | None = None) -> str:
    """Write a simple savings bar chart PNG. Returns the path. No-op if matplotlib absent."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return ""
    names = list(levers.keys())
    vals = [levers[n] for n in names]
    fig, ax = plt.subplots(figsize=(11, 5.5))
    if baseline_usd is None:
        ax.bar(names, vals, color="#2e548a")
    else:
        positions = list(range(len(names) + 2))
        labels = ["Baseline"] + names + ["Optimized"]
        remaining = baseline_usd
        heights, bottoms = [baseline_usd], [0]
        for value in vals:
            remaining -= value
            heights.append(value)
            bottoms.append(remaining)
        heights.append(remaining)
        bottoms.append(0)
        ax.bar(positions, heights, bottom=bottoms,
               color=["#2e548a"] + ["#25865b"] * len(vals) + ["#2e548a"])
        for i, (height, bottom) in enumerate(zip(heights, bottoms)):
            ax.text(i, bottom + height + baseline_usd * 0.015,
                    f"{'-' if 0 < i < len(positions)-1 else ''}${height:,.2f}",
                    ha="center", fontsize=8)
        ax.set_xticks(positions, labels)
        ax.set_ylim(0, baseline_usd * 1.15)
    ax.set_ylabel("Modeled spend (USD / 30 days)")
    ax.set_title("Baseline to optimized: sequential, non-overlapping savings")
    plt.xticks(rotation=20, ha="right")
    plt.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)
    return path
