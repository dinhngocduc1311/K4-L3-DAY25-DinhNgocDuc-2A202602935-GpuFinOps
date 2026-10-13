# Lab 25 — Tối ưu hóa Chi phí GPU (GPU FinOps Workshop)

> **AICB · Phase 2 · Track 2 (Infrastructure) · Day 25**
> Kết hợp với slide `day25-gpu-finops-cost-optimization`.
> Đầu ra chính: **Báo cáo chi phí GPU (baseline vs. optimized)** — đầu vào cho Milestone 2.

---

## Trạng thái bản hoàn thiện (đề bổ sung ngày 2026-10-13)

Bản này đã triển khai **5/5 extension**, có bảng trước/sau và giải thích trong
[outputs/report.md](outputs/report.md), bài viết trong [outputs/writeup.md](outputs/writeup.md).
Đối chiếu yêu cầu tại [REQUIREMENTS.md](REQUIREMENTS.md); đề bạn gửi lưu ở [Practice.md](Practice.md).

- Bộ dữ liệu seed=25 giữ nguyên; baseline trước sửa lưu trong `outputs/before/`, SHA-256 trong `baseline.json`.
- 11/11 verify checks; 15 tests gốc giữ nguyên; 19 checks FinOps và 16 tests bonus tại `checks/`.
- Inference có cache writes: **6.487984 → 1.181472 USD/1M-token** (81.8% savings).
- Kế hoạch 30 ngày: **27,133.62 → 15,352.83 USD**, dự kiến **43.42%**; idle/right-sizing có điều kiện.
- Kế hoạch 30 ngày giả định pool reserved hiện hữu và tính đủ 24h/ngày; extension mua mới dùng `days` thực tế
  và tính toàn bộ nghĩa vụ 1yr/3yr. Hai kịch bản không so trực tiếp với nhau.
- Report tách vùng điện rẻ nhất, sạch nhất và cân bằng. FOCUS-style export đủ 2.400 request, khớp M2/M4.
- Số liệu là mô phỏng; cần benchmark throughput/chất lượng và xác nhận ánh xạ GPU → job trước áp dụng.

## Bối cảnh

Bạn vừa được tuyển làm **FinOps Engineer** tại *NimbusAI* — một startup LLM đang có hóa đơn GPU mất kiểm soát. Bạn được giao:

- Dữ liệu telemetry GPU tổng hợp (mô phỏng)
- Danh mục giá GPU tháng 6/2026
- Nhật ký sử dụng token

**Nhiệm vụ:** Tìm ra điểm lãng phí và **cắt giảm chi phí 40–95%** — đo bằng `$/1M-token`, không phải `$/GPU-giờ`.

> Lab này chạy hoàn toàn trên **laptop không có GPU, không có tài khoản cloud, không cần API key**.

---

## Cài đặt môi trường

```bash
# Mở terminal tại thư mục gốc project (có requirements.txt)

# Tạo và kích hoạt virtual environment
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# Cài đặt thư viện
pip install -r requirements.txt

# Kiểm tra cài đặt (phải in ra 11/11 checks passed)
python verify.py
```

### Chạy toàn bộ lab nhanh

```bash
python data/generate.py       # (Tạo lại) dữ liệu tổng hợp (seed cố định = 25)
python missions/run_all.py    # Chạy M1 → M5, in kết quả
pytest -q                    # 15 tests gốc (mặc định trong pytest.ini)
pytest -q tests checks       # 50 tests: 15 gốc + 19 checks mở rộng + 16 bonus
```

Kết quả xuất ra thư mục `outputs/`: `report.md`, `savings.png`, `focus_export.csv`, `writeup.md`, `after.json`.

---

## Cấu trúc dự án

```
Day25-Track2-GPU-FinOps-Lab/
├── data/
│   ├── generate.py           # Sinh dữ liệu tổng hợp (tất định, seed=25)
│   ├── price_catalog.csv     # Bảng giá 7 loại GPU
│   ├── gpu_telemetry.csv     # Telemetry 11 GPU × 24 giờ
│   ├── token_usage.csv       # 2,400 request LLM
│   └── workloads.csv         # 8 workload training/inference
├── finops/
│   ├── metrics.py            # MFU, MBU, roofline, phát hiện "GPU-Util lie"
│   ├── pricing.py            # Chi phí request, $/1M-token, chiết khấu, tier
│   ├── allocation.py         # Phân bổ chi phí theo tag, FOCUS export
│   ├── sustainability.py     # Năng lượng, carbon, vùng tối ưu
│   └── report.py             # Tạo báo cáo Markdown + biểu đồ
├── missions/
│   ├── m1_efficiency_audit.py   # Mission 1: Kiểm toán hiệu quả GPU
│   ├── m2_inference_levers.py   # Mission 2: Đòn bẩy chi phí inference
│   ├── m3_purchasing.py         # Mission 3: Chiến lược mua GPU
│   ├── m4_allocation.py         # Mission 4: Phân bổ chi phí
│   ├── m5_report.py             # Mission 5: Báo cáo tổng hợp
│   └── run_all.py               # Chạy M1–M5 liên tiếp
├── tests/                    # 15 tests gốc giữ nguyên
├── checks/                   # 19 checks FinOps + 16 tests bonus
├── outputs/                  # Kết quả sinh ra (report.md, savings.png, ...)
├── bonus/                    # Phần mở rộng không bắt buộc
│   ├── litellm_tracker/      # Giả lập LiteLLM proxy + budget cap
│   ├── local_model/          # Đo tok/s với model chạy CPU
│   └── docker/               # Prometheus + Grafana dashboard
├── verify.py                 # Kiểm tra toàn bộ (11 checks)
└── requirements.txt
```

---

## Các module `finops/`

| Module | Chức năng |
|---|---|
| `metrics.py` | `compute_mfu`, `compute_mbu`, `roofline_regime`, `flag_util_lies`, `idle_waste_usd` |
| `pricing.py` | `request_cost`, `dollars_per_million`, `discount_stack`, `break_even_utilization`, `recommend_tier`, `tier_costs`, `spot_checkpoint_cost`, `cache_is_worth_it` |
| `allocation.py` | `cost_by_tag`, `tag_coverage`, `chargeback_ready`, `to_focus_rows` |
| `sustainability.py` | `wh_per_query`, `carbon_g`, `energy_cost_usd`, `tokens_per_watt` |
| `report.py` | `build_report`, `savings_waterfall` |

---

## 5 Missions

| # | Tên | Bạn học được gì | Chạy lệnh |
|---|---|---|---|
| **M1** | **Kiểm toán hiệu quả** — MFU/MBU, "GPU-Util lie", lãng phí idle | Slide §5 | `python missions/m1_efficiency_audit.py` |
| **M2** | **Đòn bẩy chi phí Inference** — `$/1M-token`, batch × cache × cascade | Slide §7 | `python missions/m2_inference_levers.py` |
| **M3** | **Chiến lược mua GPU** — điểm hòa vốn, spot/reserved, checkpoint sim | Slide §4 | `python missions/m3_purchasing.py` |
| **M4** | **Phân bổ chi phí** — tag → showback → chargeback, FOCUS export | Slide §10 | `python missions/m4_allocation.py` |
| **M5** | **Báo cáo tối ưu** — baseline vs. optimized + tính bền vững | Slide §1/§11 | `python missions/m5_report.py` |

**Bài học cốt lõi của M1:** GPU `gpu-h100-4` hiển thị **98% GPU-Util nhưng MFU chỉ ~0.20** — bạn trả tiền cho cả giờ H100 nhưng chỉ nhận được 1/5 FLOPs. `nvidia-smi` đo "clock đang bận", không đo hiệu quả tính toán.

---

## Dữ liệu đầu vào (`data/`)

| File | Số dòng | Cột quan trọng |
|---|---|---|
| `price_catalog.csv` | 7 GPU | `on_demand_hr`, `spot_hr`, `reserved_3yr_hr`, `peak_tflops_fp16`, `peak_bw_tbs`, `watts` |
| `gpu_telemetry.csv` | 11 GPU × 24 giờ | `gpu_util_pct`, `achieved_tflops`, `achieved_bw_tbs`, `power_w` |
| `token_usage.csv` | 2,400 request | `route_tier`, `input/output/cached_input_tokens`, `is_batch`, `is_reasoning`, `team`, `project` |
| `workloads.csv` | 8 job | `hours_per_day`, `days`, `interruptible`, `gpu_type`, `num_gpus` |

> `data/generate.py` dùng seed cố định — tái tạo luôn cho kết quả giống nhau.

---

## Phần mở rộng "Your Turn" (nơi học sâu nhất)

Đã thực hiện cả năm phần; chạy lại để kiểm tra và đọc bảng định lượng trong report:

1. **Cải thiện chính sách tier.** `pricing.recommend_tier()` giữ lời gọi cơ bản và có chế độ `prices` + `job_days` để so tổng chi phí, interruption theo GPU type và nghĩa vụ 1yr/3yr.
2. **Right-sizing theo MBU.** Trong M1, dùng `$/GB-VRAM` và `peak_bw_tbs` để quyết định GPU nào phù hợp cho từng inference workload bị memory-bound.
3. **Kinh tế học của Cache.** Prompt caching chỉ có lợi khi tỷ lệ read đủ cao. Đã thêm `cache_is_worth_it()`; gate tính cả phí ghi, batch và các kịch bản ít/nhiều reads.
4. **Ngân sách Reasoning.** Tính toán chi phí `$` và `Wh` thêm từ traffic `is_reasoning` trong M2/M5 và đề xuất quy tắc routing để giới hạn.
5. **Lịch trình nhận thức Carbon.** So vùng điện rẻ nhất, carbon sạch nhất và vùng cân bằng cho job interruptible; báo cáo carbon tiết kiệm theo ngày thực tế của job.

---

## Kiểm tra kết quả

Chạy hai lệnh kiểm tra, sau đó đọc lại báo cáo được sinh từ kết quả mới:

```bash
python verify.py
pytest -q
cat outputs/report.md
```

Cần đạt **11/11 checks passed** và **15 passed** cho bộ tests gốc.
`pytest.ini` đặt `testpaths = tests`; không thay đổi nội dung file trong `tests/`.
Verify tạo lại dữ liệu seed=25 và chạy lại M1–M5, nên mở lại `outputs/report.md` sau lệnh này.
Trong PowerShell, dùng `Get-Content outputs/report.md -Encoding UTF8` để đọc đúng tiếng Việt.

Các checks mở rộng chạy riêng hoặc chạy cùng bộ gốc:

```bash
pytest -q checks/test_extensions.py # 19 passed
pytest -q checks/test_bonus.py      # 16 passed
pytest -q tests checks  # 50 passed
```

Đối chiếu số liệu với terminal M5 (`python missions/m5_report.py`):

| Chỉ số | Kết quả seed=25 |
|---|---|
| Baseline / 30 ngày | 27,133.62 USD |
| Optimized / 30 ngày | 15,352.83 USD |
| Projected savings | 11,780.79 USD (43.42%) |
| Inference baseline → optimized | 6.487984 → 1.181472 USD/1M-token |
| `focus_export.csv` | 2.400 request; tổng BilledCost = 8.900059 USD/ngày, khớp M2/M4 |

Mở [savings.png](outputs/savings.png): baseline, bốn lever và optimized phải khớp report.
Đọc [focus_export.csv](outputs/focus_export.csv): kiểm tra `BilledCost`, `team`, `project`;
giữ request thiếu project để tag coverage không bị che giấu.
Savings idle/right-sizing là dự báo có điều kiện; giả định được ghi trong báo cáo.

Pass kiểm tra code cần đi kèm đủ bốn file nộp:

- [report.md](outputs/report.md): baseline/optimized, breakdown, sustainability, bảng mở rộng và giả định.
- [savings.png](outputs/savings.png): biểu đồ đọc được.
- [focus_export.csv](outputs/focus_export.csv): dữ liệu phân bổ khớp tổng tiền.
- [writeup.md](outputs/writeup.md): bài viết phân tích và ba hành động ưu tiên.

Bằng chứng chạy kiểm tra lưu trong [validation.txt](outputs/validation.txt);
baseline và kết quả mới trong `outputs/before/` và `outputs/after.json`.

**Lỗi thường gặp**

- Thiếu `pandas` → kích hoạt `.venv` và chạy `python -m pip install -r requirements.txt`.
- Thiếu `data/gpu_telemetry.csv` → chạy `python data/generate.py`.
- M2 savings ngoài khoảng 60–95% → kiểm tra `cache_discount=0.10`, `batch_discount=0.50`, gate cache và phí ghi.
- `test_flag_util_lies` fail → chia `gpu_util_pct` cho 100 trước khi so với 0.90.
- Thiếu `savings.png` → kiểm tra `python -m pip show matplotlib`, cài requirements và chạy lại `python missions/m5_report.py`.
- Không tìm thấy lệnh `pytest` → dùng `python -m pytest -q` để chạy bằng cùng Python với verify.

**Không sửa file trong `tests/` để làm pass.** Nếu test bị sửa để hardcode kết quả, rubric trừ toàn bộ điểm phần B.

---

## Đầu ra & Chấm điểm

Nộp `outputs/report.md`, `outputs/savings.png`, `outputs/focus_export.csv`, `outputs/writeup.md`:

| Thành phần | Trọng số |
|---|---|
| `verify.py` pass 11/11 | 30% |
| `pytest` pass | 20% |
| Báo cáo thể hiện baseline vs. optimized theo **$/1M-token** với từng lever | 30% |
| ≥2 phần mở rộng "Your Turn" được thực hiện và đo lường | 20% |

> Đây là **đầu vào Milestone 2** — mang báo cáo đến buổi demo platform.

---

## Nộp bài

Nộp đúng bốn file theo [Rubric.md](Rubric.md):

```text
outputs/report.md
outputs/savings.png
outputs/focus_export.csv
outputs/writeup.md
```

[writeup.md](outputs/writeup.md) là bài viết ngắn khoảng 1–2 trang, trả lời đủ:

1. **Baseline vs. Optimized:** chi phí trước/sau, USD/1M-token và tổng phần trăm tiết kiệm.
2. **Từng đòn bẩy:** số tiền, tỷ trọng đóng góp, lever lớn nhất và nguyên nhân.
3. **GPU-Util Lie:** GPU bị flag, cơ chế có thể xảy ra và tác động tài chính có điều kiện.
4. **Phần mở rộng:** mô tả, kết quả định lượng và insight của cả năm extension đã làm.
5. **Khuyến nghị NimbusAI:** ba hành động đầu tiên theo thứ tự ưu tiên.

Bài viết được M5 sinh từ cùng số liệu với report; sửa phần sinh trong
`missions/m5_report.py` nếu cần thay nội dung để lần chạy verify sau không ghi đè chỉnh sửa thủ công.

Checklist trước khi nộp:

- [ ] `python verify.py` → **11/11 checks passed**.
- [ ] `pytest -q` → **15 passed**, giữ nguyên tests gốc.
- [ ] `outputs/report.md` có chi phí trước/sau, savings từng lever, điện năng và phát thải CO₂.
- [ ] `outputs/savings.png` tồn tại và đọc được; số tiền khớp report.
- [ ] `outputs/focus_export.csv` có đủ request; tổng tiền khớp M2/M4.
- [ ] Đã thực hiện **≥2 extension** có kết quả đo lường; bản này có **5/5**.
- [ ] `outputs/writeup.md` trả lời đủ năm câu hỏi, ngắn khoảng 1–2 trang.

Log kiểm tra tại [validation.txt](outputs/validation.txt); baseline trước sửa tại `outputs/before/`.
Dùng báo cáo làm đầu vào **Milestone 2** và mang đến buổi demo platform.
Repo bài lab gốc: [VinUni-AI20k/Day25-Track2-GpuFinOps](https://github.com/VinUni-AI20k/Day25-Track2-GpuFinOps).

---

## Bonus (đã hoàn thiện cả ba, không chấm điểm)

Bản hiện tại có tracker mock với ledger/budget cap, benchmark model CPU thật và stack
Prometheus/Grafana. Kết quả riêng xem [outputs/bonus/report.md](outputs/bonus/report.md).
Các bonus không thay đổi bốn file nộp và không cộng chi phí vào ngân sách M1–M5.

Chạy từ root project bằng venv đã cài dependencies:

```bash
python bonus/litellm_tracker/demo.py
python -m pip install -r bonus/local_model/requirements.txt
python bonus/local_model/run_local.py --strict
docker compose -f bonus/docker/docker-compose.yml up -d --wait --wait-timeout 90
python bonus/verify.py --docker --model
pytest -q checks/test_bonus.py # 16 passed; không cần Docker/model để chạy unit tests
pytest -q tests checks        # 50 passed: 15 gốc + 19 extension + 16 bonus
```

Grafana http://127.0.0.1:3000 (demo admin/admin); Prometheus http://127.0.0.1:9090;
exporter http://127.0.0.1:9101/metrics. Dừng stack bằng
`docker compose -f bonus/docker/docker-compose.yml down`. Cache model trong `.cache/`, không commit weights.

Các phần kiểm tra thực tế và giới hạn được ghi trong hướng dẫn từng bonus:

- **`bonus/litellm_tracker/`** — tracker mock có budget cap theo alias key và ledger CSV đối chiếu.
- **`bonus/local_model/`** — đo CPU thật sau warm-up, output-only USD/1M với giá CPU giả định.
- **`bonus/docker/`** — exporter stdlib + Prometheus/Grafana có datasource và dashboard provisioning.

---

## Lưu ý quan trọng

- **Giá thay đổi hàng tháng.** Tất cả số liệu là snapshot tháng 6/2026. Cập nhật lại trước khi áp dụng thực tế.
- Bài học cốt lõi **bền vững theo thời gian**: đo `$/token`, dùng MFU thay vì GPU-Util, chồng chiết khấu, tính điểm hòa vốn trước khi commit reserved, gắn tag trước khi chargeback.
- Path graded thuần Python: `pandas`, `matplotlib`, `pytest`. Không cần GPU / API key / Docker.
