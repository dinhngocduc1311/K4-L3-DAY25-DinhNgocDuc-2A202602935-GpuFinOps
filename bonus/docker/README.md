# Bonus — Prometheus + Grafana theo dõi GPU cost

Stack đọc **CSV synthetic seed=25** và replay giá trị trung bình của snapshot 24h.
Đây là telemetry lịch sử, không phải DCGM trực tiếp; đường time-series ổn định là đúng với dữ liệu này.

Chạy từ root project, đã sinh dữ liệu và Docker Desktop/Engine đang hoạt động:

```bash
python data/generate.py
docker compose -f bonus/docker/docker-compose.yml config --quiet
docker compose -f bonus/docker/docker-compose.yml up -d --wait --wait-timeout 90
docker compose -f bonus/docker/docker-compose.yml ps
python bonus/verify.py --docker
```

- Exporter: http://127.0.0.1:9101/metrics ; health: http://127.0.0.1:9101/healthz .
- Prometheus: http://127.0.0.1:9090 ; target `gpu-cost-exporter` phải UP.
- Grafana: http://127.0.0.1:3000 ; demo login admin/admin.
- Dashboard **GPU Cost & Efficiency** trong folder **GPU FinOps Lab**, UID `lab25-gpu-cost`.

Compose chỉ bind port ra localhost; anonymous Grafana tắt. Password demo có thể đổi bằng
`GRAFANA_ADMIN_PASSWORD` trước khi khởi tạo container; không commit password. Dùng cùng biến khi chạy bonus verifier.
Có thể đổi port bằng `EXPORTER_PORT`, `PROMETHEUS_PORT`, `GRAFANA_PORT`.
Images Prometheus v3.5.0 và Grafana 12.1.0 được cố định để tái lập bản lab; không coi đây là bản production đã harden.

Dashboard có text giải thích và tám panel, datasource UID `lab25-prometheus` được provisioning tự động:

| Metric | Ý nghĩa / đơn vị |
|---|---|
| gpu_util_pct | % thời gian GPU có hoạt động, mean snapshot |
| gpu_mfu | MFU 0..1, mean snapshot |
| gpu_mbu | MBU 0..1, mean snapshot |
| gpu_power_watts | Power mean của telemetry synthetic, W |
| gpu_hourly_cost_usd | Catalog on-demand, USD/GPU-hour |
| gpu_wasted_cost_usd_per_hr | (1-MFU) × rate: diagnostic unused compute capacity |
| gpu_idle_seconds | Thời gian idle util <10% trong snapshot, giây (đơn vị cơ sở Prometheus) |
| gpu_idle_cost_usd | Idle hours × on-demand rate của snapshot |

**Diagnostic unused compute không phải tiền có thể thu hồi.** Inference memory-bound vẫn có ích khi MFU thấp;
xem MBU và benchmark. Idle cost của snapshot không cộng thêm vào waterfall đã có purchasing/idle/right-sizing.
[Report chính](../../outputs/report.md) giải thích savings tuần tự và các giả định.

Không có Docker vẫn chạy exporter thuần stdlib:

```bash
python bonus/docker/exporter.py
```

Exporter mặc định bind 127.0.0.1; trong container Compose đặt BIND_HOST=0.0.0.0.
HTTP /metrics trả text Prometheus UTF-8, escape label đúng, clamp utilization,
trả 404 cho endpoint lạ và 503 khi dữ liệu thiếu/không hợp lệ.
Prometheus scrape mỗi 10s; exporter đọc lại CSV mỗi scrape.

Dừng đúng stack bonus khi demo xong:

```bash
docker compose -f bonus/docker/docker-compose.yml down
```

Nếu lỗi: kiểm tra Docker đang chạy, port trùng, `docker compose ... logs`, target Prometheus và Grafana datasource.
Verifier kiểm tra HTTP thực: target UP, 11 MFU series, tổng idle cost=20 USD,
dashboard 9 panel và datasource được provisioning. Bonus tests cũng kiểm tra HTTP exporter cục bộ:

```bash
pytest -q checks/test_bonus.py
```

Nguồn định dạng: [Prometheus exposition](https://prometheus.io/docs/instrumenting/exposition_formats/),
[Grafana provisioning](https://grafana.com/docs/grafana/latest/administration/provisioning/).
