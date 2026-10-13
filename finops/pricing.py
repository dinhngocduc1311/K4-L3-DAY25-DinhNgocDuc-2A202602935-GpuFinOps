"""Pricing & purchasing economics — measure in $/1M-token, not $/GPU-hr.

Figures are June-2026 as-of snapshots from the deck's RESEARCH dossier; treat
live prices as fast-moving (re-baseline before each cohort).
"""
from __future__ import annotations
import math

# Lab assumptions: interruption events per productive GPU-hour, not live market data.
INTERRUPTION_RATES = {"H100": 0.04, "H200": 0.05, "A100": 0.06,
                      "A10G": 0.12, "L4": 0.08, "B200": 0.05, "MI300X": 0.07}


def cache_break_even_reads(write_cost_per_m: float, price_in_per_m: float,
                           read_discount: float = 0.10) -> float:
    """Reads/write needed to recover an additional cache-write price ($/1M tokens)."""
    if any(x < 0 or not math.isfinite(x) for x in (write_cost_per_m, price_in_per_m)) or not 0 <= read_discount <= 1:
        raise ValueError("Cache prices must be nonnegative and discount within 0..1")
    saving = price_in_per_m * (1 - read_discount)
    return write_cost_per_m / saving if saving else math.inf


def cache_is_worth_it(avg_cache_reads: float, write_cost_per_m: float,
                     read_discount: float = 0.10, price_in_per_m: float = 1.0) -> bool:
    """Enable cache only when read savings cover additional writes, in the same units."""
    if avg_cache_reads < 0 or not math.isfinite(avg_cache_reads):
        raise ValueError("Cache reads must be nonnegative")
    return avg_cache_reads > 0 and avg_cache_reads >= cache_break_even_reads(
        write_cost_per_m, price_in_per_m, read_discount)


def request_cost(
    input_tok: int,
    output_tok: int,
    price_in_per_m: float,
    price_out_per_m: float,
    cached_in: int = 0,
    cache_discount: float = 0.10,   # lab cached-read multiplier (90% off)
    batch: bool = False,
    batch_discount: float = 0.50,   # lab batch multiplier (50% off)
) -> float:
    """USD cost of a single request. Cached input billed at cache_discount x price."""
    if any(x < 0 or not math.isfinite(x) for x in
           (input_tok, output_tok, price_in_per_m, price_out_per_m)):
        raise ValueError("Token counts and prices must be finite and nonnegative")
    if not 0 <= cache_discount <= 1 or not 0 <= batch_discount <= 1:
        raise ValueError("Discount multipliers must be within 0..1")
    cached_in = min(max(0, cached_in), input_tok)
    uncached_in = input_tok - cached_in
    cost = (
        (uncached_in / 1e6) * price_in_per_m
        + (cached_in / 1e6) * price_in_per_m * cache_discount
        + (output_tok / 1e6) * price_out_per_m
    )
    if batch:
        cost *= batch_discount
    return cost


def dollars_per_million(total_cost_usd: float, total_tokens: int) -> float:
    """Aggregate unit economics: $ per 1,000,000 tokens served."""
    if total_tokens <= 0:
        return 0.0
    return total_cost_usd / (total_tokens / 1e6)


def discount_stack(
    batch: bool = False,
    cache_hit_frac: float = 0.0,
    batch_discount: float = 0.50,
    cache_discount: float = 0.10,
) -> float:
    """Effective fraction of the naive bill after stacking discounts (input-heavy view).

    Discounts MULTIPLY: cache applies to the cached share of input, batch to the
    whole bill. batch + 100% cache-hit -> 0.5 * 0.1 = 0.05 (~95% off).
    """
    cache_mult = cache_hit_frac * cache_discount + (1.0 - cache_hit_frac)
    batch_mult = batch_discount if batch else 1.0
    return cache_mult * batch_mult


def break_even_utilization(discount_frac: float) -> float:
    """Utilization at which a commitment pays off ~= 1 - discount.

    A 45% reserved discount needs ~55% utilization (~13.2h/day) to beat on-demand.
    """
    return max(0.0, min(1.0, 1.0 - discount_frac))


def recommend_tier(hours_per_day: float, interruptible: bool, reserved_discount: float = 0.45,
                   gpu_type: str | None = None, job_days: float | None = None,
                   prices: dict | None = None) -> str:
    """Compare actual-duration costs when prices/days are supplied; otherwise use lab policy.

    DOCUMENTED simple policy (instructor extension point — swap in your own):
      - interruptible & not 24/7  -> 'spot'      (checkpoint and ride the discount)
      - duty cycle >= break-even  -> 'reserved'  (steady, high utilization)
      - otherwise                 -> 'on_demand' (spiky / low duty)
    """
    if not 0 <= hours_per_day <= 24:
        raise ValueError("hours_per_day must be within 0..24")
    if prices is not None and job_days is not None:
        costs = tier_costs(hours_per_day, interruptible, gpu_type, job_days, prices)
        return min(costs, key=costs.get)
    duty = hours_per_day / 24.0
    be = break_even_utilization(reserved_discount)
    if interruptible and hours_per_day < 24:
        return "spot"
    if duty >= be:
        return "reserved"
    return "on_demand"


def tier_costs(hours_per_day: float, interruptible: bool, gpu_type: str | None,
               job_days: float, prices: dict) -> dict:
    """Per-GPU costs over actual job duration, including the entire new commitment.

    No resale or reuse after the job is assumed. Reserved bills all 24 hours,
    including unused days through the 365/1095-day term; longer jobs renew terms.
    """
    if not 0 <= hours_per_day <= 24 or job_days < 0 or not math.isfinite(job_days):
        raise ValueError("Invalid workload duration")
    hours = hours_per_day * job_days
    od = float(prices["on_demand_hr"])
    costs = {"on_demand": hours * od}
    if interruptible:
        costs["spot"] = spot_checkpoint_cost(
            hours, float(prices["spot_hr"]), od,
            interrupt_rate=INTERRUPTION_RATES.get(gpu_type, 0.05))["spot_cost"]
    for years, term in ((1, 365), (3, 1095)):
        costs[f"reserved_{years}yr"] = (
            math.ceil(job_days / term) * term * 24 * float(prices[f"reserved_{years}yr_hr"]))
    return costs


def spot_checkpoint_cost(
    job_hours: float,
    spot_hr: float,
    on_demand_hr: float,
    interrupt_rate: float = 0.05,      # assumed interruption events per productive GPU-hour
    ckpt_overhead_frac: float = 0.03,  # steady cost of writing checkpoints
    rework_hours_per_interrupt: float = 0.5,
) -> dict:
    """Effective cost of running a checkpointable job on spot vs on-demand.

    Interruptions waste the compute since the last checkpoint (rework); checkpointing
    adds a small steady overhead. Spot still wins for interruptible jobs.
    """
    if any(x < 0 or not math.isfinite(x) for x in (job_hours, spot_hr, on_demand_hr, interrupt_rate,
                           ckpt_overhead_frac, rework_hours_per_interrupt)):
        raise ValueError("Spot duration, rates and overhead must be nonnegative")
    expected_interrupts = job_hours * interrupt_rate
    rework_hours = expected_interrupts * rework_hours_per_interrupt
    effective_hours = job_hours * (1.0 + ckpt_overhead_frac) + rework_hours
    spot_cost = effective_hours * spot_hr
    on_demand_cost = job_hours * on_demand_hr
    savings_pct = (1.0 - spot_cost / on_demand_cost) * 100.0 if on_demand_cost > 0 else 0.0
    return {
        "spot_effective_hours": effective_hours,
        "spot_cost": spot_cost,
        "on_demand_cost": on_demand_cost,
        "savings_pct": savings_pct,
    }
