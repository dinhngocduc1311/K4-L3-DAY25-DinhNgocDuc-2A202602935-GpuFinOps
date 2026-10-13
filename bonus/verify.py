"""Validate bonus artifacts; optionally check running Docker and completed CPU benchmark.

Run from the repository root: python bonus/verify.py --docker --model
This does not start/stop Docker or download a model.
"""
from __future__ import annotations
import argparse
import base64
import csv
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from bonus.docker import exporter
from bonus.litellm_tracker.demo import main as tracker_demo


def fetch_json(url, credentials=None):
    request = urllib.request.Request(url)
    if credentials is not None:
        auth = base64.b64encode(credentials.encode()).decode()
        request.add_header("Authorization", "Basic " + auth)
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.load(response)


def check_docker():
    prom = "http://127.0.0.1:" + os.environ.get("PROMETHEUS_PORT", "9090")
    grafana = "http://127.0.0.1:" + os.environ.get("GRAFANA_PORT", "3000")
    targets = fetch_json(prom + "/api/v1/targets")
    assert any(t["health"] == "up" and t["labels"].get("job") == "gpu-cost-exporter"
               for t in targets["data"]["activeTargets"]), "Exporter target not UP"
    series = fetch_json(prom + "/api/v1/query?query=gpu_mfu")
    assert series["status"] == "success" and len(series["data"]["result"]) == 11
    duration = fetch_json(prom + "/api/v1/query?query=gpu_idle_seconds")
    assert len(duration["data"]["result"]) == 11
    assert sum(float(r["value"][1]) for r in duration["data"]["result"]) == 8 * 3600
    idle = fetch_json(prom + "/api/v1/query?query=sum%28gpu_idle_cost_usd%29")
    assert math.isclose(float(idle["data"]["result"][0]["value"][1]), 20)
    credentials = "admin:" + os.environ.get("GRAFANA_ADMIN_PASSWORD", "admin")
    dashboard = fetch_json(grafana + "/api/dashboards/uid/lab25-gpu-cost", credentials)
    assert len(dashboard["dashboard"]["panels"]) == 9
    datasource = fetch_json(grafana + "/api/datasources/uid/lab25-prometheus", credentials)
    assert datasource["type"] == "prometheus"
    health = fetch_json(grafana + "/api/datasources/uid/lab25-prometheus/health", credentials)
    assert health["status"] == "OK", "Grafana datasource cannot reach Prometheus"
    return {"status": "completed", "exporter_target": "up", "mfu_series": 11,
            "idle_cost_usd_snapshot": 20, "dashboard_uid": "lab25-gpu-cost", "panels": 9,
            "datasource_uid": "lab25-prometheus"}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--docker", action="store_true", help="Require live Prometheus/Grafana checks")
    parser.add_argument("--model", action="store_true", help="Require a successful saved CPU benchmark")
    args = parser.parse_args(argv)
    out = ROOT / "outputs/bonus"
    out.mkdir(parents=True, exist_ok=True)
    result = {"tracker": tracker_demo()}
    result["verified_at_utc"] = datetime.now(timezone.utc).isoformat()
    with (out / "tracker_requests.csv").open(encoding="utf-8", newline="") as f:
        ledger = list(csv.DictReader(f))
    assert math.isclose(sum(float(r["cost"]) for r in ledger), sum(result["tracker"]["spend_usd"].values()))
    metrics = exporter.render()
    assert metrics.count("gpu_mfu{") == metrics.count("gpu_mbu{") == 11
    (out / "prometheus_metrics.txt").write_bytes(metrics.encode("utf-8"))
    result["exporter"] = {"status": "completed", "metric_families": 8, "gpu_series_per_family": 11}
    if args.docker:
        result["docker"] = check_docker()
    if args.model:
        benchmark = json.loads((out / "local_benchmark.json").read_text(encoding="utf-8"))
        assert benchmark["status"] == "completed", "CPU benchmark did not run successfully"
        assert benchmark["device"] == "cpu" and len(benchmark["runs"]) >= 1
        assert benchmark["total_output_tokens"] > 0 and benchmark["tokens_per_second"] > 0
        result["model"] = {"status": "completed", "model": benchmark["model"],
                           "output_tokens": benchmark["total_output_tokens"],
                           "tokens_per_second": benchmark["tokens_per_second"],
                           "estimated_usd_per_million_output_tokens": benchmark["usd_per_million_output_tokens"]}
    sections = ["# Kết quả bonus — GPU FinOps", "",
                "Các số dưới đây được tạo từ lần chạy thực tế, độc lập với hóa đơn M1–M5.", "",
                "## 1. Tracker mock và budget cap", "",
                f"- Chat spend: {result['tracker']['spend_usd']['team-chat']:.6f} USD; cap 0.05 USD.",
                f"- Eval spend: {result['tracker']['spend_usd']['team-eval']:.6f} USD.",
                f"- {len(ledger)} request được log; request vượt cap bị chặn, tổng ledger khớp spend.",
                "- Budget theo phiên process; đây là mock, input token ước lượng và output theo limit.", "",
                "## 2. Exporter snapshot", "",
                "- 8 nhóm metric × 11 GPU; artifact: prometheus_metrics.txt.",
                "- MFU/MBU/util/power và giá/idle từ CSV; không phải telemetry live.",
                "- (1-MFU) × rate là diagnostic unused compute, không phải savings thu hồi."]
    if args.docker:
        sections += ["", "## 3. Docker kiểm tra HTTP thật", "",
                     "- Exporter target UP; Prometheus có 11 MFU series, idle cost snapshot = 20 USD.",
                     "- Grafana datasource lab25-prometheus và dashboard lab25-gpu-cost: 9 panel.",
                     "- Ports chỉ bind localhost; stack có thể dừng bằng docker compose ... down."]
    if args.model:
        b = benchmark
        sections += ["", "## 4. Model thật trên CPU", "",
                     f"- Model: {b['model']}; revision: {b['model_revision']}.",
                     f"- Python {b['python']}; torch {b['torch']}; transformers {b['transformers']}.",
                     f"- {len(b['runs'])} lần đo sau {b['warmup_runs']} warm-up; {b['threads']} thread; "
                     f"tổng {b['total_output_tokens']} output tokens.",
                     f"- Throughput tổng hợp: {b['tokens_per_second']:.2f} output tok/s; "
                     f"median {b['median_tokens_per_second']:.2f}.",
                     f"- Giả định CPU {b['cpu_rate_usd_hr_assumption']:.2f} USD/h: "
                     f"{b['usd_per_million_output_tokens']:.6f} USD/1M output token.",
                     f"- Lab small model output-only: {b['simulation_small_output_usd_per_m']:.2f} USD/1M. "
                     f"M2 input+output: {b['simulation_m2_input_plus_output_usd_per_m']:.6f} USD/1M.",
                     "- Model tiny không có chất lượng tương đương production; giá CPU là giả định; "
                     "không gồm load, warm-up và idle capacity."]
    sections += ["", "Xem validation.json, tracker_requests.csv, tracker_summary.json và local_benchmark.json "
                 "cho chi tiết. Các phần Docker/model chỉ được xác nhận khi verifier chạy với --docker/--model.", ""]
    (out / "report.md").write_text("\n".join(sections), encoding="utf-8")
    (out / "validation.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print("Bonus validation passed:", ", ".join(k for k in result if k != "verified_at_utc"))
    print("Written: outputs/bonus/validation.json + report.md + prometheus_metrics.txt")
    return 0


if __name__ == "__main__":
    sys.exit(main())
