# NimbusAI — GPU Cost Optimization Report

**Period:** 30-day capacity planning scenario

**Baseline spend:** $27,133.62

**Optimized spend:** $15,352.83

**Projected savings:** $11,780.79  (**43.42%**)

## Savings by lever

| Lever | Savings (USD) |
|---|---|
| Inference (cascade/cache/batch) | $1,199.22 |
| Purchasing (spot/reserved) | $9,742.17 |
| Right-sizing (conditional) | $461.40 |
| Idle shutdown (conditional) | $378.00 |

## Sustainability

- Energy per query: 13.20 Wh
- Carbon per query: 5.015 gCO2e
- Cleanest region: europe-north1
- Cheapest electricity region: us-east-wa
- Balanced region (equal normalized price/carbon weights): us-east-wa

_Illustrative June-2026 lab figures; validate prices and assumptions before acting._

## Phạm vi và cách đối chiếu

Tiết kiệm dự kiến chính xác: **43.42%**. Chỉ cascade/cache/batch và purchasing: optimized **$16,192.23**, savings **40.32%**. Hai lever GPU còn lại là dự báo có điều kiện.

M2 là hóa đơn API; M3 là danh mục GPU độc lập trong mô phỏng. Cộng chúng để lập ngân sách chỉ khi chúng là hai khoản chi riêng. Nếu API log mô tả inference tự host trên chính GPU M3, không cộng hai hóa đơn. Không quy chi phí training thành $/1M-token vì workload không có sản lượng token.

Kịch bản chính dùng 30 ngày cho mọi job và giả định đã có pool reserved 3yr có thể tái sử dụng. Reserved tính đủ 24h/ngày; tắt máy không giảm tiền cam kết. Right-sizing reserved chỉ giảm chi phí công suất khi tái phân bổ cam kết hoặc điều chỉnh ở kỳ gia hạn. CSV không nối gpu_id với job_id: ánh xạ dưới đây là giả định để định lượng, cần xác nhận trước triển khai.

Giá, interruption, carbon và điện là dữ liệu/giả định minh họa của lab, không phải báo giá hiện hành. Không có benchmark chất lượng cascade, throughput GPU hay đo điện phần cứng thực tế.

## M1 — Hiệu quả, idle và right-sizing

| GPU | Util % | MFU | MBU | Idle h | Max VRAM GB |
| --- | --- | --- | --- | --- | --- |
| gpu-h100-0 | 94.4 | 0.417 | 0.446 | 0 | 67.5 |
| gpu-h100-1 | 95.2 | 0.408 | 0.440 | 0 | 67.5 |
| gpu-h100-2 | 94.3 | 0.401 | 0.423 | 0 | 67.2 |
| gpu-h100-3 | 93.1 | 0.427 | 0.444 | 0 | 67.5 |
| gpu-h100-4 | 98.2 | 0.194 | 0.207 | 0 | 67.0 |
| gpu-h100-5 | 61.1 | 0.261 | 0.271 | 8 | 66.3 |
| gpu-a100-0 | 31.4 | 0.259 | 0.276 | 0 | 67.7 |
| gpu-a100-1 | 28.0 | 0.236 | 0.247 | 0 | 67.0 |
| gpu-a10g-0 | 25.0 | 0.219 | 0.235 | 0 | 20.3 |
| gpu-a10g-1 | 96.9 | 0.268 | 0.302 | 0 | 20.4 |
| gpu-l4-0 | 40.0 | 0.302 | 0.328 | 0 | 20.2 |

GPU-Util đo phần thời gian GPU có kernel hoạt động; kernel có thể chờ bộ nhớ hoặc dùng ít tensor cores. MFU thấp cùng util cao là tín hiệu cần profile, chưa chứng minh nguyên nhân. gpu-h100-4: util 98.2%, MFU 0.194; gpu-a10g-1: util 96.9%, MFU 0.268.

Idle quan sát: $20.00/ngày, $600.00/30 ngày, 3.90% chi phí on-demand của fleet telemetry. Đây là tỷ lệ fleet telemetry, không phải tỷ lệ tổng ngân sách M2+M3.

| GPU type | $/h | VRAM GB | $/GB-h | BW TB/s |
| --- | --- | --- | --- | --- |
| H100 | 2.5 | 80.0 | 0.03125 | 3.35 |
| H200 | 3.95 | 141.0 | 0.02801 | 4.8 |
| A100 | 1.79 | 80.0 | 0.02237 | 2.0 |
| A10G | 1.0 | 24.0 | 0.04167 | 0.6 |
| L4 | 0.8 | 24.0 | 0.03333 | 0.3 |
| B200 | 5.09 | 192.0 | 0.02651 | 8.0 |
| MI300X | 1.95 | 192.0 | 0.01016 | 5.3 |

### Extension 2 — Right-sizing theo MBU

Giả định decode/embed là memory-bound; MBU thấp tự nó không xác định roofline. Kiểm tra max VRAM × 1.10, max bandwidth/0.80 và max TFLOPs/0.80. Trong nhóm đạt năng lực, decode/embed ưu tiên $/GB-h thấp rồi giá/giờ; training util-lie xét giá/giờ trong nhóm đủ năng lực.

| GPU | Hiện tại → đề xuất | VRAM cần GB | $/GB-h trước → sau | USD/30 ngày OD | Lý do |
| --- | --- | --- | --- | --- | --- |
| gpu-a100-0 | A100 → A100 | 74.47 | 0.02237 → 0.02237 | 0.00 | No cheaper GPU passes VRAM, bandwidth and compute capacity screens; VRAM >= 74.47 GB; BW >= 0.884 TB/s; FP16 >= 112.0 TFLOPs; 10% VRAM headroom, target MFU/MBU 80%; benchmark required |
| gpu-a100-1 | A100 → A100 | 73.70 | 0.02237 → 0.02237 | 0.00 | No cheaper GPU passes VRAM, bandwidth and compute capacity screens; VRAM >= 73.70 GB; BW >= 0.846 TB/s; FP16 >= 103.2 TFLOPs; 10% VRAM headroom, target MFU/MBU 80%; benchmark required |
| gpu-a10g-0 | A10G → L4 | 22.33 | 0.04167 → 0.03333 | 144.00 | VRAM >= 22.33 GB; BW >= 0.227 TB/s; FP16 >= 39.0 TFLOPs; 10% VRAM headroom, target MFU/MBU 80%; benchmark required |
| gpu-a10g-1 | A10G → L4 | 22.44 | 0.04167 → 0.03333 | 144.00 | VRAM >= 22.44 GB; BW >= 0.265 TB/s; FP16 >= 46.7 TFLOPs; 10% VRAM headroom, target MFU/MBU 80%; benchmark required |
| gpu-l4-0 | L4 → L4 | 22.22 | 0.03333 → 0.03333 | 0.00 | No cheaper GPU passes VRAM, bandwidth and compute capacity screens; VRAM >= 22.22 GB; BW >= 0.147 TB/s; FP16 >= 49.7 TFLOPs; 10% VRAM headroom, target MFU/MBU 80%; benchmark required |
| gpu-h100-4 | H100 → A100 | 73.70 | 0.03125 → 0.02237 | 511.20 | VRAM >= 73.70 GB; BW >= 1.135 TB/s; FP16 >= 281.9 TFLOPs; 10% VRAM headroom, target MFU/MBU 80%; benchmark required |

A100 inference cần khoảng 74 GB sau headroom, nên L4/A10G 24 GB không đạt dù rẻ hơn. A10G → L4 là đề xuất cần benchmark. Chưa có bằng chứng throughput hoặc software stack tương thích.

### Đối chiếu savings sau purchasing

| GPU | Job giả định | GPU trước → sau | Tier | Idle USD | Right-size USD |
| --- | --- | --- | --- | --- | --- |
| gpu-h100-4 | job-train-llm | H100 → A100 | spot | 0.00 | 245.40 |
| gpu-h100-5 | job-train-llm | H100 → H100 | spot | 378.00 | 0.00 |
| gpu-a10g-0 | job-infer-chat | A10G → L4 | reserved | 0.00 | 108.00 |
| gpu-a10g-1 | job-infer-chat | A10G → L4 | reserved | 0.00 | 108.00 |

Tính idle theo rate sau purchasing trước, rồi right-sizing trên giờ còn hoạt động của từng GPU. Giả định giờ budget của GPU được ánh xạ chứa idle quan sát; phải xác minh runtime/productive hours. Không cộng lại toàn bộ savings on-demand của M1; không ghi nhận idle savings cho reserved.

## M2 — Unit economics và đóng góp tuần tự

| Giai đoạn | USD/ngày | $/1M-token | Savings tăng thêm USD/ngày |
| --- | --- | --- | --- |
| Baseline | 48.874161 | 6.487984 | — |
| Cascade | 11.475643 | 1.523377 | 37.398518 |
| + Cache incl. writes | 10.694624 | 1.419698 | 0.781019 |
| + Batch | 8.900059 | 1.181472 | 1.794565 |

Cùng **7,533,027 token/ngày**, inference giảm **81.8%**. Cascade đóng góp lớn nhất do đa số request đi model nhỏ. Model/output token không đổi giữa các stage. Cần đánh giá chất lượng để xác nhận route_tier. 0.5 × 0.1 = 0.05 chỉ cho input đã cache 100%, chưa bao gồm output và phí ghi. Batch chỉ dùng cho traffic is_batch=1 chấp nhận độ trễ.

### Extension 3 — Kinh tế cache

CSV không có prefix ID/số reads; giả định **4 reads/write** và phí ghi bổ sung **1.25 × giá input/1M token**, tách khỏi tiền input thường. Số token ghi ước lượng = cached tokens / reads; phí ghi không hưởng batch discount. Hòa vốn = write price / [input price × (1-read_discount) × batch multiplier].

| Tier | Write USD/1M | Reads hòa vốn sync | Reads hòa vốn batch |
| --- | --- | --- | --- |
| small | 0.2500 | 1.3889 | 2.7778 |
| large | 3.7500 | 1.3889 | 2.7778 |

Optimized cũ bỏ qua writes: $8.484623/ngày ($1.126323/1M-token). Tính writes: $8.900059/ngày; write fee $0.415436/ngày.

| Reads/write giả định | Request bật cache | Write USD/ngày | USD/ngày | $/1M-token |
| --- | --- | --- | --- | --- |
| 0.5 | 0 | 0.000000 | 9.658588 | 1.282166 |
| 1.0 | 0 | 0.000000 | 9.658588 | 1.282166 |
| 4.0 | 2400 | 0.415436 | 8.900059 | 1.181472 |
| 20.0 | 2400 | 0.083087 | 8.567710 | 1.137353 |

Ít reads: bỏ cache để tránh trả phí ghi nhiều hơn savings; nhiều reads: phân bổ phí ghi qua nhiều lần đọc nên đơn giá giảm. Không gọi số reads giả định là phép đo thực tế.

### Extension 4 — Ngân sách reasoning

| is_reasoning | Requests (%) | Tokens (%) | USD/ngày (%) | Wh/ngày (%) |
| --- | --- | --- | --- | --- |
| 0 | 2199 (91.62%) | 6,291,871 (83.52%) | 7.495613 (84.22%) | 1887.56 (5.96%) |
| 1 | 201 (8.38%) | 1,241,156 (16.48%) | 1.404445 (15.78%) | 29787.74 (94.04%) |

Cap 10%: đổi **0 request**; USD **8.900059 → 8.900059**; Wh **31675.31 → 31675.31**. Savings **$0.000000 và 0.00 Wh**.

Traffic đã dưới 10% thì savings bằng 0. Giữ nguyên input/output/model; nếu vượt cap, chỉ bỏ multiplier năng lượng 80× ở request dư, giữ request output dài nhất làm proxy độ phức tạp. Đây là counterfactual, không đảm bảo giữ chất lượng. Không nhân tiền với 80×; token output reasoning đã dài hơn trong CSV. Quy tắc triển khai: chỉ reasoning khi task phức tạp hoặc confidence thấp qua đánh giá, tối đa 10% traffic; scores đó chưa có trong dữ liệu.

## M3 — Purchasing và Extension 1

### Kế hoạch 30 ngày với pool reserved đã có

| Job | Tier | On-demand USD | Optimized USD |
| --- | --- | --- | --- |
| job-train-llm | spot | 12000.00 | 7560.00 |
| job-train-embed | spot | 2148.00 | 1399.20 |
| job-finetune | spot | 900.00 | 567.00 |
| job-infer-chat | reserved | 4320.00 | 2592.00 |
| job-infer-rag | reserved | 3866.40 | 2160.00 |
| job-infer-search | reserved | 1728.00 | 1296.00 |
| job-dev-sandbox | spot | 480.00 | 209.28 |
| job-batch-eval | spot | 225.00 | 141.75 |

30 ngày: $25667.40 → $15925.23; savings 38.0%. Reserved L4 18h/ngày vẫn tính 24h capacity.

### Thời gian job thực tế, mua cam kết mới

Dùng days trong CSV. Chi phí reserved tính đủ kỳ 365/1095 ngày × 24h, kể cả sau khi job xong; không giả định có job tiếp theo dùng phần dư. Nếu job vượt kỳ, mua nguyên số kỳ tiếp theo. Policy so tất cả tier hợp lệ, spot chỉ cho interruptible. Giá là catalog lab.

| GPU type | Interruption events/GPU-hour (giả định) |
| --- | --- |
| H100 | 0.04 |
| H200 | 0.05 |
| A100 | 0.06 |
| A10G | 0.12 |
| L4 | 0.08 |
| B200 | 0.05 |
| MI300X | 0.07 |

| Job | Days | Tier cũ → mới | Estimate cũ USD | OD USD | Mới USD | Lý do |
| --- | --- | --- | --- | --- | --- | --- |
| job-train-llm | 14.0 | spot → spot | 3544.80 | 5600.00 | 3528.00 | Choose least total cost including GPU-specific interruptions and checkpoint/rework |
| job-train-embed | 5.0 | spot → spot | 232.10 | 358.00 | 233.20 | Choose least total cost including GPU-specific interruptions and checkpoint/rework |
| job-finetune | 3.0 | spot → spot | 56.97 | 90.00 | 56.70 | Choose least total cost including GPU-specific interruptions and checkpoint/rework |
| job-infer-chat | 30.0 | reserved → on_demand | 2592.00 | 4320.00 | 4320.00 | Short job cannot amortize a new 365/1095-day commitment |
| job-infer-rag | 30.0 | reserved → on_demand | 2160.00 | 3866.40 | 3866.40 | Short job cannot amortize a new 365/1095-day commitment |
| job-infer-search | 30.0 | reserved → on_demand | 972.00 | 1728.00 | 1728.00 | Short job cannot amortize a new 365/1095-day commitment |
| job-dev-sandbox | 22.0 | spot → spot | 148.54 | 352.00 | 153.47 | Choose least total cost including GPU-specific interruptions and checkpoint/rework |
| job-batch-eval | 30.0 | spot → spot | 142.43 | 225.00 | 141.75 | Choose least total cost including GPU-specific interruptions and checkpoint/rework |

Tổng actual-days: OD **$16539.40**, policy mới **$14027.52**, savings **15.19%**. Estimate policy cũ trên cùng days **$9848.84**, savings **40.45%**. Estimate cũ tính trên cùng days nhưng bỏ nghĩa vụ cam kết và dùng interruption chung 0.05. Policy mới có thể trông đắt hơn vì đã tính nghĩa vụ thật; không phải cứ tăng savings là đúng.

| Job | OD USD | Spot USD | Reserved 1yr USD | Reserved 3yr USD |
| --- | --- | --- | --- | --- |
| job-train-llm | 5600.00 | 3528.00 | 140160.00 | 294336.00 |
| job-train-embed | 358.00 | 233.20 | 49056.00 | 105120.00 |
| job-finetune | 90.00 | 56.70 | 35040.00 | 73584.00 |
| job-infer-chat | 4320.00 | không hợp lệ | 42048.00 | 94608.00 |
| job-infer-rag | 3866.40 | không hợp lệ | 36792.00 | 78840.00 |
| job-infer-search | 1728.00 | không hợp lệ | 21024.00 | 47304.00 |
| job-dev-sandbox | 352.00 | 153.47 | 14016.00 | 31536.00 |
| job-batch-eval | 225.00 | 141.75 | 17520.00 | 36792.00 |

### Matrix policy: GPU × duty × interruptible × duration

| GPU | h/ngày | Interruptible | Days | Tier |
| --- | --- | --- | --- | --- |
| H100 | 4 | 0 | 30 | on_demand |
| H100 | 4 | 0 | 365 | on_demand |
| H100 | 4 | 0 | 1095 | on_demand |
| H100 | 4 | 1 | 30 | spot |
| H100 | 4 | 1 | 365 | spot |
| H100 | 4 | 1 | 1095 | spot |
| H100 | 24 | 0 | 30 | on_demand |
| H100 | 24 | 0 | 365 | reserved_1yr |
| H100 | 24 | 0 | 1095 | reserved_3yr |
| H100 | 24 | 1 | 30 | spot |
| H100 | 24 | 1 | 365 | spot |
| H100 | 24 | 1 | 1095 | reserved_3yr |
| A10G | 4 | 0 | 30 | on_demand |
| A10G | 4 | 0 | 365 | on_demand |
| A10G | 4 | 0 | 1095 | on_demand |
| A10G | 4 | 1 | 30 | spot |
| A10G | 4 | 1 | 365 | spot |
| A10G | 4 | 1 | 1095 | spot |
| A10G | 24 | 0 | 30 | on_demand |
| A10G | 24 | 0 | 365 | reserved_1yr |
| A10G | 24 | 0 | 1095 | reserved_3yr |
| A10G | 24 | 1 | 30 | spot |
| A10G | 24 | 1 | 365 | spot |
| A10G | 24 | 1 | 1095 | spot |
| L4 | 4 | 0 | 30 | on_demand |
| L4 | 4 | 0 | 365 | on_demand |
| L4 | 4 | 0 | 1095 | on_demand |
| L4 | 4 | 1 | 30 | spot |
| L4 | 4 | 1 | 365 | spot |
| L4 | 4 | 1 | 1095 | spot |
| L4 | 24 | 0 | 30 | on_demand |
| L4 | 24 | 0 | 365 | reserved_1yr |
| L4 | 24 | 0 | 1095 | reserved_3yr |
| L4 | 24 | 1 | 30 | spot |
| L4 | 24 | 1 | 365 | spot |
| L4 | 24 | 1 | 1095 | spot |

Spot effective hours = productive GPU-hours × (1 + checkpoint overhead + interruption rate × rework). Đó là thời gian trả thêm cho checkpoint/rework, không phải thêm sản lượng. Job infer 30 ngày chuyển reserved → on-demand khi mua mới vì không đủ dài để trả cam kết cả năm.

## M4 — Allocation và FOCUS-style export

| Team | USD/ngày | % tổng |
| --- | --- | --- |
| assistant | 2.815685 | 31.64% |
| search | 2.517908 | 28.29% |
| eval | 1.810183 | 20.34% |
| rag | 1.756282 | 19.73% |

Tag coverage team/project **91.79%**; gate **80%**; chargeback ready **True**. Export **2400 request**, tổng BilledCost **$8.900059/ngày**, bằng M2 optimized có writes.

Đây là tập cột FOCUS-style dùng học tập, chưa là chứng nhận tuân thủ toàn bộ schema FOCUS. Chuẩn hóa cùng trường chi phí/tags giúp so nhiều provider mà không cần đổi định nghĩa tiền. Request thiếu project giữ nguyên để không che giấu coverage.

## Extension 5 — Carbon-aware scheduling

Chỉ interruptible=1; giữ nguyên productive GPU-hours của từng job, dùng **days thực tế**. Wh = catalog watts × GPU-hours; đây là ước tính GPU rated power, chưa có PUE/CPU/network hay checkpoint overhead. So cùng lượng công việc ở mọi vùng; giá điện không cộng thêm vào giá GPU thuê, vì có thể đã nằm trong hóa đơn nhà cung cấp. Region labels là dữ liệu minh họa, không khẳng định GPU/provider tương ứng có mặt ở vùng đó.

| Job | GPU-hours | Wh | us-east-1 gCO2e | Cleanest gCO2e | Giảm gCO2e |
| --- | --- | --- | --- | --- | --- |
| job-train-llm | 2240 | 1568000 | 595840.00 | 47040.00 | 548800.00 |
| job-train-embed | 200 | 80000 | 30400.00 | 2400.00 | 28000.00 |
| job-finetune | 36 | 25200 | 9576.00 | 756.00 | 8820.00 |
| job-dev-sandbox | 352 | 52800 | 20064.00 | 1584.00 | 18480.00 |
| job-batch-eval | 90 | 63000 | 23940.00 | 1890.00 | 22050.00 |

| Region | USD/kWh | gCO2e/kWh | Điện USD | Carbon gCO2e |
| --- | --- | --- | --- | --- |
| us-east-1 | 0.12 | 380 | 214.68 | 679820.00 |
| us-west-2 | 0.07 | 120 | 125.23 | 214680.00 |
| europe-north1 | 0.09 | 30 | 161.01 | 53670.00 |
| europe-central2 | 0.18 | 660 | 322.02 | 1180740.00 |
| us-east-wa | 0.055 | 90 | 98.39 | 161010.00 |

Tổng giảm **626,150.00 gCO2e** (**92.11%**). Sạch nhất **europe-north1**; rẻ nhất **us-east-wa**; cân bằng theo tổng price/max(price) + carbon/max(carbon) với trọng số bằng nhau **us-east-wa**. Chưa có dữ liệu giờ để tối ưu theo giờ.

Ưu tiên batch/train có thể di chuyển; kiểm tra latency, dữ liệu lưu trú và khả dụng GPU trước khi chọn vùng. Vùng sạch hơn có thể xa người dùng; job realtime giữ gần người dùng.

## Khuyến nghị ưu tiên

1. Bật cascade cho tác vụ đã kiểm định chất lượng; cache qua gate hòa vốn và batch cho eval. Theo dõi $/1M-token và chất lượng trước rollout.

2. Dùng spot với checkpoint cho job interruptible; không mua cam kết mới cho job ngắn. Với pool reserved hiện hữu, theo dõi toàn bộ giờ cam kết và tái sử dụng capacity bỏ trống.

3. Tắt idle on-demand/spot, benchmark các đề xuất right-sizing; giữ gate tagging 80%, giới hạn reasoning và chuyển batch/train đến vùng sạch khi latency cho phép.

## Bằng chứng trước/sau

Seed=25; SHA-256 của bốn CSV trùng baseline: **True**. Baseline được lưu trước khi sửa code trong before/baseline.json và các artifact before/.

| Chỉ số | Code gốc | Sau sửa | Giải thích |
| --- | --- | --- | --- |
| M2 USD/ngày | 8.48 | 8.900059 | Tính thêm cache writes |
| M3 optimized 30 ngày USD | 15627 | 15925.23 | Reserved đủ 24h + rate theo GPU |
| M5 savings % | 46.1 | 43.42 | Không cộng trùng và nêu savings có điều kiện |
| FOCUS rows | 50 | 2400 | Đối chiếu toàn bộ hóa đơn |

## Bonus — bằng chứng chạy riêng

Tracker mock và các kiểm tra đã lưu: exporter, docker, model. Đọc [report bonus](bonus/report.md) và [validation.json](bonus/validation.json) cho thời điểm/kết quả đã ghi; chạy bonus/verify.py --docker --model để kiểm tra lại. Chi phí bonus không cộng thêm vào ngân sách M1–M5.
