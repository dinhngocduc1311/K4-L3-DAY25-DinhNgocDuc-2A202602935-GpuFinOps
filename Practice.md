# Đề thực hành bổ sung (nguyên văn)

Thực hành
1. Khám phá dữ liệu
Tạo đầu vào cho các mission. Seed cố định giúp bạn dùng cùng dữ liệu khi so trước/sau:

python data/generate.py
Chép
Mở file	Xem gì?	Dùng để làm gì?
data/price_catalog.csv	Giá các tier, hbm_gb, peak_tflops_fp16, peak_bw_tbs	So giá, bộ nhớ và khả năng của GPU
data/gpu_telemetry.csv	gpu_util_pct, achieved_tflops, achieved_bw_tbs	Kiểm tra GPU bận và hiệu quả đến đâu
data/token_usage.csv	Input/output token, route, cache, batch, reasoning, tags	Tính tiền request và chia theo team
data/workloads.csv	hours_per_day, days, num_gpus, interruptible	Tính giờ chạy và chọn cách mua GPU
Đọc bằng pandas.read_csv theo ví dụ Guide.md, mục 3.

2. Chạy năm mission
Code cơ bản đã có sẵn. Với mỗi mission, đọc phần tính toán, chạy lệnh rồi đối chiếu output.

M1 — GPU có đang dùng hiệu quả không?
Mở finops/metrics.py, đọc compute_mfu(), compute_mbu() và flag_util_lies(). Xem cách tính tỷ lệ và điều kiện đánh dấu GPU.
Chạy:
python missions/m1_efficiency_audit.py
Chép
Trong bảng, so util% với MFU: util ≥90% nhưng MFU <0.30 là trường hợp bị flag. MBU cho biết hiệu quả dùng băng thông; idle_h là số giờ GPU bỏ không. Dòng Idle waste đổi số giờ đó thành tiền/ngày và tiền/tháng.
M2 — Mỗi triệu token tốn bao nhiêu tiền?
Mở finops/pricing.py, đọc request_cost() và dollars_per_million(). Mở missions/m2_inference_levers.py để xem giá model trong MODEL_PRICES.
Chạy:
python missions/m2_inference_levers.py
Chép
So baseline và optimized ở phần $/1M-token: cùng số token, mức thấp hơn nghĩa là phục vụ rẻ hơn. Dòng savings là phần trăm tiền giảm được. Muốn biết từng cách đóng góp bao nhiêu, tính lần lượt cascade → thêm cache → thêm batch.
M3 — Mỗi job nên mua GPU theo cách nào?
Mở finops/pricing.py, đọc recommend_tier() và spot_checkpoint_cost(). Xem policy chọn tier và chi phí thêm do checkpoint/rework.
Chạy:
python missions/m3_purchasing.py
Chép
Trong bảng, đọc tier của từng job và so on-demand với optimized. Dòng monthly là tổng trước/sau; phần trăm cuối dòng là savings purchasing.
M4 — Team nào dùng bao nhiêu tiền?
Mở finops/allocation.py, đọc cost_by_tag(), tag_coverage() và chargeback_ready() để xem cách chia tiền và kiểm tra tag.
Chạy:
python missions/m4_allocation.py
Chép
Đọc cost by team để tìm team tốn nhiều nhất. tag coverage cho biết tỷ lệ request có đủ team/project; chargeback ready? cho biết đã vượt gate 80% chưa. Mở outputs/focus_export.csv, xem BilledCost, team và project.
M5 — Tổng hợp thành báo cáo
Mở missions/m5_report.py, tìm levers để xem bốn khoản savings lấy từ đâu: inference, purchasing, right-sizing và idle.
Chạy:
python missions/m5_report.py
Chép
Mở outputs/report.md. Đọc Baseline spend, Optimized spend, Projected savings và bảng Savings by lever để đối chiếu tổng với từng khoản. Xem phần điện năng và phát thải CO₂: mỗi truy vấn dùng bao nhiêu điện, phát thải ước tính bao nhiêu và nên chạy ở vùng nào. Mở outputs/savings.png để xem biểu đồ.
Sau mỗi mission, dừng lại trả lời các câu hỏi phân tích tương ứng trong Guide.md (mục 4.3, 5.4, 6.4, 7.4) — đây là phần giúp bạn hiểu bản chất thay vì chỉ chạy script.

Để chạy lại cả năm sau khi sửa code:

python missions/run_all.py
Chép
3. Việc của bạn — Chọn ít nhất hai trong năm phần mở rộng
Phần này chiếm 20 điểm rubric. Trước khi sửa, lưu kết quả mission liên quan. Sau khi sửa, chạy lại với cùng dữ liệu để so sánh.

1. Cải thiện recommend_tier()
Mở/sửa: finops/pricing.py, hàm recommend_tier(); cập nhật chỗ gọi trong missions/m3_purchasing.py nếu thêm tham số.
Làm: cân nhắc interruption rate theo GPU type và reserved 1yr/3yr theo thời gian job. Rate bổ sung cần ghi rõ nguồn hoặc giả định.
Đo: bảng job → tier → chi phí trước/sau và savings_pct M3. Giải thích job nào đổi tier và vì sao.
2. Right-sizing theo MBU
Mở/sửa: missions/m1_efficiency_audit.py; đọc hbm_gb, peak_bw_tbs, on_demand_hr trong data/price_catalog.csv.
Làm: đề xuất GPU cho workload memory-bound dựa trên chi phí/GB-VRAM và bandwidth. Kiểm tra dung lượng cần dùng, không chỉ chọn GPU có giá/giờ thấp nhất.
Đo: bảng GPU hiện tại → GPU đề xuất → lý do → USD/tháng có thể tiết kiệm. Ghi rõ giới hạn nếu chưa có benchmark chứng minh throughput giữ nguyên.
3. cache_is_worth_it()
Mở/sửa: thêm hàm trong finops/pricing.py; gọi trước khi áp dụng cache trong missions/m2_inference_levers.py.
Làm: chỉ dùng cache khi tiền tiết kiệm từ đọc cache đủ bù tiền ghi. CSV không có số reads mỗi prefix; nếu tự đặt số reads/write cost, ghi là giả định.
Đo: ngưỡng reads hòa vốn và cost/$/1M-token trước/sau khi tính write cost. Kiểm tra cả trường hợp ít reads và nhiều reads.
4. Ngân sách Reasoning
Mở/sửa: missions/m2_inference_levers.py và missions/m5_report.py. Dùng wh_per_query() trong finops/sustainability.py.
Làm: tách nhóm is_reasoning=1 và 0; tính riêng tiền, token và Wh. Đề xuất khi nào dùng reasoning và thử cap 10% traffic.
Đo: tỷ trọng request/chi phí/năng lượng của mỗi nhóm, USD và Wh trước/sau cap. Nếu traffic đã dưới 10%, ghi savings bằng 0; nếu đổi output hoặc model, nêu rõ.
5. Carbon-aware Scheduling
Mở/sửa: missions/m3_purchasing.py hoặc file mới; đọc REGION_CARBON, REGION_PRICE_KWH, carbon_g() trong finops/sustainability.py.
Làm: chọn job interruptible=1; ước lượng Wh từ watts và GPU-hours. So chạy ở us-east-1 với các vùng khác, giữ cùng lượng công việc.
Đo: carbon trước/sau từng job và tổng gCO2e giảm. So giá điện và carbon để phân biệt vùng rẻ nhất, sạch nhất; ghi rõ dùng ngày thực tế hay tháng 30 ngày.
Ghi kết quả hai phần đã chọn vào báo cáo/bài viết. Chi tiết và code mẫu: Guide.md, mục 10; cách chấm: Rubric.md, phần D.

Checkpoint: có ít nhất hai thay đổi code chạy được, bảng trước/sau và giải thích rút ra từ số liệu. Các hoạt động trong bonus/ là tùy chọn, không chấm điểm.