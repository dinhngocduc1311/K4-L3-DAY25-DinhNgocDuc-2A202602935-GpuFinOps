"""M3 — Purchasing Strategy: break-even, tier choice, spot-checkpoint sim (deck §4).

Run: python missions/m3_purchasing.py
"""
from __future__ import annotations
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
from missions._common import load_csv, num, catalog_by_type
from finops import pricing
from finops import sustainability

DAYS = 30


def run(verbose: bool = True) -> dict:
    jobs = load_csv("workloads.csv")
    cat = catalog_by_type()
    on_demand_monthly = optimized_monthly = 0.0
    recs = []
    for j in jobs:
        gtype = j["gpu_type"]
        ngpu = int(num(j["num_gpus"]))
        hpd = num(j["hours_per_day"])
        interruptible = bool(int(num(j["interruptible"])))
        c = cat[gtype]
        gpu_hours = hpd * DAYS * ngpu
        od = num(c["on_demand_hr"])
        on_demand_cost = gpu_hours * od

        tier = pricing.recommend_tier(hpd, interruptible)
        if tier == "spot":
            sim = pricing.spot_checkpoint_cost(gpu_hours, num(c["spot_hr"]), od,
                                               interrupt_rate=pricing.INTERRUPTION_RATES[gtype])
            opt_cost = sim["spot_cost"]
        elif tier == "reserved":
            # Planning case assumes an existing reusable 3-year capacity pool.
            # Reserved capacity is billed for every hour, including idle hours.
            opt_cost = 24 * DAYS * ngpu * num(c["reserved_3yr_hr"])
        else:
            opt_cost = on_demand_cost

        on_demand_monthly += on_demand_cost
        optimized_monthly += opt_cost
        recs.append({"job_id": j["job_id"], "gpu_type": gtype, "tier": tier,
                     "num_gpus": ngpu, "hours_per_day": hpd, "kind": j["kind"],
                     "on_demand": on_demand_cost, "optimized": opt_cost})

    actual_recs = []
    for j in jobs:
        c = cat[j["gpu_type"]]
        hpd, days, n = num(j["hours_per_day"]), num(j["days"]), int(num(j["num_gpus"]))
        interruptible = bool(int(num(j["interruptible"])))
        costs = pricing.tier_costs(hpd, interruptible, j["gpu_type"], days, c)
        new_tier = pricing.recommend_tier(hpd, interruptible, gpu_type=j["gpu_type"],
                                         job_days=days, prices=c)
        old_tier = pricing.recommend_tier(hpd, interruptible)
        hours = hpd * days * n
        if old_tier == "spot":
            old_cost = pricing.spot_checkpoint_cost(hours, num(c["spot_hr"]), num(c["on_demand_hr"]))["spot_cost"]
        elif old_tier == "reserved":
            old_cost = hours * num(c["reserved_3yr_hr"])
        else:
            old_cost = hours * num(c["on_demand_hr"])
        reason = ("Short job cannot amortize a new 365/1095-day commitment"
                  if old_tier == "reserved" and new_tier == "on_demand"
                  else "Choose least total cost including GPU-specific interruptions and checkpoint/rework")
        actual_recs.append({"job_id": j["job_id"], "gpu_type": j["gpu_type"], "days": days,
                            "old_tier": old_tier, "tier": new_tier, "old_estimate": old_cost,
                            "on_demand": costs["on_demand"] * n, "optimized": costs[new_tier] * n,
                            "candidate_costs": {k: v * n for k, v in costs.items()},
                            "interrupt_rate": pricing.INTERRUPTION_RATES[j["gpu_type"]], "reason": reason})

    carbon_jobs = []
    cleanest = min(sustainability.REGION_CARBON, key=sustainability.REGION_CARBON.get)
    cheapest = min(sustainability.REGION_PRICE_KWH, key=sustainability.REGION_PRICE_KWH.get)
    # Balanced = minimum normalized price + normalized carbon (equal weights).
    balanced = min(sustainability.REGION_CARBON, key=lambda region:
                   sustainability.REGION_CARBON[region] / max(sustainability.REGION_CARBON.values())
                   + sustainability.REGION_PRICE_KWH[region] / max(sustainability.REGION_PRICE_KWH.values()))
    for j in jobs:
        if not int(num(j["interruptible"])):
            continue
        hours = num(j["hours_per_day"]) * num(j["days"]) * num(j["num_gpus"])
        wh = hours * num(cat[j["gpu_type"]]["watts"])
        before = sustainability.carbon_g(wh, "us-east-1")
        after = sustainability.carbon_g(wh, cleanest)
        carbon_jobs.append({"job_id": j["job_id"], "gpu_hours": hours, "wh": wh,
                            "before_g": before, "after_g": after, "saved_g": before - after})
    total_wh = sum(j["wh"] for j in carbon_jobs)
    regions = [{"region": region, "usd_kwh": sustainability.REGION_PRICE_KWH[region],
                "g_kwh": intensity, "energy_usd": sustainability.energy_cost_usd(total_wh, region),
                "carbon_g": sustainability.carbon_g(total_wh, region)}
               for region, intensity in sustainability.REGION_CARBON.items()]

    savings = on_demand_monthly - optimized_monthly
    savings_pct = savings / on_demand_monthly * 100 if on_demand_monthly else 0.0

    if verbose:
        print("== M3 Purchasing Strategy ==")
        print("30-day planning scenario: existing reusable 3yr reservations; not a new short-job commitment.")
        print(f"break-even utilization @ 45% reserved discount = {pricing.break_even_utilization(0.45):.0%}")
        print(f"{'job':18}{'gpu':7}{'tier':11}{'on-demand':>12}{'optimized':>12}")
        for r in recs:
            print(f"{r['job_id']:18}{r['gpu_type']:7}{r['tier']:11}${r['on_demand']:>11,.2f}${r['optimized']:>11,.2f}")
        print(f"\nmonthly: on-demand ${on_demand_monthly:,.0f} -> optimized ${optimized_monthly:,.0f}  ({savings_pct:.1f}% saved)")
        print("Actual-duration extension: new commitments billed in full; per-GPU interruption rates are assumptions.")
        for r in actual_recs:
            print(f"  {r['job_id']}: {r['days']:g} days, {r['old_tier']} -> {r['tier']}; "
                  f"old estimate ${r['old_estimate']:.2f}, OD ${r['on_demand']:.2f}, new ${r['optimized']:.2f}; {r['reason']}")
        actual_od = sum(r["on_demand"] for r in actual_recs)
        actual_opt = sum(r["optimized"] for r in actual_recs)
        print(f"Actual-days total: ${actual_od:.2f} -> ${actual_opt:.2f} ({1-actual_opt/actual_od:.2%} savings)")
        for r in carbon_jobs:
            print(f"  carbon {r['job_id']}: {r['before_g']:.2f} -> {r['after_g']:.2f} gCO2e, Wh={r['wh']:.0f}")
        for r in regions:
            print(f"  {r['region']}: ${r['usd_kwh']}/kWh, {r['g_kwh']} g/kWh, "
                  f"electricity ${r['energy_usd']:.2f}, carbon {r['carbon_g']:.2f} gCO2e")
        print(f"Cheapest={cheapest}; cleanest={cleanest}; equal-weight balanced={balanced}; actual job days.")

    actual_od = sum(r["on_demand"] for r in actual_recs)
    actual_opt = sum(r["optimized"] for r in actual_recs)
    actual_old = sum(r["old_estimate"] for r in actual_recs)
    return {"recommendations": recs, "on_demand_monthly": on_demand_monthly,
            "optimized_monthly": optimized_monthly, "savings_pct": round(savings_pct, 1),
            "actual_recommendations": actual_recs, "actual_on_demand": actual_od,
            "actual_old_estimate": actual_old,
            "actual_old_savings_pct": (1-actual_old/actual_od)*100 if actual_od else 0,
            "actual_optimized": actual_opt, "actual_savings_pct": (1-actual_opt/actual_od)*100 if actual_od else 0,
            "carbon_jobs": carbon_jobs, "regions": regions, "cheapest_region": cheapest,
            "cleanest_region": cleanest, "balanced_region": balanced,
            "carbon_saved_g": sum(j["saved_g"] for j in carbon_jobs)}


if __name__ == "__main__":
    run()
