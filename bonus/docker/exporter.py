"""Replay hourly synthetic GPU telemetry as Prometheus gauges; stdlib only."""
from __future__ import annotations
import csv
import math
import os
from collections import defaultdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

DATA_DIR = os.environ.get("LAB_DATA_DIR", str((Path(__file__).resolve().parent / "../../data").resolve()))


def _number(value):
    result = float(value)
    if not math.isfinite(result) or result < 0:
        raise ValueError("Telemetry and catalog values must be finite and nonnegative")
    return result


def _ratio(achieved, peak):
    return min(1.0, achieved / peak) if peak > 0 else 0.0


def _label(value):
    return str(value).replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


def _load():
    with (Path(DATA_DIR) / "price_catalog.csv").open(encoding="utf-8", newline="") as f:
        cat = {r["gpu_type"]: r for r in csv.DictReader(f)}
    agg = defaultdict(lambda: {"util": [], "mfu": [], "mbu": [], "power": [], "idle": 0, "type": None})
    with (Path(DATA_DIR) / "gpu_telemetry.csv").open(encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            a = agg[r["gpu_id"]]
            a["type"] = r["gpu_type"]
            c = cat[r["gpu_type"]]
            util = min(100.0, _number(r["gpu_util_pct"]))
            a["util"].append(util)
            a["mfu"].append(_ratio(_number(r["achieved_tflops"]), _number(c["peak_tflops_fp16"])))
            a["mbu"].append(_ratio(_number(r["achieved_bw_tbs"]), _number(c["peak_bw_tbs"])))
            a["power"].append(_number(r["power_w"]))
            a["idle"] += int(util < 10)  # Each row is one hour in the lab.
    if not agg:
        raise ValueError("No telemetry samples available")
    return cat, agg


def render() -> str:
    cat, agg = _load()
    definitions = {
        "gpu_util_pct": "Time-active utilization, mean of the historical snapshot (0..100)",
        "gpu_mfu": "Model FLOPs utilization, historical mean (0..1)",
        "gpu_mbu": "Model bandwidth utilization, historical mean (0..1)",
        "gpu_power_watts": "Measured synthetic GPU power, historical mean watts",
        "gpu_hourly_cost_usd": "Catalog on-demand USD per GPU-hour",
        "gpu_wasted_cost_usd_per_hr": "Unused compute-capacity diagnostic (1-MFU)*rate; not realizable savings",
        "gpu_idle_seconds": "Idle duration in the observed snapshot, GPU utilization below 10 percent",
        "gpu_idle_cost_usd": "On-demand idle cost over the observed snapshot, not an additional lever",
    }
    out = []
    for name, help_text in definitions.items():
        out += [f"# HELP {name} {help_text}", f"# TYPE {name} gauge"]
    for gid, a in sorted(agg.items()):
        gtype = a["type"]
        mean = lambda key: sum(a[key]) / len(a[key])
        rate = _number(cat[gtype]["on_demand_hr"])
        values = {"gpu_util_pct": mean("util"), "gpu_mfu": mean("mfu"), "gpu_mbu": mean("mbu"),
                  "gpu_power_watts": mean("power"), "gpu_hourly_cost_usd": rate,
                  "gpu_wasted_cost_usd_per_hr": (1-mean("mfu")) * rate,
                  "gpu_idle_seconds": a["idle"] * 3600, "gpu_idle_cost_usd": a["idle"] * rate}
        labels = gpu_labels(gid, gtype)
        for name, value in values.items():
            out.append(f"{name}{labels} {value:.8g}")
    return "\n".join(out) + "\n"


def gpu_labels(gid, gtype):
    return '{gpu_id="' + _label(gid) + '",gpu_type="' + _label(gtype) + '"}'


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path not in ("/metrics", "/healthz"):
            self.send_error(404)
            return
        try:
            metrics = render()
            body = (metrics if self.path == "/metrics" else "ok\n").encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
        except (OSError, ValueError, KeyError):
            body = b"Telemetry unavailable; check LAB_DATA_DIR and input CSVs.\n"
            self.send_response(503)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    host, port = os.environ.get("BIND_HOST", "127.0.0.1"), int(os.environ.get("PORT", "9101"))
    print(f"GPU snapshot exporter on {host}:{port}/metrics (data: {DATA_DIR})")
    server = ThreadingHTTPServer((host, port), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
