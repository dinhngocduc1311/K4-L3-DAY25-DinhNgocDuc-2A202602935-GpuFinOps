"""M2: cascade -> economically gated cache (including writes) -> batch."""
from __future__ import annotations
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
from missions._common import load_csv, num
from finops import pricing, sustainability

MODEL_PRICES = {"small": (0.20, 0.40), "large": (3.00, 15.00)}  # Illustrative lab prices.
AVG_CACHE_READS = 4.0  # Assumption: CSV has no prefix ID or reads/write count.
WRITE_PRICE_MULTIPLIER = 1.25  # Additional write fee, outside ordinary input cost.


def price_requests(rows, avg_reads=AVG_CACHE_READS, use_cache=True, use_batch=True):
    """Shared M2/M4 billing including economically gated cache write fees."""
    if avg_reads < 0:
        raise ValueError("avg_reads must be nonnegative")
    priced = []
    for r in rows:
        inp, out = int(num(r["input_tokens"])), int(num(r["output_tokens"]))
        cached = min(inp, max(0, int(num(r["cached_input_tokens"]))))
        batch = use_batch and bool(int(num(r["is_batch"])))
        pin, pout = MODEL_PRICES[r["route_tier"]]
        write_price = pin * WRITE_PRICE_MULTIPLIER
        enabled = use_cache and pricing.cache_is_worth_it(
            avg_reads, write_price, price_in_per_m=pin * (0.5 if batch else 1))
        write_cost = cached / avg_reads / 1e6 * write_price if enabled else 0.0
        cost = pricing.request_cost(inp, out, pin, pout,
                                    cached_in=cached if enabled else 0, batch=batch) + write_cost
        priced.append({**r, "cost": cost, "cache_write_cost": write_cost,
                       "cache_enabled": enabled, "service": "gpu-inference",
                       "resource_id": f"request-{len(priced):04d}"})
    return priced


def reasoning_budget(priced, cap=0.10):
    """Cap counterfactual keeps tokens/model; only changes the energy multiplier.

    Output length proxies priority because confidence/complexity scores are absent.
    Dollar savings stay zero; reduced reasoning energy needs quality validation.
    """
    if not 0 <= cap <= 1:
        raise ValueError("cap must be within 0..1")
    groups = {k: {"requests": 0, "tokens": 0, "cost": 0.0, "wh": 0.0} for k in (0, 1)}
    reasoning = []
    for i, r in enumerate(priced):
        flag = int(num(r["is_reasoning"]))
        tokens = int(num(r["input_tokens"]) + num(r["output_tokens"]))
        g = groups[flag]
        g["requests"] += 1
        g["tokens"] += tokens
        g["cost"] += r["cost"]
        g["wh"] += sustainability.wh_per_query(tokens, is_reasoning=bool(flag))
        if flag:
            reasoning.append((i, tokens, num(r["output_tokens"])))
    reasoning.sort(key=lambda x: (-x[2], x[0]))
    overflow = reasoning[int(len(priced) * cap):]
    saved_wh = sum(sustainability.wh_per_query(t, is_reasoning=True)
                   - sustainability.wh_per_query(t) for _, t, _ in overflow)
    cost = sum(g["cost"] for g in groups.values())
    wh = sum(g["wh"] for g in groups.values())
    tokens = sum(g["tokens"] for g in groups.values())
    for g in groups.values():
        g["request_share"] = g["requests"] / len(priced) if priced else 0
        g["cost_share"] = g["cost"] / cost if cost else 0
        g["energy_share"] = g["wh"] / wh if wh else 0
        g["token_share"] = g["tokens"] / tokens if tokens else 0
    return {"groups": groups, "cap": cap, "changed_requests": len(overflow),
            "before_cost": cost, "after_cost": cost, "saved_usd": 0.0,
            "before_wh": wh, "after_wh": wh - saved_wh, "saved_wh": saved_wh,
            "after_reasoning_requests": len(reasoning) - len(overflow)}


def run(verbose=True):
    rows = load_csv("token_usage.csv")
    tokens = sum(int(num(r["input_tokens"]) + num(r["output_tokens"])) for r in rows)
    base = sum(pricing.request_cost(int(num(r["input_tokens"])), int(num(r["output_tokens"])),
                                   *MODEL_PRICES["large"]) for r in rows)
    cascade = sum(r["cost"] for r in price_requests(rows, use_cache=False, use_batch=False))
    cache = sum(r["cost"] for r in price_requests(rows, use_batch=False))
    priced = price_requests(rows)
    opt = sum(r["cost"] for r in priced)
    original = sum(pricing.request_cost(
        int(num(r["input_tokens"])), int(num(r["output_tokens"])), *MODEL_PRICES[r["route_tier"]],
        cached_in=int(num(r["cached_input_tokens"])), batch=bool(int(num(r["is_batch"])))) for r in rows)
    stages = [{"stage": name, "daily_cost": cost, "per_m": pricing.dollars_per_million(cost, tokens)}
              for name, cost in (("Baseline", base), ("Cascade", cascade),
                                 ("+ Cache incl. writes", cache), ("+ Batch", opt))]
    scenarios = []
    for reads in (0.5, 1.0, 4.0, 20.0):
        sample = price_requests(rows, avg_reads=reads)
        cost = sum(r["cost"] for r in sample)
        scenarios.append({"reads": reads, "enabled_requests": sum(r["cache_enabled"] for r in sample),
                          "daily_cost": cost, "per_m": pricing.dollars_per_million(cost, tokens),
                          "write_cost": sum(r["cache_write_cost"] for r in sample)})
    budget = reasoning_budget(priced)
    pct = (1 - opt / base) * 100 if base else 0
    if verbose:
        print("== M2 Inference Cost Levers ==")
        print(f"requests={len(rows)}  tokens={tokens:,}")
        for s in stages:
            print(f"{s['stage']:22}: ${s['daily_cost']:.4f}/day  ${s['per_m']:.4f}/1M-token")
        print(f"savings: {pct:.1f}% (same tokens; cache write fees included)")
        print(f"discount stack (batch + 100% cached INPUT): {pricing.discount_stack(True, 1.0):.3f}")
        print("Cache assumptions: 4 reads/write; additional write fee = 1.25 x input price.")
        for tier, (pin, _) in MODEL_PRICES.items():
            for batch in (False, True):
                be = pricing.cache_break_even_reads(pin * WRITE_PRICE_MULTIPLIER, pin * (0.5 if batch else 1))
                print(f"  {tier}, batch={batch}: break-even {be:.3f} reads/write")
        for s in scenarios:
            print(f"  reads={s['reads']}: enabled={s['enabled_requests']}, "
                  f"${s['daily_cost']:.4f}/day, ${s['per_m']:.4f}/1M-token")
        for flag, g in budget["groups"].items():
            print(f"reasoning={flag}: requests={g['requests']} ({g['request_share']:.2%}), "
                  f"tokens={g['tokens']}, cost=${g['cost']:.4f} ({g['cost_share']:.2%}), "
                  f"energy={g['wh']:.2f} Wh ({g['energy_share']:.2%})")
        print(f"10% cap: changed={budget['changed_requests']}; USD {budget['before_cost']:.4f} -> "
              f"{budget['after_cost']:.4f}; Wh {budget['before_wh']:.2f} -> {budget['after_wh']:.2f}")
    return {"baseline_daily": base, "optimized_daily": opt,
            "baseline_per_m": pricing.dollars_per_million(base, tokens),
            "optimized_per_m": pricing.dollars_per_million(opt, tokens),
            "savings_pct": round(pct, 1), "total_tokens": tokens, "requests": len(rows),
            "stages": stages, "cache_scenarios": scenarios, "original_optimized_daily": original,
            "write_cost_daily": sum(r["cache_write_cost"] for r in priced),
            "reasoning": budget, "priced_rows": priced}


if __name__ == "__main__":
    run()
