"""Demo: per-key $/request tracking + a hard budget stop. Run: python demo.py"""
from pathlib import Path
import json
import math
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from bonus.litellm_tracker.tracker import CostTracker, BudgetExceeded

def main():
    t = CostTracker(budgets={"team-chat": 0.05, "team-eval": 100.0})
    blocked = False
    for i in range(40):
        try:
            t.complete("team-chat", "large", "Summarize this very long document " * 30)
        except BudgetExceeded as e:
            blocked = True
            print(f"BLOCKED after {i} chat requests: {e}")
            break
    for _ in range(5):
        t.complete("team-eval", "small", "classify: positive or negative?", batch=True)
    spend = t.report()
    assert blocked and spend["team-chat"] <= 0.05
    assert math.isclose(sum(r["cost"] for r in t.log), sum(spend.values()))
    out = Path(__file__).resolve().parents[2] / "outputs" / "bonus"
    t.export_csv(out / "tracker_requests.csv")
    summary = {"backend": "mock", "period": "process session", "blocked": blocked,
               "requests_logged": len(t.log), "budgets_usd": t.budgets, "spend_usd": spend}
    (out / "tracker_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print("per-key spend:", {k: round(v, 6) for k, v in spend.items()})
    print("requests logged:", len(t.log))
    print("Written: outputs/bonus/tracker_requests.csv + tracker_summary.json")
    return summary


if __name__ == "__main__":
    main()
