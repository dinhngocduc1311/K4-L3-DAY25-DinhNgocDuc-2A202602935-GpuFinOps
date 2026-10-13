# Hướng dẫn Hoàn thành Lab 25 — GPU FinOps Optimization

> Hướng dẫn từng bước dành cho sinh viên thực hiện Lab 25.
> Yêu cầu: Python 3.9+, không cần GPU/cloud/API key; đã kiểm tra trên Python 3.11.
>
> Bản hoàn thiện: **5/5 extension**, baseline trong `outputs/before/`, 15 tests gốc và 19 checks mở rộng.
> Kết quả: [report.md](outputs/report.md), [writeup.md](outputs/writeup.md), [REQUIREMENTS.md](REQUIREMENTS.md).

---

## Mục lục

1. [Hiểu bối cảnh bài lab](#1-hiểu-bối-cảnh-bài-lab)
2. [Cài đặt môi trường](#2-cài-đặt-môi-trường)
3. [Khám phá dữ liệu đầu vào](#3-khám-phá-dữ-liệu-đầu-vào)
4. [Mission 1 — Kiểm toán hiệu quả GPU](#4-mission-1--kiểm-toán-hiệu-quả-gpu)
5. [Mission 2 — Đòn bẩy chi phí Inference](#5-mission-2--đòn-bẩy-chi-phí-inference)
6. [Mission 3 — Chiến lược mua GPU](#6-mission-3--chiến-lược-mua-gpu)
7. [Mission 4 — Phân bổ chi phí](#7-mission-4--phân-bổ-chi-phí)
8. [Mission 5 — Báo cáo tổng hợp](#8-mission-5--báo-cáo-tổng-hợp)
9. [Chạy toàn bộ kiểm tra](#9-chạy-toàn-bộ-kiểm-tra)
10. [Phần mở rộng "Your Turn"](#10-phần-mở-rộng-your-turn)
11. [Chuẩn bị nộp bài](#11-chuẩn-bị-nộp-bài)
12. [Các lỗi thường gặp](#12-các-lỗi-thường-gặp)

---

## 1. Hiểu bối cảnh bài lab

### Câu chuyện

Bạn là FinOps Engineer mới gia nhập **NimbusAI** — một startup LLM đang tiêu tốn quá nhiều tiền cho GPU. Nhiệm vụ của bạn là phân tích dữ liệu và **cắt giảm ít nhất 40% chi phí GPU**, đo bằng `$/1M-token`.

### Tại sao `$/1M-token` quan trọng hơn `$/GPU-giờ`?

`$/GPU-giờ` nói lên bạn **trả bao nhiêu** để thuê GPU, nhưng không nói lên bạn **nhận được gì**. Hai đội có thể trả cùng `$/GPU-giờ`, nhưng một đội phục vụ 10× nhiều token hơn do tối ưu tốt hơn. Đơn vị `$/1M-token` bắt buộc bạn đo cả **hiệu quả sử dụng**.

### Các khái niệm cốt lõi cần nắm trước khi làm lab

| Khái niệm | Giải thích |
|---|---|
| **MFU** (Model FLOPs Utilization) | % FLOPs thực sự dùng / peak FLOPs. Tốt: 35–50%. Giá trị thực đo hiệu quả tính toán. |
| **MBU** (Model Bandwidth Utilization) | % băng thông HBM thực sự dùng / peak. Dùng cho workload memory-bound (ví dụ: decode). |
| **GPU-Util %** (từ `nvidia-smi`) | Chỉ đo "clock có đang hoạt động không" — **KHÔNG phải hiệu quả**. GPU-Util 98% vẫn có thể MFU 20%. |
| **Cascade** | Định tuyến request đơn giản sang model nhỏ (rẻ hơn 15×), chỉ dùng model lớn khi cần. |
| **Prompt Caching** | Phần input đã cache được chiết khấu 90% (chỉ tính 10% giá). |
| **Batch API** | Nhóm request không cần real-time → chiết khấu 50%. |
| **Spot Instance** | GPU giá thấp nhưng có thể bị thu hồi. Phù hợp với job có thể gián đoạn + checkpoint. |
| **Reserved Instance** | Cam kết 1–3 năm → chiết khấu ~45%. Chỉ có lợi khi utilization ≥ 55%. |
| **Showback** | Hiển thị chi phí theo team để nhận thức, chưa thực sự tính phí. |
| **Chargeback** | Thực sự thu tiền từ team theo mức sử dụng. Cần tag coverage ≥ 80%. |
| **FOCUS** | Chuẩn mở đa nhà cung cấp cho dữ liệu chi phí cloud (FinOps Foundation). |

---

## 2. Cài đặt môi trường

### Bước 2.1 — Clone hoặc vào thư mục lab

```bash
# Mở terminal tại thư mục gốc project (có requirements.txt)
```

### Bước 2.2 — Tạo virtual environment

```bash
# macOS / Linux
python -m venv .venv
source .venv/bin/activate

# Windows (PowerShell)
python -m venv .venv
.venv\Scripts\activate
```

Khi kích hoạt thành công, terminal sẽ hiển thị `(.venv)` ở đầu dòng lệnh.

### Bước 2.3 — Cài đặt thư viện

```bash
pip install -r requirements.txt
```

Thư viện cần:
- `pandas>=2.0` — xử lý CSV
- `matplotlib>=3.7` — vẽ biểu đồ savings waterfall
- `pytest>=7.4` — chạy unit tests

### Bước 2.4 — Kiểm tra cài đặt

```bash
python verify.py
```

**Kết quả mong đợi:**
```
============================================================
  LAB 25 VERIFY
============================================================
  [PASS] M1 flags the GPU-Util lie (gpu-h100-4)
  [PASS] M1 detects idle waste
  [PASS] M2 $/1M-token drops after optimization
  ...
------------------------------------------------------------
  11/11 checks passed
============================================================
```

> Nếu chưa được 11/11 ngay lúc này, tiếp tục làm lab và chạy lại sau khi hoàn thành.

---

## 3. Khám phá dữ liệu đầu vào

### Bước 3.1 — Sinh dữ liệu tổng hợp

```bash
python data/generate.py
```

Lệnh này tạo 4 file CSV trong `data/` với seed cố định (seed=25), luôn cho kết quả giống nhau.

### Bước 3.2 — Đọc và hiểu từng file

**`data/price_catalog.csv`** — Bảng giá GPU:

```python
import pandas as pd
df = pd.read_csv("data/price_catalog.csv")
print(df[["gpu_type", "on_demand_hr", "spot_hr", "reserved_3yr_hr", "peak_tflops_fp16", "watts"]])
```

Chú ý: H100 on-demand ~$2.5/giờ. Spot rẻ hơn đáng kể. Reserved 3yr rẻ nhất nhưng cần cam kết.

**`data/gpu_telemetry.csv`** — Telemetry GPU theo giờ:

```python
df = pd.read_csv("data/gpu_telemetry.csv")
print(df[["gpu_id", "gpu_type", "gpu_util_pct", "achieved_tflops", "achieved_bw_tbs"]].head(20))
```

Tìm các GPU có `gpu_util_pct` cao nhưng `achieved_tflops` thấp so với peak — đây là "GPU-Util lie".

**`data/token_usage.csv`** — Nhật ký 2,400 request LLM:

```python
df = pd.read_csv("data/token_usage.csv")
print(df[["route_tier", "input_tokens", "output_tokens", "cached_input_tokens", "is_batch", "team"]].head(10))
```

`route_tier` = `"small"` hoặc `"large"`. `is_batch` = 1 nếu request có thể gộp batch.

**`data/workloads.csv`** — 8 job training/inference:

```python
df = pd.read_csv("data/workloads.csv")
print(df[["job_id", "gpu_type", "num_gpus", "hours_per_day", "interruptible"]])
```

`interruptible=1` → phù hợp với spot instance + checkpoint.

---

## 4. Mission 1 — Kiểm toán hiệu quả GPU

**Mục tiêu:** Phát hiện GPU đang "nói dối" (GPU-Util cao nhưng MFU thấp) và tính lãng phí idle.

### Bước 4.1 — Đọc code `finops/metrics.py`

Mở file và đọc kỹ 3 hàm:
- `compute_mfu(achieved_tflops, peak_tflops)` → trả về tỷ lệ 0.0–1.0
- `flag_util_lies(rows, util_threshold=0.90, mfu_threshold=0.30)` → các GPU có util ≥ 90% nhưng MFU < 30%
- `idle_waste_usd(idle_hours, on_demand_hr)` → dollars lãng phí do GPU để trống

### Bước 4.2 — Chạy M1

```bash
python missions/m1_efficiency_audit.py
```

**Kết quả mong đợi (mẫu):**
```
== M1 Efficiency Audit ==
GPU            type   util%    MFU    MBU  idle_h
gpu-h100-4     H100    98.2  0.194  0.207       0
...
GPU-Util LIES (util>=90% but MFU<30%): ['gpu-h100-4', 'gpu-a10g-1']
Idle waste (1 day): $20.00  ->  $600/month
```

### Bước 4.3 — Phân tích kết quả

Trả lời các câu hỏi sau (để hiểu sâu):

1. GPU nào có `GPU-Util` cao nhất? MFU của nó là bao nhiêu?
2. Tại sao `GPU-Util 98%` có thể đi kèm với `MFU 20%`? (Gợi ý: GPU "bận" nhưng làm gì? Memory stall? I/O wait?)
3. Lãng phí idle tính ra bao nhiêu `/tháng`? Chiếm bao nhiêu % tổng chi phí?

### Bước 4.4 — Hiểu roofline model (tùy chọn nhưng nên đọc)

```python
from finops.metrics import roofline_regime, arithmetic_intensity
# H100 ridge point: ~295 FLOP/byte (BF16)
# LLM decode: ~1-2 FLOP/byte → memory-bound
# LLM prefill: ~455 FLOP/byte → compute-bound
print(roofline_regime(1.5, 295))   # 'memory-bound'
print(roofline_regime(455, 295))   # 'compute-bound'
```

---

## 5. Mission 2 — Đòn bẩy chi phí Inference

**Mục tiêu:** Hiểu 3 "đòn bẩy" chính để giảm `$/1M-token`:
1. **Cascade** — định tuyến request sang model nhỏ khi đủ
2. **Prompt Caching** — chiết khấu 90% cho phần input đã cache
3. **Batch API** — chiết khấu 50% cho request không cần real-time

### Bước 5.1 — Đọc code `finops/pricing.py`

Tập trung vào:
- `request_cost(input_tok, output_tok, price_in, price_out, cached_in, batch)` — chi phí một request
- `dollars_per_million(total_cost, total_tokens)` — quy về `$/1M-token`
- `discount_stack(batch, cache_hit_frac)` — xem chiết khấu nhân lên nhau thế nào

### Bước 5.2 — Chạy M2

```bash
python missions/m2_inference_levers.py
```

**Kết quả mong đợi (mẫu):**
```
== M2 Inference Cost Levers ==
requests=2400  tokens=7,533,027
Baseline              : $48.8742/day  $6.4880/1M-token
Cascade               : $11.4756/day  $1.5234/1M-token
+ Cache incl. writes  : $10.6946/day  $1.4197/1M-token
+ Batch               : $8.9001/day   $1.1815/1M-token
savings: 81.8% (same tokens; cache write fees included)
```

### Bước 5.3 — Tính tay để kiểm tra hiểu biết

```python
from finops.pricing import request_cost, discount_stack

# Baseline: model lớn, không cache, không batch
baseline = request_cost(
    input_tok=1000, output_tok=200,
    price_in_per_m=3.00, price_out_per_m=15.00
)
print(f"Baseline: ${baseline:.4f}")

# Optimized: model nhỏ + cache 80% input + batch
optimized = request_cost(
    input_tok=1000, output_tok=200,
    price_in_per_m=0.20, price_out_per_m=0.40,
    cached_in=800, batch=True
)
print(f"Optimized: ${optimized:.4f}")

# Discount stack: batch=True + 80% cache hit
print(f"Effective fraction: {discount_stack(batch=True, cache_hit_frac=0.8):.3f}")
```

### Bước 5.4 — Phân tích kết quả

1. Trong 3 đòn bẩy (cascade, cache, batch), đòn bẩy nào đóng góp savings lớn nhất?
2. Tại sao `discount_stack(batch=True, cache_hit_frac=1.0) = 0.05`? (Gợi ý: 50% × 10% = ?)
3. Khi nào **không nên** dùng batch API? (Gợi ý: nghĩ về latency)

---

## 6. Mission 3 — Chiến lược mua GPU

**Mục tiêu:** Chọn đúng tier (on-demand / spot / reserved) cho từng workload để tối ưu chi phí.

### Bước 6.1 — Hiểu logic `recommend_tier()`

```python
# Trong finops/pricing.py:
def recommend_tier(hours_per_day, interruptible, reserved_discount=0.45):
    duty = hours_per_day / 24.0
    be = break_even_utilization(reserved_discount)  # = 1 - 0.45 = 55%
    if interruptible and hours_per_day < 24:
        return "spot"       # Có thể gián đoạn → spot + checkpoint
    if duty >= be:
        return "reserved"   # Duty cycle ≥ 55% → reserved
    return "on_demand"      # Còn lại
```

Đoạn trên là policy cơ bản để giữ tương thích lab. Khi truyền `prices` và `job_days`, policy so tổng chi phí thực tế của on-demand/spot/reserved 1yr/3yr. Xem mục 10.

**Điểm hòa vốn:** `1-discount` chỉ áp dụng khi xét đủ kỳ cam kết và giá cố định. Reserved tính 24h/ngày. Job ngắn cần tính cả ngày chưa dùng trong kỳ cam kết.

### Bước 6.2 — Chạy M3

```bash
python missions/m3_purchasing.py
```

**Kết quả mong đợi (mẫu):**
```
== M3 Purchasing Strategy ==
break-even utilization @ 45% reserved discount = 55%
job                gpu    tier        on-demand    optimized
job-train-llm      H100   spot          $12,000.00   $7,560.00
job-infer-chat     A10G   reserved       $4,320.00   $2,592.00
job-infer-search   L4     reserved       $1,728.00   $1,296.00
...
monthly: on-demand $25,667 -> optimized $15,925 (38.0% saved)
Actual-days total: $16,539.40 -> $14,027.52 (15.19% savings)
```

### Bước 6.3 — Tìm hiểu spot checkpoint simulation

```python
from finops.pricing import spot_checkpoint_cost

result = spot_checkpoint_cost(
    job_hours=720,          # 30 ngày × 24h
    spot_hr=1.40,           # Giá spot H100
    on_demand_hr=2.50,      # Giá on-demand H100
    interrupt_rate=0.05,    # giả định 0.05 interruption events / productive GPU-hour
    ckpt_overhead_frac=0.03 # 3% overhead để ghi checkpoint
)
print(result)
# {'spot_effective_hours': 759.6, 'spot_cost': 1063.44, 'on_demand_cost': 1800.0, 'savings_pct': 40.9}
```

### Bước 6.4 — Phân tích kết quả

1. Job nào được đề xuất dùng spot? Tại sao?
2. Với spot, "effective hours" cao hơn "job hours" thực tế — điều này nghĩa là gì?
3. Job nào được đề xuất reserved nhưng bạn nghĩ on-demand phù hợp hơn (hoặc ngược lại)? Tại sao?

---

## 7. Mission 4 — Phân bổ chi phí

**Mục tiêu:** Chuyển hóa đơn GPU chung thành trách nhiệm theo từng team — từ "visibility" → "showback" → "chargeback".

### Bước 7.1 — Hiểu lý thuyết

**Thang trưởng thành:**
```
Visibility → Showback → Chargeback
   (thấy)    (thông báo)  (thu tiền)
```

Chỉ có thể chargeback khi **tag coverage ≥ 80%** — nếu không, bạn đang tính phí dựa trên dữ liệu không đầy đủ.

### Bước 7.2 — Chạy M4

```bash
python missions/m4_allocation.py
```

**Kết quả mong đợi (mẫu):**
```
== M4 Cost Allocation ==
cost by team ($/day):
  assistant     $    2.82
  search        $    2.52
  eval          $    1.81
  rag           $    1.76
tag coverage: 92%  ->  chargeback ready? True
FOCUS export -> outputs/focus_export.csv (2400 rows)
```

### Bước 7.3 — Kiểm tra FOCUS export

```bash
head -5 outputs/focus_export.csv
```

Đây là **FOCUS-style export** phục vụ lab, chưa xác nhận tuân thủ toàn bộ schema FOCUS. Export đủ request, giữ precision để tổng `BilledCost` khớp M2/M4 (gồm cache writes).

**Các cột xuất:**
- `BillingAccountId` — tài khoản thanh toán
- `ChargePeriodStart` — kỳ tính phí
- `ServiceCategory` — loại dịch vụ (`AI and Machine Learning`)
- `BilledCost` — chi phí thực tế tính
- `team`, `project` — tags phân bổ

### Bước 7.4 — Phân tích kết quả

1. Team nào tốn nhiều nhất? Tỷ lệ so với tổng là bao nhiêu?
2. Tag coverage là bao nhiêu %? Có đủ để chargeback không?
3. Tại sao FOCUS lại quan trọng khi công ty dùng nhiều cloud provider?

---

## 8. Mission 5 — Báo cáo tổng hợp

**Mục tiêu:** Gộp kết quả từ M1–M4, tạo báo cáo baseline vs. optimized với biểu đồ waterfall.

### Bước 8.1 — Hiểu cấu trúc M5

M5 kết hợp 4 "đòn bẩy" tiết kiệm:

| Đòn bẩy | Nguồn |
|---|---|
| Inference (cascade/cache/batch) | M2 |
| Purchasing (spot/reserved) | M3 |
| Right-sizing (conditional) | M1 — kiểm tra VRAM/BW/compute, cần benchmark |
| Idle shutdown (conditional) | M1 — util <10%, tính rate sau purchasing; reserved không giảm bill |

### Bước 8.2 — Chạy M5

```bash
python missions/m5_report.py
```

**Kết quả mong đợi:**
```
== M5 Optimization Report ==
Baseline $27,133.62 -> optimized $15,352.83; savings 43.42%
Inference $6.487984 -> $1.181472/1M-token
Written: outputs/report.md + outputs/writeup.md + outputs/after.json + outputs/savings.png
```

### Bước 8.3 — Đọc báo cáo đầu ra

```bash
cat outputs/report.md
```

Mở `outputs/savings.png`: baseline, bốn savings tuần tự, optimized. M5 tính idle trước right-sizing theo từng GPU để tránh cộng trùng. CSV không nối gpu_id với job_id: ánh xạ là giả định, cần xác minh runtime chứa idle và benchmark throughput. API M2 và GPU M3 chỉ được cộng nếu là hai khoản chi riêng.

Kịch bản chính 30 ngày giả định pool reserved có thể tái sử dụng, savings là avoided capacity cost khi tái phân bổ/gia hạn. Bảng extension mua mới dùng days thực tế và tính toàn bộ kỳ cam kết.

### Bước 8.4 — Kiểm tra section Sustainability

Báo cáo dùng năng lượng trung bình từ toàn bộ request, gồm reasoning:
```markdown
## Sustainability
- Energy per query: 13.20 Wh
- Carbon per query: 5.015 gCO2e
- Cleanest region: europe-north1
- Cheapest electricity region: us-east-wa
- Balanced region (equal normalized price/carbon weights): us-east-wa
```

Nhãn vùng, điện và carbon là dữ liệu minh họa trong catalog. Vùng sạch nhất không đồng nghĩa rẻ nhất.
Cap reasoning 10% có savings bằng 0 vì traffic reasoning hiện tại chỉ 8.38%.

---

## 9. Chạy toàn bộ kiểm tra

### Bước 9.1 — Chạy tất cả missions cùng lúc

```bash
python missions/run_all.py
```

### Bước 9.2 — Chạy verify.py

```bash
python verify.py
```

Phải đạt **11/11 checks passed**. Nếu fail ở check nào, đọc chi tiết error để biết mission nào cần sửa.

**Các check quan trọng:**
- `M1 flags the GPU-Util lie (gpu-h100-4)` — `flag_util_lies()` phải trả về đúng GPU
- `M2 inference savings in 60-95% band` — savings phải trong khoảng 60–95%
- `M3 recommends a spot tier` và `M3 recommends a reserved tier` — phải có cả hai
- `M4 tag coverage 85-100%` — coverage ≥ 85%
- `M5 total savings in 40-95% band` — tổng savings phải đạt 40–95%
- `M5 report.md written` — file phải tồn tại

### Bước 9.3 — Chạy pytest

```bash
python -m pytest -q
```

**Kết quả mong đợi:**
```
...............
15 passed
```

Nếu fail, đọc assertion và sửa code. `pytest.ini` mặc định chỉ thu thập 15 tests giảng viên trong `tests/`, giữ nguyên nội dung bộ gốc. Verify chạy lại M1–M5, nên đọc lại report, mở PNG và kiểm tra CSV sau verify; pass tests vẫn cần đủ bốn file nộp. 19 checks tự viết nằm trong `checks/` và chạy riêng:

```bash
python -m pytest -q tests   # 15 tests gốc
python -m pytest -q checks/test_extensions.py # 19 checks FinOps
python -m pytest -q checks/test_bonus.py      # 16 tests bonus
python -m pytest -q tests checks  # 50 tests tổng cộng
```

---

## 10. Phần mở rộng "Your Turn"

Đề yêu cầu ít nhất hai; bản này triển khai và đo **cả năm**.
Baseline lưu trước sửa cùng SHA-256 bốn CSV trong `outputs/before/baseline.json`.
Kết quả mới: `outputs/after.json`; bảng định lượng/insight được sinh lại trong report và write-up.

### Extension 1 — Cải thiện `recommend_tier()`

File: `finops/pricing.py`, `missions/m3_purchasing.py`.

```python
from missions._common import catalog_by_type
from finops.pricing import recommend_tier
cat = catalog_by_type()
print(recommend_tier(24, False, gpu_type="H100", job_days=30, prices=cat["H100"]))
# on_demand
print(recommend_tier(24, False, gpu_type="H100", job_days=365, prices=cat["H100"]))
# reserved_1yr
print(recommend_tier(24, False, gpu_type="H100", job_days=1095, prices=cat["H100"]))
# reserved_3yr
```

Interruption theo GPU type là giả định trong `INTERRUPTION_RATES`, không phải số thị trường.
So spot có checkpoint/rework, on-demand và reserved tính đủ số kỳ 365/1095 ngày × 24h.
Không giả định có job khác dùng capacity dư sau khi job kết thúc.
Report có bảng job, chi phí tất cả candidate, tier cũ/mới, savings trước/sau và matrix.
Kịch bản chính 30 ngày dùng pool reserved đã có; extension dùng days thực tế, mua cam kết mới.
So policy trước/sau trên **cùng days**, không so tổng hai kỳ khác nhau.

### Extension 2 — Right-sizing theo MBU

File: `missions/m1_efficiency_audit.py`.

Giả định infer/embed memory-bound; MBU thấp chưa đủ kết luận roofline.
Đọc max telemetry VRAM/BW/TFLOPs và catalog `hbm_gb`, `peak_bw_tbs`, `on_demand_hr`.
Candidate cần max VRAM × 1.10; peak BW × 0.80 ≥ achieved max BW;
peak TFLOPs × 0.80 ≥ achieved max TFLOPs. Trong nhóm đủ năng lực, decode/embed ưu tiên $/GB-h thấp,
rồi giá/giờ; training util-lie là nhóm riêng, ưu tiên giá/giờ sau khi kiểm tra năng lực.

Report ghi GPU hiện tại → GPU đề xuất → lý do → USD/30 ngày.
A100 cần hơn 73 GB sau headroom nên giữ A100; A10G → L4 là ứng viên, saving 144 USD/GPU/30 ngày on-demand.
Training util-lie là nhóm sàng lọc riêng. Chưa có benchmark throughput hoặc tương thích phần mềm.
Không cộng thẳng savings on-demand của M1 vào waterfall đã giảm giá purchasing.

### Extension 3 — `cache_is_worth_it()`

File: `finops/pricing.py`, `missions/m2_inference_levers.py`; M4 dùng cùng `price_requests()`.

```python
from finops.pricing import cache_break_even_reads, cache_is_worth_it
print(cache_break_even_reads(0.25, 0.20))  # 1.3889 reads/write
print(cache_is_worth_it(1, 0.25, price_in_per_m=0.20))  # False
print(cache_is_worth_it(4, 0.25, price_in_per_m=0.20))  # True
```

Write/input prices cùng USD/1M token. CSV không có prefix IDs/reads: dùng giả định 4 reads/write,
additional write fee = 1.25 × input price ngoài ordinary input cost và không hưởng batch discount.
Hòa vốn sync 1.389 reads, batch 2.778 reads cho cả hai tier vì giả định phí ghi tỷ lệ với input price.
Chạy các case 0.5/1/4/20 reads, ghi cost và $/1M-token; không gọi reads giả định là dữ liệu quan sát.

### Extension 4 — Ngân sách Reasoning

File: `missions/m2_inference_levers.py`, `missions/m5_report.py`.

Tách is_reasoning=0/1: request/token/USD/Wh và tỷ trọng.
Dùng `wh_per_query()`; 80× là multiplier năng lượng, không nhân giá tiền thêm lần nữa.
Cap 10% giữ tokens/model; khi overflow chỉ bỏ multiplier, ưu tiên output dài nhất làm proxy độ phức tạp.
CSV không có confidence/complexity scores; cần kiểm định chất lượng trước routing thật.

Seed=25: 201/2.400 reasoning request (8.38%), 94.04% năng lượng theo mô hình.
Dưới cap nên savings USD/Wh bằng **0**. Checks có case giả định vượt cap, xác minh cost/token giữ nguyên.

### Extension 5 — Carbon-aware Scheduling

File: `missions/m3_purchasing.py`, `finops/sustainability.py`.

Chỉ interruptible=1, dùng **days thực tế**. Wh = catalog watts × productive GPU-hours.
Giữ cùng workload ở mọi vùng; chưa cộng PUE/CPU/network/checkpoint overhead.
Bảng report có carbon từng job, năm vùng USD/kWh, gCO2e/kWh, tiền điện và carbon.

Tổng 1.789.000 Wh: carbon 679.820 → 53.670 gCO2e, giảm **626.150 gCO2e (92.11%)**.
Điện us-east-1 214.68 USD, cleanest europe-north1 161.01 USD, cheapest us-east-wa 98.39 USD.
Balanced theo tổng price/max price + carbon/max carbon, trọng số bằng nhau: us-east-wa.
Giá điện chỉ để so sánh, không cộng lại vào GPU rental; nhãn vùng là minh họa, chưa xác nhận provider/GPU availability.
Chưa có carbon theo giờ; cân nhắc latency, data residency và GPU availability.

---

## 11. Chuẩn bị nộp bài

### Checklist trước khi nộp

```
[ ] python verify.py  →  11/11 checks passed
[ ] pytest -q → 15 passed (tests gốc, giữ nguyên)
[ ] pytest -q tests checks → 50 passed (15 gốc + 19 mở rộng + 16 bonus)
[ ] outputs/report.md tồn tại và có đủ các section
[ ] outputs/savings.png tồn tại và đọc được; matplotlib cần để nộp đủ artifact
[ ] outputs/focus_export.csv tồn tại
[ ] Đã thực hiện ≥2 extension với kết quả đo lường
```

### Bài viết ngắn đi kèm (write-up)

Viết 1–2 trang (không có template cứng) trả lời:

1. **Baseline vs. Optimized:** Chi phí trước và sau, `$/1M-token` trước và sau. Tiết kiệm tổng cộng bao nhiêu %?
2. **Phân tích từng đòn bẩy:** Đòn bẩy nào đóng góp nhiều nhất? Tại sao?
3. **GPU-Util Lie:** GPU nào bị "lie"? Tác động tài chính là gì?
4. **Phần mở rộng đã làm:** Mô tả từng extension, kết quả đo được, insight quan trọng nhất.
5. **Khuyến nghị cho NimbusAI:** Nếu bạn là FinOps lead, 3 hành động đầu tiên bạn sẽ làm là gì?

### File cần nộp

```
outputs/report.md
outputs/savings.png
outputs/focus_export.csv
outputs/writeup.md
```

Có thể kèm `outputs/after.json`, `outputs/before/` và `outputs/validation.txt` làm bằng chứng trước/sau;
bốn file trong danh sách trên là các file nộp bắt buộc.

---

## 12. Các lỗi thường gặp

### Lỗi: `ModuleNotFoundError: No module named 'pandas'`

```bash
# Kiểm tra virtual environment đã được kích hoạt chưa
which python   # Phải trỏ vào .venv/bin/python
pip install -r requirements.txt
```

### Lỗi: `FileNotFoundError: data/gpu_telemetry.csv`

```bash
python data/generate.py   # Sinh lại dữ liệu trước
```

### Lỗi: verify.py fail ở M2 savings out of band

Kiểm tra `finops/pricing.py` — hàm `request_cost()` có đang áp dụng đúng `cache_discount=0.10` và `batch_discount=0.50` không?

### Lỗi: pytest fail `test_flag_util_lies`

Hàm `flag_util_lies()` cần:
- Nhận `gpu_util_pct` theo thang 0–100
- Nhưng so sánh nội bộ chia 100 (`util = float(r["gpu_util_pct"]) / 100.0`)
- Ngưỡng: `util >= 0.90` VÀ `mfu < 0.30`

### Lỗi: matplotlib không tạo được PNG

Verify cơ bản có thể pass nếu thiếu PNG, nhưng bài nộp và checks mở rộng yêu cầu PNG. Kiểm tra `python -m pip show matplotlib` và cài dependencies để tạo đủ artifact.

### Warnings về `is_batch` type

Nếu thấy warning về kiểu dữ liệu bool, kiểm tra:
```python
is_batch = bool(int(num(r["is_batch"])))   # Không phải bool(r["is_batch"]) trực tiếp
```

---

## 13. Bonus hoàn thiện (không chấm điểm)

Cả ba bonus có code chạy được và evidence riêng tại [outputs/bonus/report.md](outputs/bonus/report.md).
Đọc [tracker](bonus/litellm_tracker/README.md), [CPU benchmark](bonus/local_model/README.md),
[Docker observability](bonus/docker/README.md). Model/library là dependencies tùy chọn;
graded requirements giữ nhẹ, không cần model/GPU/Docker.

```bash
python bonus/litellm_tracker/demo.py
python -m pip install -r bonus/local_model/requirements.txt
python bonus/local_model/run_local.py --strict
docker compose -f bonus/docker/docker-compose.yml up -d --wait --wait-timeout 90
python bonus/verify.py --docker --model
pytest -q checks/test_bonus.py # 16 bonus tests
```

CPU benchmark dùng warm-up và nhiều lần đo, output-only cost, ghi rõ giá CPU giả định.
Exporter có MFU/MBU/util/power/cost/idle, health endpoint và datasource dashboard được provisioning.
Theo dõi [validation bonus](outputs/bonus/validation.json); không gọi skipped là đã benchmark thành công.
Dừng stack với `docker compose -f bonus/docker/docker-compose.yml down`.
