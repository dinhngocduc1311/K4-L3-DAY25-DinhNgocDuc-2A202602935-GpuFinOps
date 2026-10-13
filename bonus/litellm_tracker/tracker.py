"""A tiny LiteLLM-style token-cost tracker with per-API-key budget caps.

The §10 "token tier" of cost observability: attribute $/request per key/team and
HARD-STOP requests that would blow the budget. Mock backend — no API key needed.
"""
from __future__ import annotations
import csv
import math
import os, sys, time
from pathlib import Path
from threading import Lock
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from finops import pricing
from missions.m2_inference_levers import MODEL_PRICES


class BudgetExceeded(Exception):
    pass


class CostTracker:
    def __init__(self, budgets: dict | None = None):
        self.budgets = dict(budgets or {})    # key alias -> USD cap for this session
        if any(not isinstance(k, str) or not k.strip() for k in self.budgets):
            raise ValueError("Budget keys must be non-empty aliases, not provider credentials")
        if any(not math.isfinite(v) or v < 0 for v in self.budgets.values()):
            raise ValueError("Budgets must be finite and nonnegative")
        self.spend = defaultdict(float)       # api_key -> USD spent
        self.log = []
        self._lock = Lock()

    def _estimate_tokens(self, text: str) -> int:
        return max(1, len(text) // 4)         # ~4 chars/token rule of thumb

    def complete(self, api_key: str, model: str, prompt: str,
                 max_output_tokens: int = 256, cached_input_tokens: int = 0,
                 batch: bool = False) -> dict:
        if not isinstance(api_key, str) or not api_key.strip():
            raise ValueError("api_key must be a non-empty alias")
        if model not in MODEL_PRICES:
            raise ValueError(f"Unknown model tier: {model}")
        if not isinstance(prompt, str):
            raise ValueError("prompt must be text")
        for count in (max_output_tokens, cached_input_tokens):
            if isinstance(count, bool) or not isinstance(count, int) or count < 0:
                raise ValueError("Token counts must be nonnegative integers")
        if not isinstance(batch, bool):
            raise ValueError("batch must be boolean")
        in_tok = self._estimate_tokens(prompt)
        out_tok = max_output_tokens
        pin, pout = MODEL_PRICES[model]
        cost = pricing.request_cost(in_tok, out_tok, pin, pout,
                                    cached_in=cached_input_tokens, batch=batch)
        rec = {"ts": time.strftime("%H:%M:%S"), "key": api_key, "model": model,
               "in": in_tok, "out": out_tok, "cost": cost}
        # Keep budget check + debit atomic for calls from multiple threads.
        with self._lock:
            cap = self.budgets.get(api_key)
            next_spend = self.spend.get(api_key, 0.0) + cost
            if cap is not None and next_spend > cap:
                raise BudgetExceeded(f"key={api_key} would spend ${next_spend:.6f} > cap ${cap:.6f}")
            self.spend[api_key] = next_spend
            self.log.append(dict(rec))
        # MOCK: output token count equals the requested limit, not a real provider bill.
        rec["text"] = f"[mock {model}] ok ({in_tok} in / {out_tok} out)"
        return rec

    def report(self) -> dict:
        with self._lock:
            return dict(self.spend)

    def export_csv(self, path: str | Path) -> Path:
        """Export unrounded per-request costs so the ledger reconciles with spend."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            rows = [dict(r) for r in self.log]
        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["ts", "key", "model", "in", "out", "cost"],
                                    lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
        return path
