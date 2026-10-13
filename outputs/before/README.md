# Kết quả trước khi sửa code

Các artifact trong thư mục này là **baseline lịch sử**, được lưu trước khi triển khai phần mở rộng.
Báo cáo lưu trữ đã được chuyển encoding CP1252 → UTF-8, giữ nguyên nội dung tài chính.
Giữ số liệu cũ để so sánh; báo cáo hiện hành nằm ở [../report.md](../report.md).

- `baseline.json`: kết quả M1–M5 code gốc và SHA-256 bốn CSV.
- `report.md`, `savings.png`, `focus_export.csv`: artifact code gốc, không sinh lại khi chạy mission mới.
- Code gốc dùng 30 ngày cho tất cả job, bỏ cache writes, reserved chỉ tính giờ sử dụng,
  và cộng savings idle/right-sizing on-demand sau purchasing. Report mới giải thích các sửa đổi này.

Chạy `python -m pytest -q checks` ở root để xác nhận hashes dữ liệu hiện tại trùng baseline.
Xem `outputs/after.json` để đối chiếu kết quả mới; không so tổng chi phí hai kỳ thời gian khác nhau.
