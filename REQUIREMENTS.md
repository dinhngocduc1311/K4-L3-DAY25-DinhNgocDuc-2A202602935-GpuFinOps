# Đối chiếu yêu cầu — GPU FinOps, Lab 25

Ngày cập nhật: **2026-10-13**. Đề bổ sung được giữ nguyên trong [Practice.md](Practice.md).
Guide/CODELAB/README mô tả cách chạy; Rubric giữ thang điểm 30 + 20 + 30 + 20.
Không tự xác nhận điểm 100/100: phần chấm chất lượng vẫn do giảng viên đánh giá.

| Yêu cầu | Triển khai / bằng chứng | Kiểm tra |
|---|---|---|
| Khám phá 4 CSV, seed cố định | `data/generate.py`; 7 GPU type, 264 telemetry samples, 2.400 request, 8 job | SHA-256 cả bốn CSV khớp baseline trước sửa |
| M1 MFU/MBU và util ≥90%, MFU <0.30 | `finops/metrics.py`, `missions/m1_efficiency_audit.py`; hai GPU bị flag | Tests gốc + report M1 |
| M1 idle giờ và tiền/ngày/tháng | 8h idle, 20 USD/ngày, 600 USD/30 ngày on-demand | Report ghi tỷ lệ 3.90% fleet telemetry |
| M2 request_cost và $/1M-token | `finops/pricing.py`, M2; giữ 7.533.027 token/ngày | 6.487984 → 1.181472 USD/1M-token |
| Đóng góp cascade → cache → batch | Bốn stage tuần tự, cache bao gồm phí ghi | Bảng M2 và check tổng incremental savings |
| M3 tier và checkpoint/rework | Policy cơ bản + policy duration-aware trong `recommend_tier`, `tier_costs` | Có spot/reserved ở kế hoạch pool hiện hữu; actual-days tách riêng |
| M4 team/project, gate 80%, FOCUS-style | M4 dùng chung `price_requests` với M2 | Coverage 91.79%; 2.400 export rows; tổng tiền khớp M2 |
| M5 baseline/optimized, bốn lever | `missions/m5_report.py` | 27,133.62 → 15,352.83 USD/30 ngày; dự kiến 43.42% |
| Tránh cộng trùng savings | Rate sau purchasing, idle trước resize trên giờ còn lại | Reserved không có idle savings; mỗi GPU chỉ tính một lần |
| Sustainability query energy/carbon | Trung bình từ tất cả request, gồm reasoning | 13.20 Wh/query, 5.015 gCO2e/query tại us-east-1 |
| Biểu đồ waterfall | `finops/report.py`, `outputs/savings.png` | Baseline + bốn lever + optimized, PNG đọc được |
| Trả lời Guide 4.3, 5.4, 6.4, 7.4 | `outputs/report.md` theo mission; `outputs/writeup.md` | Số liệu sinh từ cùng kết quả mission |
| ≥2 thay đổi code mở rộng và đo lường | Đã triển khai **5/5** phần bên dưới | Bảng trước/sau, lý do, giả định và checks |
| Baseline trước sửa, dữ liệu giống sau sửa | `outputs/before/baseline.json`, report/chart/export trước sửa | `outputs/after.json` lưu số liệu và hashes mới |
| Verify và tests gốc | `verify.py` vẫn 11 check; giữ nguyên `tests/` | 11/11 checks, 15/15 tests gốc |
| Lệnh mặc định đúng đề | `pytest.ini`: `testpaths = tests` | `pytest -q` chỉ chạy 15 tests gốc; `pytest -q tests checks` chạy tổng 50 |
| Tests tự viết cho logic mới | `checks/test_extensions.py` | 19 checks FinOps + 16 bonus; tổng 50 tests |
| Bài viết 1–2 trang, 3 hành động ưu tiên | `outputs/writeup.md` | Baseline/unit economics, levers, GPU lie, extensions, hành động |
| Bonus tùy chọn, không chấm điểm | Ba thư mục `bonus/` có hướng dẫn riêng | Không cần Docker/GPU/API key cho graded path |

## Năm phần mở rộng

| Extension | Nội dung hoàn thiện | Đo trước/sau và insight |
|---|---|---|
| 1. Purchasing | Interruption theo GPU type; tính đủ 365/1095 ngày, 24h cam kết; so mọi tier; matrix policy | Bảng từng job trên cùng days; inference 30 ngày reserved → on-demand khi mua mới; actual-days savings 15.19% |
| 2. Right-sizing MBU | Max VRAM ×1.10, max bandwidth/compute với target 80%; decode/embed ưu tiên $/GB-h, training xét giá/giờ | A100 không đủ chỗ trên GPU 24GB; A10G → L4 ứng viên 144 USD/GPU/30 ngày OD; có check phân biệt hai tiêu chí; chưa benchmark |
| 3. Cache economics | `cache_is_worth_it`, USD/1M cùng đơn vị; ghi phí write, gate có xét batch | Giả định reads=0.5/1/4/20; hòa vốn sync 1.389, batch 2.778; cost và $/1M trước/sau writes |
| 4. Reasoning budget | Tách request/token/cost/Wh và tỷ trọng, counterfactual cap 10% | Reasoning 8.38% traffic nhưng 94.04% energy; dưới cap nên USD/Wh savings = 0; check case vượt cap |
| 5. Carbon-aware scheduling | Interruptible jobs; watts × actual GPU-hours; bảng năm vùng | 679.820 → 53.670 gCO2e; giảm 626.150 gCO2e; rẻ nhất us-east-wa, sạch nhất europe-north1 |

## Giả định ảnh hưởng kết quả

- Kế hoạch chính là **30 ngày**, có pool reserved hiện hữu tái sử dụng. Extension mua cam kết mới dùng **days thực tế**; không so tổng hai thời kỳ trực tiếp.
- API M2 và GPU M3 chỉ cộng vào tổng nếu là hai khoản chi độc lập. Workload training chưa có sản lượng token nên không quy tổng GPU spend thành $/1M-token.
- CSV chưa có ID nối GPU telemetry với job. M5 ghi rõ ánh xạ giả định, cần xác nhận giờ budget chứa idle. Right-sizing cần benchmark throughput và tương thích software; thay reserved chỉ giảm chi capacity khi tái phân bổ/gia hạn.
- Reads/write, phí ghi, interruption, headroom 10%, target utilization 80%, power/carbon/điện đều là giả định minh họa. Giá không phải báo giá hiện hành.
- Reasoning cap giữ tokens/model. Không giảm tiền nếu chưa đổi output/model; 80× là giả định Wh, không phải hệ số tiền.
- Carbon scheduling dùng rated GPU watts, chưa cộng PUE/CPU/network/checkpoint. Không cộng tiền điện lần nữa vào GPU rental.

## Chạy lại và nộp bài

```bash
python data/generate.py
python missions/run_all.py
python verify.py
pytest -q              # 15 passed: tests gốc
pytest -q tests checks # 50 passed: gốc + mở rộng
```

Nộp `outputs/report.md`, `outputs/savings.png`, `outputs/focus_export.csv`, `outputs/writeup.md`.
Kèm `outputs/before/` và `outputs/after.json` làm bằng chứng so trước/sau. File `tests/` gốc giữ nguyên.
Toàn bộ graded path đã kiểm tra trên Python 3.11, không cần cài thêm dependency ngoài `requirements.txt`.

## Kết quả rà soát toàn bộ yêu cầu — 2026-10-13

Đã đối chiếu 15 file Markdown, gồm tài liệu chính, đề bổ sung, report/write-up, hướng dẫn và report bonus
và baseline lịch sử. Baseline giữ số liệu trước sửa để so sánh; các file hiện hành mô tả kết quả mới.

| Nhóm | Bằng chứng hiện tại |
|---|---|
| A — Chạy pipeline | `python verify.py`: 11/11 checks passed |
| B — Tests gốc | `pytest -q`: 15 passed; không sửa `tests/` |
| Checks phần mở rộng | `pytest -q tests checks`: 50 passed |
| C — Báo cáo và file nộp | Đủ bốn file; tiền trong report/write-up khớp kết quả mission; PNG đọc được; CSV đủ 2.400 request |
| D — Phần mở rộng | Hoàn thiện 5/5, mỗi phần có code, số liệu, bảng so sánh và insight; giả định được nêu rõ |
| Tái lập dữ liệu | Bốn CSV đọc được bằng pandas; SHA-256 giống baseline trước sửa |
| Tài liệu | UTF-8 hợp lệ; liên kết file nội bộ tồn tại; danh sách nộp thống nhất bốn file bắt buộc |

Lượt này đã chỉnh tiêu chí right-sizing: decode/embed ưu tiên USD/GB-VRAM/giờ sau khi đạt
VRAM/bandwidth/compute; training ưu tiên giá/giờ. Có check chứng minh hai loại workload dùng tiêu chí khác nhau.
Guide/CODELAB đã tách baseline/JSON/log thành bằng chứng bổ sung thay vì file nộp bắt buộc.

Theo checklist của đề mới và rubric, các yêu cầu bắt buộc của **lab mô phỏng** đã có bằng chứng đáp ứng.
Đây không phải cam kết đạt 100 điểm hoặc chứng minh GPU đã tối ưu tuyệt đối ngoài thực tế.
Benchmark throughput GPU, chất lượng routing, giá thị trường và đo điện thật chưa thực hiện;
đề cho phép ghi rõ các giới hạn này. Bonus tùy chọn không ảnh hưởng hoàn thành bài chấm điểm.
Log lượt kiểm tra ở `outputs/validation.txt`. Chưa commit/push.

## Yêu cầu bonus được bổ sung — 2026-10-13

User yêu cầu hoàn thiện cả ba bonus sau lượt rà soát graded path; chúng vẫn không chấm điểm.
`pytest -q` vẫn 15 tests gốc; `pytest -q tests checks` hiện gồm 15 gốc + 19 extension + 16 bonus = 50 tests.

| Bonus | Nội dung hoàn thiện | Kiểm chứng / artifact |
|---|---|---|
| Tracker | Budget/token validation; cap atomic; per-key log và precision đầy đủ; CSV export | Demo chặn sau 10 chat request; CSV khớp spend; tests concurrency/boundary; tracker_summary.json |
| CPU model | Model thật, CPU eval/inference_mode, warm-up + 3 timed runs, output-only economics, offline/strict | local_benchmark.json ghi model/revision/versions, throughput và giá CPU giả định; skipped không coi là pass |
| Docker | Prometheus/Grafana cố định phiên bản, ports localhost, exporter health + 8 metrics, datasource UID, 9-panel dashboard | bonus verifier kiểm tra target UP, 11 MFU series, idle=20 USD, datasource/dashboard HTTP thật |

Evidence mới: [report bonus](outputs/bonus/report.md), [validation bonus](outputs/bonus/validation.json).
Hướng dẫn từng bonus ghi rõ phạm vi mock, giá thuê CPU giả định, snapshot synthetic và cách dừng stack.
Không commit model weights/dependencies; `.venv/` và `.cache/` được gitignore.

Kết quả thực tế sau hoàn thiện bonus:

- `python bonus/verify.py --docker --model`: tracker/exporter/Docker/model đều pass.
- Model CPU: tiny-gpt2 revision `5f91d94bd9cd7190a9f3216ff93cd1dd95f2c7be`, 3 timed runs, 192 output tokens;
  số đo cuối 185.29 output tok/s, 0.149919 USD/1M output tokens với giá CPU giả định 0.10 USD/h.
- Docker: cả ba service healthy, target exporter UP, datasource Prometheus health OK, dashboard có 9 panel.
- `promtool check config` và `promtool check metrics` trực tiếp từ exporter HTTP đều pass;
  idle duration dùng giây, artifact metric dùng LF để đúng Prometheus text protocol trên Windows.
- `.venv/Scripts/python.exe -m pytest -q tests checks`: 50 passed; `pytest -q`: 15 passed;
  `python verify.py`: 11/11 checks passed.

Benchmark CPU đo thật nhưng tốc độ phụ thuộc tải máy; không khẳng định chất lượng tiny model tương đương
model production hoặc giá thuê giả định là hóa đơn thật. Các giới hạn này không phải phần bỏ sót của bonus lab.
Stack đang chạy localhost để demo; dừng bằng `docker compose -f bonus/docker/docker-compose.yml down`.
