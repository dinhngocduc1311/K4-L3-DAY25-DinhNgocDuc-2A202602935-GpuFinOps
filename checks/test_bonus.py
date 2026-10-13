"""Bonus tests run without Docker or model downloads: pytest -q checks/test_bonus.py."""
import csv
from concurrent.futures import ThreadPoolExecutor
import json
import math
import runpy
from pathlib import Path
import sys
from threading import Thread
from urllib.error import HTTPError
from urllib.request import urlopen
from http.server import ThreadingHTTPServer

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from bonus.litellm_tracker.tracker import CostTracker, BudgetExceeded
from bonus.local_model import run_local
from bonus.docker import exporter
from finops.pricing import request_cost


@pytest.mark.parametrize("cap", [-1, float("nan"), float("inf")])
def test_invalid_budget(cap):
    with pytest.raises(ValueError):
        CostTracker({"team": cap})


@pytest.mark.parametrize("kwargs", [{"max_output_tokens": -1}, {"cached_input_tokens": -1},
                                    {"max_output_tokens": 1.5}, {"batch": "false"}])
def test_tracker_bad_tokens_do_not_change_spend(kwargs):
    t = CostTracker({"team": 1})
    with pytest.raises(ValueError):
        t.complete("team", "small", "hello", **kwargs)
    assert not t.log and not t.report()


def test_budget_exact_boundary_then_reject():
    cost = request_cost(1, 1, 0.2, 0.4)
    t = CostTracker({"team": cost})
    rec = t.complete("team", "small", "a", max_output_tokens=1)
    rec["cost"] = -99  # Returned objects cannot corrupt the ledger.
    with pytest.raises(BudgetExceeded):
        t.complete("team", "small", "a", max_output_tokens=1)
    assert t.report()["team"] == cost and t.log[0]["cost"] == cost
    assert len(t.log) == 1


def test_tracker_concurrent_requests_never_exceed_cap():
    cost = request_cost(1, 1, 0.2, 0.4)
    t = CostTracker({"team": cost * 5})
    def attempt(_):
        try:
            t.complete("team", "small", "a", max_output_tokens=1)
        except BudgetExceeded:
            pass
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(attempt, range(30)))
    assert 1 <= len(t.log) <= 5 and t.report()["team"] <= t.budgets["team"]


def test_tracker_discount_export_and_isolated_teams(tmp_path):
    t = CostTracker({"blocked": 0})
    with pytest.raises(BudgetExceeded):
        t.complete("blocked", "small", "hello")
    rec = t.complete("free", "large", "a" * 4000, cached_input_tokens=1000, batch=True)
    assert rec["cost"] == request_cost(1000, 256, 3, 15, cached_in=1000, batch=True)
    path = t.export_csv(tmp_path / "ledger.csv")
    with path.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    assert math.isclose(sum(float(r["cost"]) for r in rows),sum(t.report().values()))
    assert set(t.report()) == {"free"}


def test_local_output_economics_and_reject_zero_tokens():
    r = run_local.unit_economics(100, 10, 0.1)
    assert r["tokens_per_second"] == 10
    assert r["usd_per_million_output_tokens"] == pytest.approx(10/3600*0.1/100*1e6)
    for tokens, seconds, rate in [(0, 1, 1), (1, 0, 1), (1, 1, -1), (1, float("nan"), 1)]:
        with pytest.raises(ValueError):
            run_local.unit_economics(tokens, seconds, rate)


def test_local_missing_dependency_skip_and_strict(monkeypatch, tmp_path):
    monkeypatch.setitem(sys.modules, "torch", None)
    output = tmp_path / "benchmark.json"
    assert run_local.main(["--output", str(output)]) == 0
    assert json.loads(output.read_text(encoding="utf-8"))["status"] == "skipped"
    assert run_local.main(["--strict", "--output", str(output)]) == 1


def test_local_invalid_options(tmp_path):
    with pytest.raises(SystemExit) as exc:
        run_local.main(["--runs", "0", "--output", str(tmp_path / "unused.json")])
    assert exc.value.code == 2


def test_exporter_snapshot_matches_mission_and_escapes_labels():
    text = exporter.render()
    assert text.count("# TYPE ") == 8 and text.count("gpu_mfu{") == 11
    idle = [float(line.rsplit(" ", 1)[1]) for line in text.splitlines() if line.startswith("gpu_idle_cost_usd{")]
    assert sum(idle) == 20
    duration = [float(line.rsplit(" ", 1)[1]) for line in text.splitlines() if line.startswith("gpu_idle_seconds{")]
    assert sum(duration) == 8 * 3600
    assert exporter._ratio(2000, 990) == 1 and exporter._ratio(100, 0) == 0
    assert exporter._label('a"b\\c\nd') == 'a\\"b\\\\c\\nd'


def test_exporter_http_and_unavailable_data(monkeypatch, tmp_path):
    server = ThreadingHTTPServer(("127.0.0.1", 0), exporter.Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        with urlopen(base + "/metrics", timeout=3) as r:
            assert r.status == 200 and "version=0.0.4" in r.headers["Content-Type"]
            assert b"gpu_mbu{" in r.read()
        with pytest.raises(HTTPError) as exc:
            urlopen(base + "/unknown", timeout=3)
        assert exc.value.code == 404
        monkeypatch.setattr(exporter, "DATA_DIR", str(tmp_path))
        with pytest.raises(HTTPError) as exc:
            urlopen(base + "/healthz", timeout=3)
        assert exc.value.code == 503
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def test_grafana_panels_reference_exported_metrics(monkeypatch, tmp_path):
    config = json.loads((ROOT / "bonus/docker/grafana/dashboards/gpu_cost.json").read_text(encoding="utf-8"))
    assert config["uid"] == "lab25-gpu-cost" and len(config["panels"]) == 9
    text = exporter.render()
    for panel in config["panels"]:
        if panel["type"] == "text":
            continue
        assert panel["datasource"]["uid"] == "lab25-prometheus"
        for target in panel["targets"]:
            assert "# TYPE " + target["expr"] + " gauge" in text
    # Container mounts /app/exporter.py: don't assume three filesystem parents.
    script = tmp_path / "exporter.py"
    script.write_text((ROOT / "bonus/docker/exporter.py").read_text(encoding="utf-8"), encoding="utf-8")
    monkeypatch.setenv("LAB_DATA_DIR", str(ROOT / "data"))
    relocated = runpy.run_path(str(script), run_name="exporter_check")
    assert relocated["render"]().count("gpu_mbu{") == 11
