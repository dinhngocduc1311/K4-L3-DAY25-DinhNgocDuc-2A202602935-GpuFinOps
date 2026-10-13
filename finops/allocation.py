"""Cost allocation — turn a shared GPU bill into per-team accountability.

Maturity ladder (deck §10): visibility -> showback -> chargeback. Only enforce
chargeback once tag coverage is high enough (~>80%), else you bill noise.
"""
from __future__ import annotations
from collections import defaultdict


def cost_by_tag(rows, dim: str, cost_key: str = "cost") -> dict:
    """Sum cost grouped by a tag dimension (e.g. 'team' or 'project')."""
    out: dict = defaultdict(float)
    for r in rows:
        key = r.get(dim) or "(untagged)"
        out[key] += float(r.get(cost_key, 0.0))
    return dict(out)


def tag_coverage(rows, tag_keys) -> float:
    """Fraction of rows where every required tag is present and non-empty (0..1)."""
    rows = list(rows)
    if not rows:
        return 0.0
    tagged = 0
    for r in rows:
        if all(str(r.get(k, "")).strip() not in ("", "(untagged)", "nan", "None") for k in tag_keys):
            tagged += 1
    return tagged / len(rows)


def chargeback_ready(coverage: float, threshold: float = 0.80) -> bool:
    """Enforce chargeback only once tag coverage clears the threshold."""
    return coverage >= threshold


def to_focus_rows(rows, period_start: str = "2026-06-01", billing_account: str = "nimbusai-prod") -> list:
    """Emit FOCUS-style normalized cost rows (the open multi-vendor billing schema).

    Minimal FOCUS 1.x-flavored columns so cost data is portable across providers.
    """
    focus = []
    for r in rows:
        focus.append({
            "BillingAccountId": billing_account,
            "ChargePeriodStart": period_start,
            "ServiceCategory": "AI and Machine Learning",
            "ServiceName": r.get("service", "gpu-inference"),
            "ResourceId": r.get("resource_id", r.get("gpu_id", "")),
            "BilledCost": float(r.get("cost", 0.0)),
            "BillingCurrency": "USD",
            "Tags": {"team": r.get("team", ""), "project": r.get("project", "")},
        })
    return focus
