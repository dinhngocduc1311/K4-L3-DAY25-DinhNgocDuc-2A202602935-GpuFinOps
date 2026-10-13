"""M1 — Efficiency Audit: MFU/MBU, the GPU-Util lie, and idle waste (deck §5).

Run: python missions/m1_efficiency_audit.py
"""
from __future__ import annotations
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
from collections import defaultdict
from missions._common import load_csv, num, catalog_by_type
from finops import metrics

MEMORY_HEADROOM = 1.10  # Assumption: 10% above maximum observed VRAM.
TARGET_UTILIZATION = 0.80  # Assumed attainable MFU/MBU, to be benchmarked.


def rightsize_candidate(s: dict, cat: dict) -> dict:
    """Capacity screen, not a throughput benchmark; keep training separate from decode."""
    cur = cat[s["gpu_type"]]
    required_mem = s["max_mem_gb"] * MEMORY_HEADROOM
    candidates = [c for c in cat.values()
                  if num(c["hbm_gb"]) >= required_mem
                  and num(c["peak_bw_tbs"]) * TARGET_UTILIZATION >= s["max_bw_tbs"]
                  and num(c["peak_tflops_fp16"]) * TARGET_UTILIZATION >= s["max_tflops"]
                  and num(c["on_demand_hr"]) < num(cur["on_demand_hr"])]
    memory_bound = s["workload"] in ("infer", "embed")
    target = min(candidates, key=lambda c: (
        num(c["on_demand_hr"]) / num(c["hbm_gb"]) if memory_bound else num(c["on_demand_hr"]),
        num(c["on_demand_hr"]))) if candidates else cur
    active_hours = s["sample_hours"] - s["idle_hours"]
    saving = (num(cur["on_demand_hr"]) - num(target["on_demand_hr"])) * active_hours * 30
    reason = (f"VRAM >= {required_mem:.2f} GB; BW >= {s['max_bw_tbs']/TARGET_UTILIZATION:.3f} TB/s; "
              f"FP16 >= {s['max_tflops']/TARGET_UTILIZATION:.1f} TFLOPs; "
              "10% VRAM headroom, target MFU/MBU 80%; benchmark required")
    if target is cur:
        reason = "No cheaper GPU passes VRAM, bandwidth and compute capacity screens; " + reason
    return {"gpu_id": s["gpu_id"], "workload": s["workload"], "current_gpu": s["gpu_type"],
            "proposed_gpu": target["gpu_type"], "required_mem_gb": required_mem,
            "current_usd_per_gb": num(cur["on_demand_hr"]) / num(cur["hbm_gb"]),
            "proposed_usd_per_gb": num(target["on_demand_hr"]) / num(target["hbm_gb"]),
            "monthly_savings": saving, "reason": reason}


def run(verbose: bool = True) -> dict:
    tel = load_csv("gpu_telemetry.csv")
    cat = catalog_by_type()

    # per-row MFU/MBU, then aggregate per GPU
    agg = defaultdict(lambda: {"util": [], "mfu": [], "mbu": [], "type": None,
                               "idle_hours": 0, "max_mem_gb": 0, "max_bw_tbs": 0,
                               "max_tflops": 0, "workload": ""})
    for r in tel:
        gtype = r["gpu_type"]
        peak_fp16 = num(cat[gtype]["peak_tflops_fp16"])
        peak_bw = num(cat[gtype]["peak_bw_tbs"])
        mfu = metrics.compute_mfu(num(r["achieved_tflops"]), peak_fp16)
        mbu = metrics.compute_mbu(num(r["achieved_bw_tbs"]), peak_bw)
        a = agg[r["gpu_id"]]
        a["type"] = gtype
        a["workload"] = r["workload"]
        a["max_mem_gb"] = max(a["max_mem_gb"], num(r["mem_used_gb"]))
        a["max_bw_tbs"] = max(a["max_bw_tbs"], num(r["achieved_bw_tbs"]))
        a["max_tflops"] = max(a["max_tflops"], num(r["achieved_tflops"]))
        a["util"].append(num(r["gpu_util_pct"]))
        a["mfu"].append(mfu)
        a["mbu"].append(mbu)
        if num(r["gpu_util_pct"]) < 10:  # effectively idle this interval (1h)
            a["idle_hours"] += 1

    summary = []
    for gid, a in agg.items():
        summary.append({
            "gpu_id": gid, "gpu_type": a["type"],
            "gpu_util_pct": round(sum(a["util"]) / len(a["util"]), 1),
            "mfu": round(sum(a["mfu"]) / len(a["mfu"]), 3),
            "mbu": round(sum(a["mbu"]) / len(a["mbu"]), 3),
            "idle_hours": a["idle_hours"],
            "sample_hours": len(a["util"]), "workload": a["workload"],
            "max_mem_gb": a["max_mem_gb"], "max_bw_tbs": a["max_bw_tbs"],
            "max_tflops": a["max_tflops"],
        })

    lies = metrics.flag_util_lies(summary)
    idle_waste = 0.0
    for s in summary:
        on_demand = num(cat[s["gpu_type"]]["on_demand_hr"])
        idle_waste += metrics.idle_waste_usd(s["idle_hours"], on_demand)

    # Decode/embed are assumed memory-bound; low MBU alone cannot prove that regime.
    right_sizing = [rightsize_candidate(s, cat) for s in summary
                   if s["workload"] in ("infer", "embed") and s["mbu"] < 0.60]
    lie_sizing = [rightsize_candidate(s, cat) for s in lies if s["workload"] == "train"]
    fleet_daily = sum(s["sample_hours"] * num(cat[s["gpu_type"]]["on_demand_hr"])
                      for s in summary)

    if verbose:
        print("== M1 Efficiency Audit ==")
        print(f"{'GPU':14}{'type':7}{'util%':>7}{'MFU':>7}{'MBU':>7}{'idle_h':>8}")
        for s in sorted(summary, key=lambda x: x["mfu"]):
            print(f"{s['gpu_id']:14}{s['gpu_type']:7}{s['gpu_util_pct']:>7}{s['mfu']:>7}{s['mbu']:>7}{s['idle_hours']:>8}")
        print(f"\nGPU-Util LIES (util>=90% but MFU<30%): {[l['gpu_id'] for l in lies]}")
        print(f"Idle waste (1 day): ${idle_waste:,.2f}  ->  ${idle_waste*30:,.0f}/month")
        print(f"Idle share of observed telemetry fleet on-demand spend: {idle_waste/fleet_daily:.2%}")
        print("Right-sizing candidates (conditional; 30 days, on-demand, active hours only):")
        for s in right_sizing + lie_sizing:
            print(f"  {s['gpu_id']}: {s['current_gpu']} -> {s['proposed_gpu']}, "
                  f"${s['monthly_savings']:.2f}/month; {s['reason']}")

    return {"summary": summary, "lies": lies, "idle_waste_daily": idle_waste,
            "fleet_daily": fleet_daily, "right_sizing": right_sizing, "lie_sizing": lie_sizing}


if __name__ == "__main__":
    run()
