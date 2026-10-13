# Bonus — Benchmark model thật trên CPU

Đo generation trên CPU bằng model nhỏ, **warm-up một lần rồi đo ba lần**.
Không cần GPU hay API key. Chạy từ root project bằng Python trong venv:

```bash
python -m pip install -r bonus/local_model/requirements.txt
python bonus/local_model/run_local.py --strict
```

macOS/Linux: kích hoạt `.venv/bin/activate`; Windows PowerShell: `.venv\Scripts\Activate.ps1`.
Hoặc gọi trực tiếp `.venv/Scripts/python.exe bonus/local_model/run_local.py --strict` trên Windows.

Model mặc định `sshleifer/tiny-gpt2` tải vào `.cache/huggingface/` trong project, đã gitignore.
JSON ghi commit model thực tế từ cache; có thể dùng `--revision <commit_hash>` để tái lập đúng weights.
Không commit model weights. Script dùng CPU, eval mode, inference_mode, seed=25,
deterministic generation, một thread mặc định và perf_counter. Không bật trust_remote_code.
Chạy lại model đã cache khi offline:

```bash
python bonus/local_model/run_local.py --offline --strict
python bonus/local_model/run_local.py --runs 5 --max-new-tokens 64 --threads 1 --cpu-rate-hr 0.10
python bonus/local_model/run_local.py --model Qwen/Qwen2.5-0.5B
```

Có thể dùng biến môi trường cũ `LAB_MODEL`/`LAB_CPU_RATE_HR`.
PowerShell: `$env:LAB_MODEL = 'Qwen/Qwen2.5-0.5B'`; Bash: `LAB_MODEL=Qwen/Qwen2.5-0.5B python bonus/local_model/run_local.py`.

Artifact `outputs/bonus/local_benchmark.json` có trạng thái, model/revision, phiên bản thư viện,
số thread, load time, từng lần đo, tok/s tổng hợp/median và chi phí ước tính.
Công thức: `USD/1M output tokens = (generation_seconds / 3600 × assumed_CPU_USD_hr) / new_tokens × 1e6`.
Chỉ đếm token sinh thêm, không đếm prompt vào tok/s/output cost; loại load và warm-up khỏi thời gian đo.

So với giá **output-only** của model nhỏ trong catalog lab (0.40 USD/1M output tokens).
M2 dùng input+output nên ghi riêng reference đó, không so hai denominator như cùng một phép đo.
Tiny model không có chất lượng tương đương model production; tốc độ đo thật, giá thuê CPU là giả định,
chưa gồm idle capacity/loading/warm-up hoặc chi phí hạ tầng khác.

Không có deps/model/inference: mặc định ghi `status: skipped` và thoát 0 để không phá lab.
`--strict` thoát 1 khi chưa benchmark thành công; tham số sai thoát 2.
Lần chạy skipped ghi đè JSON cũ bằng trạng thái mới để không báo nhầm benchmark cũ là thành công.

```bash
python bonus/verify.py --model
pytest -q checks/test_bonus.py
```

Cơ chế inference theo [PyTorch inference_mode](https://pytorch.org/docs/stable/generated/torch.inference_mode.html)
và tải model theo [Transformers model loading](https://huggingface.co/docs/transformers/main_classes/model).
