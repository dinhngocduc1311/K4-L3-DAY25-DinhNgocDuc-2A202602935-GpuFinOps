"""Independent extension checks; the 15 instructor tests in tests/ stay unchanged.

Run: python -m pytest -q checks
"""
import csv
import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from finops import pricing
from missions import m1_efficiency_audit as m1, m2_inference_levers as m2
from missions import m3_purchasing as m3, m4_allocation as m4, m5_report as m5
from missions._common import catalog_by_type


@pytest.fixture(scope="module")
def results():
    return m1.run(False), m2.run(False), m3.run(False), m4.run(False), m5.run(False)


def test_original_data_unchanged():
    before = json.loads((ROOT / "outputs/before/baseline.json").read_text(encoding="utf-8"))
    assert {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (ROOT / "data").glob("*.csv")} == before["data_sha256"]


@pytest.mark.parametrize("price", [0.2, 3.0])
def test_cache_break_even_units_and_batch(price):
    write = price * 1.25
    threshold = pricing.cache_break_even_reads(write, price)
    assert threshold == pytest.approx(1.25 / 0.9)
    assert not pricing.cache_is_worth_it(threshold - 0.01, write, price_in_per_m=price)
    assert pricing.cache_is_worth_it(threshold, write, price_in_per_m=price)
    assert pricing.cache_break_even_reads(write, price * 0.5) == pytest.approx(threshold * 2)


def test_cache_no_discount_and_zero_reads():
    assert not pricing.cache_is_worth_it(0, 0)
    assert not pricing.cache_is_worth_it(100, 1, read_discount=1)
    with pytest.raises(ValueError):
        pricing.cache_is_worth_it(-1, 1)
    with pytest.raises(ValueError):
        pricing.cache_break_even_reads(-1, 1)


@pytest.mark.parametrize("batch", [0, 1])
def test_cache_gate_never_increases_cost(batch):
    row = {"input_tokens": "1000", "output_tokens": "100", "cached_input_tokens": "800",
           "route_tier": "small", "is_batch": str(batch)}
    no_cache = m2.price_requests([row], use_cache=False)[0]["cost"]
    for reads in (0, 0.5, 1, 2, 4, 20):
        result = m2.price_requests([row], avg_reads=reads)[0]
        assert result["cost"] <= no_cache + 1e-12
        assert result["cache_write_cost"] >= 0
    enabled = m2.price_requests([row], avg_reads=4)[0]
    expected_write = 800 / 4 / 1e6 * 0.2 * 1.25
    assert enabled["cache_write_cost"] == pytest.approx(expected_write)


@pytest.mark.parametrize("days,tier", [(30, "on_demand"), (365, "reserved_1yr"), (1095, "reserved_3yr")])
def test_new_commitment_duration(days, tier):
    cat = catalog_by_type()
    assert pricing.recommend_tier(24, False, gpu_type="H100", job_days=days, prices=cat["H100"]) == tier


def test_full_reserved_term_and_idle_billing():
    c = catalog_by_type()["H100"]
    costs = pricing.tier_costs(4, False, "H100", 30, c)
    assert costs["reserved_1yr"] == 365 * 24 * float(c["reserved_1yr_hr"])
    assert costs["reserved_3yr"] == 1095 * 24 * float(c["reserved_3yr_hr"])
    assert pricing.recommend_tier(4, False, gpu_type="H100", job_days=1095, prices=c) == "on_demand"
    with pytest.raises(ValueError):
        pricing.recommend_tier(25, False)


def test_expensive_spot_is_rejected():
    c = dict(catalog_by_type()["H100"], spot_hr="100")
    assert pricing.recommend_tier(24, True, gpu_type="H100", job_days=30, prices=c) == "on_demand"


def test_interruption_rate_changes_cost():
    c = catalog_by_type()["H100"]
    low = pricing.tier_costs(10, True, "H100", 30, c)["spot"]
    high = pricing.tier_costs(10, True, "A10G", 30, c)["spot"]
    assert high > low
    with pytest.raises(ValueError):
        pricing.spot_checkpoint_cost(-1, 1, 2)
    with pytest.raises(ValueError):
        pricing.request_cost(100, -1, 3, 15)
    with pytest.raises(ValueError):
        pricing.cache_is_worth_it(float("nan"), 1)
    with pytest.raises(ValueError):
        pricing.tier_costs(4, False, "H100", float("inf"), c)


def test_rightsizing_enforces_capacity(results):
    r1 = results[0]
    cat = catalog_by_type()
    samples = {s["gpu_id"]: s for s in r1["summary"]}
    for proposal in r1["right_sizing"] + r1["lie_sizing"]:
        s = samples[proposal["gpu_id"]]
        target = cat[proposal["proposed_gpu"]]
        assert float(target["hbm_gb"]) >= s["max_mem_gb"] * 1.1
        assert float(target["peak_bw_tbs"]) * 0.8 >= s["max_bw_tbs"]
        assert float(target["peak_tflops_fp16"]) * 0.8 >= s["max_tflops"]
        if s["gpu_type"] == "A100":
            assert proposal["proposed_gpu"] not in ("A10G", "L4")
    # The same demand chooses capacity value for decode, hourly price for training.
    demand = samples["gpu-h100-4"]
    assert m1.rightsize_candidate(demand, cat)["proposed_gpu"] == "A100"
    assert m1.rightsize_candidate({**demand, "workload": "infer"}, cat)["proposed_gpu"] == "MI300X"


def test_reasoning_below_cap_saves_zero(results):
    b = results[1]["reasoning"]
    assert b["groups"][1]["request_share"] < 0.1
    assert b["saved_usd"] == b["saved_wh"] == b["changed_requests"] == 0


def test_reasoning_over_cap_keeps_money_and_tokens():
    rows = [{"input_tokens": "1000", "output_tokens": "1000", "is_reasoning": str(int(i < 10)),
             "cost": 1.0} for i in range(20)]
    b = m2.reasoning_budget(rows)
    assert b["changed_requests"] == 8 and b["after_reasoning_requests"] == 2
    assert b["saved_wh"] == pytest.approx(8 * 2 * 0.3 * 79)
    assert b["before_cost"] == b["after_cost"] == 20
    assert sum(g["tokens"] for g in b["groups"].values()) == 40000
    assert m2.reasoning_budget([])["saved_wh"] == 0


def test_stages_and_allocation_reconcile(results):
    r2, r4 = results[1], results[3]
    costs = [s["daily_cost"] for s in r2["stages"]]
    assert costs == sorted(costs, reverse=True)
    assert sum(a-b for a,b in zip(costs, costs[1:])) == pytest.approx(costs[0]-costs[-1])
    assert sum(r4["by_team"].values()) == pytest.approx(r2["optimized_daily"])
    assert sum(r4["by_project"].values()) == pytest.approx(r2["optimized_daily"])
    with (ROOT / "outputs/focus_export.csv").open(encoding="utf-8", newline="") as f:
        exported = list(csv.DictReader(f))
    assert len(exported) == r2["requests"] == 2400
    assert len({r["ResourceId"] for r in exported}) == 2400
    assert sum(float(r["BilledCost"]) for r in exported) == pytest.approx(r2["optimized_daily"])


def test_carbon_same_work_actual_days_and_regions(results):
    r3 = results[2]
    assert sum(r["gpu_hours"] for r in r3["carbon_jobs"]) == 2918
    assert sum(r["wh"] for r in r3["carbon_jobs"]) == 1789000
    assert r3["carbon_saved_g"] == pytest.approx(626150)
    assert r3["cleanest_region"] != r3["cheapest_region"]
    assert min(r3["regions"], key=lambda r:r["carbon_g"])["region"] == r3["cleanest_region"]
    assert min(r3["regions"], key=lambda r:r["energy_usd"])["region"] == r3["cheapest_region"]


def test_sequential_savings_no_double_count(results):
    r5 = results[4]
    assert r5["baseline_monthly"] - r5["optimized_monthly"] == pytest.approx(sum(r5["levers"].values()))
    adjustments = r5["adjustments"]
    assert len({r["gpu_id"] for r in adjustments}) == len(adjustments)
    assert all(r["idle_savings"] == 0 for r in adjustments if r["tier"] == "reserved")
    by_job = {}
    for r in adjustments:
        by_job[r["assumed_job_id"]] = by_job.get(r["assumed_job_id"], 0) + r["idle_savings"] + r["rightsize_savings"]
    for r in results[2]["recommendations"]:
        assert by_job.get(r["job_id"], 0) <= r["optimized"]


def test_utf8_reports_and_png(results):
    for name in ("report.md", "writeup.md"):
        content = (ROOT / "outputs" / name).read_text(encoding="utf-8")
        assert "\ufffd" not in content and "$$" not in content
    assert (ROOT / "outputs/savings.png").read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
