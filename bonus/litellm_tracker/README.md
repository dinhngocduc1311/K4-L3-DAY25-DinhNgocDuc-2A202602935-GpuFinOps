# Bonus — Tracker chi phí và budget cap

Mô phỏng backend LLM kiểu LiteLLM, không cần API key thật. Chạy từ root project:

```bash
python bonus/litellm_tracker/demo.py
```

Demo có 10 chat request được phục vụ trước khi request tiếp theo vượt cap 0.05 USD và bị chặn.
Team eval dùng model nhỏ + batch, vẫn chạy độc lập. Ledger giữ cost đầy đủ precision; chỉ làm tròn khi in.
Đầu vào budget/token/model/batch được kiểm tra. Budget check + ghi tiền dùng lock để tránh vượt cap
khi nhiều thread gọi cùng key.

Artifact:

- `outputs/bonus/tracker_requests.csv`: timestamp, alias key/team, model, input/output token và USD/request.
- `outputs/bonus/tracker_summary.json`: cap, spend theo key, số request và trạng thái blocked.
- Tổng cost CSV khớp tổng spend; request bị chặn không ghi thêm tiền hoặc log.

```bash
pytest -q checks/test_bonus.py
python bonus/verify.py
```

**Phạm vi:** đây là mock backend, output token = max_output_tokens; input dùng ước lượng 4 ký tự/token.
`api_key` là alias như `team-chat`, không nhập credential thật vì alias sẽ xuất ra ledger.
Budget là **theo phiên process**, không phải hóa đơn tháng và không lưu qua restart. Lock chỉ trong process.
Lab dùng cùng MODEL_PRICES với M2 nhưng bonus minh họa read-cache discount; không tính phí ghi cache
vì traffic demo không có prefix/write lifecycle. [Report chính](../../outputs/report.md) tính cache writes đầy đủ.

Để dùng provider thật cần thay mock bằng SDK/LiteLLM, lấy usage thật, dự trù chi phí trước call,
đối soát sau response và lưu budget trong kho dữ liệu chung. Phần đó không thuộc yêu cầu bonus mock.
