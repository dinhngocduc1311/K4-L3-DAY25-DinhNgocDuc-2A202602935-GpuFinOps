"""M4 — Cost Allocation: tag -> showback -> chargeback + FOCUS export (deck §10).

Run: python missions/m4_allocation.py
"""
from __future__ import annotations
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import csv
import os
from missions._common import load_csv, ROOT
from finops import allocation
from missions.m2_inference_levers import price_requests

TAGS = ["team", "project"]


def run(verbose: bool = True) -> dict:
    rows = load_csv("token_usage.csv")
    priced = price_requests(rows)

    by_team = allocation.cost_by_tag(priced, "team")
    by_project = allocation.cost_by_tag(priced, "project")
    coverage = allocation.tag_coverage(priced, TAGS)
    ready = allocation.chargeback_ready(coverage)

    # Export every request so BilledCost reconciles with M2/M4 totals.
    period_start = min(r["ts"] for r in rows) if rows else "2026-06-15T00:00:00"
    focus = allocation.to_focus_rows(priced, period_start=period_start)
    out_path = os.path.join(ROOT, "outputs", "focus_export.csv")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["BillingAccountId", "ChargePeriodStart", "ServiceCategory",
                    "ServiceName", "ResourceId", "BilledCost", "BillingCurrency", "team", "project"])
        for fr in focus:
            w.writerow([fr["BillingAccountId"], fr["ChargePeriodStart"], fr["ServiceCategory"],
                        fr["ServiceName"], fr["ResourceId"], fr["BilledCost"], fr["BillingCurrency"],
                        fr["Tags"]["team"], fr["Tags"]["project"]])

    if verbose:
        print("== M4 Cost Allocation ==")
        print("cost by team ($/day):")
        for k, v in sorted(by_team.items(), key=lambda x: -x[1]):
            print(f"  {k:12} ${v:8.2f}")
        print(f"tag coverage: {coverage:.0%}  ->  chargeback ready? {ready}")
        print(f"FOCUS export -> outputs/focus_export.csv ({len(focus)} rows)")

    return {"by_team": by_team, "by_project": by_project,
            "total_daily": sum(r["cost"] for r in priced), "export_rows": len(focus),
            "tag_coverage": coverage, "chargeback_ready": ready}


if __name__ == "__main__":
    run()
