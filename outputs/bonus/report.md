# Kết quả bonus — GPU FinOps

Các số dưới đây được tạo từ lần chạy thực tế, độc lập với hóa đơn M1–M5.

## 1. Tracker mock và budget cap

- Chat spend: 0.046050 USD; cap 0.05 USD.
- Eval spend: 0.000260 USD.
- 15 request được log; request vượt cap bị chặn, tổng ledger khớp spend.
- Budget theo phiên process; đây là mock, input token ước lượng và output theo limit.

## 2. Exporter snapshot

- 8 nhóm metric × 11 GPU; artifact: prometheus_metrics.txt.
- MFU/MBU/util/power và giá/idle từ CSV; không phải telemetry live.
- (1-MFU) × rate là diagnostic unused compute, không phải savings thu hồi.

## 3. Docker kiểm tra HTTP thật

- Exporter target UP; Prometheus có 11 MFU series, idle cost snapshot = 20 USD.
- Grafana datasource lab25-prometheus và dashboard lab25-gpu-cost: 9 panel.
- Ports chỉ bind localhost; stack có thể dừng bằng docker compose ... down.

## 4. Model thật trên CPU

- Model: sshleifer/tiny-gpt2; revision: 5f91d94bd9cd7190a9f3216ff93cd1dd95f2c7be.
- Python 3.11.9; torch 2.14.1+cpu; transformers 5.19.0.
- 3 lần đo sau 1 warm-up; 1 thread; tổng 192 output tokens.
- Throughput tổng hợp: 185.29 output tok/s; median 199.19.
- Giả định CPU 0.10 USD/h: 0.149919 USD/1M output token.
- Lab small model output-only: 0.40 USD/1M. M2 input+output: 1.181472 USD/1M.
- Model tiny không có chất lượng tương đương production; giá CPU là giả định; không gồm load, warm-up và idle capacity.

Xem validation.json, tracker_requests.csv, tracker_summary.json và local_benchmark.json cho chi tiết. Các phần Docker/model chỉ được xác nhận khi verifier chạy với --docker/--model.
