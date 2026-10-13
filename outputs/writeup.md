# Bài viết — GPU FinOps, Lab 25

Dữ liệu mô phỏng seed=25: 7 GPU type, 11 GPU × 24h, 2.400 request và 8 job.
Bảng đầy đủ ở [report.md](report.md); kết quả trước sửa ở [before/baseline.json](before/baseline.json).

## 1. Baseline vs. Optimized

| Chỉ số | Baseline | Optimized |
|---|---|---|
| Chi phí kế hoạch 30 ngày (USD) | 27,133.62 | 15,352.83 |
| Inference (USD/1M-token) | 6.487984 | 1.181472 |

Tổng tiết kiệm dự kiến **11,780.79 USD (43.42%)**;
inference giữ 7,533,027 token/ngày, giảm 81.8%.
Kế hoạch giả định pool reserved hiện hữu, tính đủ 24h/ngày. API và GPU chỉ cộng khi là hai khoản chi riêng;
không quy chi phí training theo token API. Bỏ hai lever GPU có điều kiện, optimized còn
16,192.23 USD (40.32% savings).

## 2. Phân tích từng đòn bẩy

| Lever | USD/30 ngày | % tổng savings |
| --- | --- | --- |
| Inference (cascade/cache/batch) | 1,199.22 | 10.18% |
| Purchasing (spot/reserved) | 9,742.17 | 82.70% |
| Right-sizing (conditional) | 461.40 | 3.92% |
| Idle shutdown (conditional) | 378.00 | 3.21% |

**Purchasing (spot/reserved)** đóng góp nhiều nhất theo USD vì ngân sách GPU lớn và spot/reserved giảm giá thuê.
Trong inference, cascade giảm 37.398518 USD/ngày,
lớn hơn cache 0.781019
và batch 1.794565,
do đa số request dùng model nhỏ. Cache tính cả writes; batch chỉ cho traffic chấp nhận độ trễ.
Right-sizing kiểm tra năng lực rồi tính theo rate sau purchasing; idle chỉ giảm giờ trả tiền
của on-demand/spot. Tính idle trước resize trên giờ còn lại để tránh cộng trùng.

## 3. GPU-Util Lie và tác động tài chính

- **gpu-h100-4**: util 98.2%, MFU 0.194.
- **gpu-a10g-1**: util 96.9%, MFU 0.268.

Util đo thời gian kernel hoạt động; kernel có thể chờ bộ nhớ hoặc dùng ít tensor cores.
MFU thấp là tín hiệu cần profiler, chưa chứng minh nguyên nhân. Hai GPU bị flag có tiềm năng
right-sizing **353.40 USD/30 ngày** trong ánh xạ GPU → job giả định, gồm H100 → A100
và A10G → L4. Cần benchmark throughput; không quy toàn bộ phần FLOPs chưa dùng thành tiền thu hồi.
Idle là vấn đề riêng: fleet telemetry lãng phí 600.00 USD/30 ngày on-demand,
nhưng waterfall chỉ ghi 378.00 USD sau purchasing.

## 4. Năm phần mở rộng: kết quả và insight

1. **Tier policy:** so interruption theo GPU type (giả định) và toàn bộ nghĩa vụ reserved 365/1095 ngày.
   Trên days thực tế: 16539.40 → 14027.52 USD,
   giảm 15.19%. Job inference 30 ngày chọn on-demand khi mua mới;
   không so tổng kỳ actual-days với kỳ kế hoạch 30 ngày.
2. **Right-sizing MBU:** max VRAM ×1.10; peak BW/TFLOPs tại target 80%.
   A100 cần hơn 73 GB nên không thể thay bằng GPU 24GB. Hai A10G → L4 có tiềm năng
   **288.00 USD/30 ngày on-demand**; bảng sau purchasing dùng rate khác.
   Chưa benchmark throughput/tương thích software; MBU thấp chưa chứng minh memory-bound.
3. **Cache:** CSV thiếu prefix IDs/reads: giả định 4 reads/write, phí ghi thêm 1.25× input price.
   Hòa vốn sync 1.389 reads, batch 2.778. Bỏ writes: 8.484623 USD/ngày;
   có writes: 8.900059. Case 0.5/1 read tắt cache, 4/20 reads bật.
   Insight: cache phải bù phí ghi, không mặc định tiết kiệm ở mọi traffic.
4. **Reasoning:** 8.38% request nhưng
   94.04% năng lượng. Cap 10% đổi 0 request:
   8.900059 → 8.900059 USD/ngày,
   31675.31 → 31675.31 Wh/ngày.
   Dưới cap nên savings bằng 0. Giữ tokens/model; multiplier 80× là giả định Wh, không phải tiền.
5. **Carbon scheduling:** cùng productive GPU-hours, days thực tế, Wh = catalog watts × GPU-hours.
   Chuyển interruptible us-east-1 → europe-north1 giảm **626,150.00 gCO2e**.
   Điện rẻ nhất ở us-east-wa, vùng cân bằng us-east-wa.
   Vùng sạch nhất không đồng nghĩa rẻ nhất; chưa tính PUE/CPU/network/checkpoint hoặc latency.

## 5. Ba hành động đầu tiên cho NimbusAI

1. Kiểm định chất lượng cascade rồi áp dụng cache đủ hòa vốn và batch; theo dõi USD/1M-token,
   chất lượng và latency để bảo đảm giảm tiền vẫn đáp ứng sản phẩm.
2. Checkpoint + spot cho job interruptible; mua reserved mới chỉ khi tính đủ kỳ cam kết có lợi.
   Tái sử dụng pool reserved hiện hữu và ưu tiên tắt idle on-demand/spot.
3. Benchmark right-sizing, duy trì tagging trước chargeback và chuyển batch/train đến vùng sạch
   khi latency/khả dụng cho phép. Chỉ reasoning cho task phức tạp/confidence thấp, cap 10%.

Tag coverage 91.79% vượt gate 80%; FOCUS-style export đủ 2400 request,
tổng 8.900059 USD/ngày khớp M2. Giá/điện/carbon là giả định lab; chưa có benchmark GPU,
chất lượng model hay đo điện thật. Savings GPU có điều kiện được ghi riêng trong report.
