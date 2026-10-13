"""M5: reproducible report, five extensions and a reconciled planning waterfall."""
from __future__ import annotations
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import os
import json
import hashlib
from pathlib import Path
from missions._common import num, catalog_by_type, ROOT
from finops import report, sustainability, pricing
from missions import m1_efficiency_audit, m2_inference_levers, m3_purchasing, m4_allocation

DAYS = 30


def table(headers, rows):
    return "\n".join(["| " + " | ".join(headers) + " |",
                       "| " + " | ".join(["---"] * len(headers)) + " |"]
                      + ["| " + " | ".join(map(str, row)) + " |" for row in rows])


def capacity_adjustments(r1, r3, cat):
    """Hypothetical telemetry -> job assignment, after purchasing, once per GPU.

    The CSVs have no shared resource ID. These are explicit capacity-planning
    assumptions; released reservations must be reused to realize avoided spend.
    """
    proposals = {r["gpu_id"]: r for r in r1["right_sizing"] + r1["lie_sizing"]}
    remaining = {r["job_id"]: r["num_gpus"] for r in r3["recommendations"]}
    adjustments = []
    for s in r1["summary"]:
        proposal = proposals.get(s["gpu_id"])
        target = proposal["proposed_gpu"] if proposal else s["gpu_type"]
        if not s["idle_hours"] and target == s["gpu_type"]:
            continue
        kind = "train" if s["workload"] == "train" else "infer"
        job = next((j for j in r3["recommendations"] if j["kind"] == kind
                    and j["gpu_type"] == s["gpu_type"] and remaining[j["job_id"]] > 0), None)
        if job is None:
            continue
        remaining[job["job_id"]] -= 1
        current, new = cat[s["gpu_type"]], cat[target]
        active = job["hours_per_day"]
        idle_h = min(s["idle_hours"], active)
        tier = job["tier"]
        if tier == "spot":
            mult = 1.03 + pricing.INTERRUPTION_RATES[s["gpu_type"]] * 0.5
            rate = num(current["spot_hr"]) * mult
            # A replacement must use its own interruption rate.
            target_rate = num(new["spot_hr"]) * (1.03 + pricing.INTERRUPTION_RATES[target] * 0.5)
        elif tier == "reserved":
            rate, target_rate = num(current["reserved_3yr_hr"]), num(new["reserved_3yr_hr"])
            active, idle_h = 24, 0  # Switching off does not reduce a committed bill.
        else:
            rate, target_rate = num(current["on_demand_hr"]), num(new["on_demand_hr"])
        idle = idle_h * DAYS * rate
        rightsize = max(0, rate - target_rate) * (active - idle_h) * DAYS
        adjustments.append({"gpu_id": s["gpu_id"], "assumed_job_id": job["job_id"],
                            "current_gpu": s["gpu_type"], "proposed_gpu": target,
                            "tier": tier, "idle_savings": idle, "rightsize_savings": rightsize})
    return adjustments


def run(verbose=True):
    r1 = m1_efficiency_audit.run(False)
    r2 = m2_inference_levers.run(False)
    r3 = m3_purchasing.run(False)
    r4 = m4_allocation.run(False)
    cat = catalog_by_type()
    adjustments = capacity_adjustments(r1, r3, cat)
    levers = {
        "Inference (cascade/cache/batch)": (r2["baseline_daily"] - r2["optimized_daily"]) * DAYS,
        "Purchasing (spot/reserved)": r3["on_demand_monthly"] - r3["optimized_monthly"],
        "Right-sizing (conditional)": sum(r["rightsize_savings"] for r in adjustments),
        "Idle shutdown (conditional)": sum(r["idle_savings"] for r in adjustments),
    }
    baseline = r2["baseline_daily"] * DAYS + r3["on_demand_monthly"]
    optimized = baseline - sum(levers.values())
    proven_optimized = baseline - levers["Inference (cascade/cache/batch)"] - levers["Purchasing (spot/reserved)"]
    budget = r2["reasoning"]
    wh = budget["before_wh"] / r2["requests"] if r2["requests"] else 0
    sust = {"wh_per_query": wh, "carbon_g": sustainability.carbon_g(wh),
            "best_region": r3["cleanest_region"], "cheapest_region": r3["cheapest_region"],
            "balanced_region": r3["balanced_region"]}
    md = report.build_report(baseline, optimized, levers, sust, period="30-day capacity planning scenario")
    sections = [
        "## Phạm vi và cách đối chiếu",
        f"Tiết kiệm dự kiến chính xác: **{sum(levers.values())/baseline:.2%}**. "
        f"Chỉ cascade/cache/batch và purchasing: optimized **${proven_optimized:,.2f}**, "
        f"savings **{1-proven_optimized/baseline:.2%}**. Hai lever GPU còn lại là dự báo có điều kiện.",
        "M2 là hóa đơn API; M3 là danh mục GPU độc lập trong mô phỏng. Cộng chúng để lập ngân sách "
        "chỉ khi chúng là hai khoản chi riêng. Nếu API log mô tả inference tự host trên chính GPU M3, "
        "không cộng hai hóa đơn. Không quy chi phí training thành $/1M-token vì workload không có sản lượng token.",
        "Kịch bản chính dùng 30 ngày cho mọi job và giả định đã có pool reserved 3yr có thể tái sử dụng. "
        "Reserved tính đủ 24h/ngày; tắt máy không giảm tiền cam kết. Right-sizing reserved chỉ giảm chi "
        "phí công suất khi tái phân bổ cam kết hoặc điều chỉnh ở kỳ gia hạn. "
        "CSV không nối gpu_id với job_id: ánh xạ dưới đây là giả định để định lượng, cần xác nhận trước triển khai.",
        "Giá, interruption, carbon và điện là dữ liệu/giả định minh họa của lab, không phải báo giá hiện hành. "
        "Không có benchmark chất lượng cascade, throughput GPU hay đo điện phần cứng thực tế.",
        "## M1 — Hiệu quả, idle và right-sizing",
        table(["GPU", "Util %", "MFU", "MBU", "Idle h", "Max VRAM GB"],
              [(s["gpu_id"], f'{s["gpu_util_pct"]:.1f}', f'{s["mfu"]:.3f}', f'{s["mbu"]:.3f}',
                s["idle_hours"], f'{s["max_mem_gb"]:.1f}') for s in r1["summary"]]),
        "GPU-Util đo phần thời gian GPU có kernel hoạt động; kernel có thể chờ bộ nhớ hoặc dùng ít "
        "tensor cores. MFU thấp cùng util cao là tín hiệu cần profile, chưa chứng minh nguyên nhân. "
        + "; ".join(f'{s["gpu_id"]}: util {s["gpu_util_pct"]:.1f}%, MFU {s["mfu"]:.3f}' for s in r1["lies"]) + ".",
        f'Idle quan sát: ${r1["idle_waste_daily"]:.2f}/ngày, ${r1["idle_waste_daily"]*30:.2f}/30 ngày, '
        f'{r1["idle_waste_daily"]/r1["fleet_daily"]:.2%} chi phí on-demand của fleet telemetry. '
        "Đây là tỷ lệ fleet telemetry, không phải tỷ lệ tổng ngân sách M2+M3.",
        table(["GPU type", "$/h", "VRAM GB", "$/GB-h", "BW TB/s"],
              [(k, num(c["on_demand_hr"]), num(c["hbm_gb"]),
                f'{num(c["on_demand_hr"])/num(c["hbm_gb"]):.5f}', num(c["peak_bw_tbs"]))
               for k, c in cat.items()]),
        "### Extension 2 — Right-sizing theo MBU",
        "Giả định decode/embed là memory-bound; MBU thấp tự nó không xác định roofline. "
        "Kiểm tra max VRAM × 1.10, max bandwidth/0.80 và max TFLOPs/0.80. Trong nhóm đạt năng lực, "
        "decode/embed ưu tiên $/GB-h thấp rồi giá/giờ; training util-lie xét giá/giờ trong nhóm đủ năng lực.",
        table(["GPU", "Hiện tại → đề xuất", "VRAM cần GB", "$/GB-h trước → sau", "USD/30 ngày OD", "Lý do"],
              [(s["gpu_id"], s["current_gpu"] + " → " + s["proposed_gpu"],
                f'{s["required_mem_gb"]:.2f}', f'{s["current_usd_per_gb"]:.5f} → {s["proposed_usd_per_gb"]:.5f}',
                f'{s["monthly_savings"]:.2f}', s["reason"])
               for s in r1["right_sizing"] + r1["lie_sizing"]]),
        "A100 inference cần khoảng 74 GB sau headroom, nên L4/A10G 24 GB không đạt dù rẻ hơn. "
        "A10G → L4 là đề xuất cần benchmark. Chưa có bằng chứng throughput hoặc software stack tương thích.",
        "### Đối chiếu savings sau purchasing",
        table(["GPU", "Job giả định", "GPU trước → sau", "Tier", "Idle USD", "Right-size USD"],
              [(s["gpu_id"], s["assumed_job_id"], s["current_gpu"] + " → " + s["proposed_gpu"], s["tier"],
                f'{s["idle_savings"]:.2f}', f'{s["rightsize_savings"]:.2f}') for s in adjustments]),
        "Tính idle theo rate sau purchasing trước, rồi right-sizing trên giờ còn hoạt động của từng GPU. "
        "Giả định giờ budget của GPU được ánh xạ chứa idle quan sát; phải xác minh runtime/productive hours. "
        "Không cộng lại toàn bộ savings on-demand của M1; không ghi nhận idle savings cho reserved.",
        "## M2 — Unit economics và đóng góp tuần tự",
        table(["Giai đoạn", "USD/ngày", "$/1M-token", "Savings tăng thêm USD/ngày"],
              [(s["stage"], f'{s["daily_cost"]:.6f}', f'{s["per_m"]:.6f}',
                "—" if i == 0 else f'{r2["stages"][i-1]["daily_cost"]-s["daily_cost"]:.6f}')
               for i, s in enumerate(r2["stages"])]),
        f'Cùng **{r2["total_tokens"]:,} token/ngày**, inference giảm **{r2["savings_pct"]:.1f}%**. '
        "Cascade đóng góp lớn nhất do đa số request đi model nhỏ. Model/output token không đổi giữa các stage. "
        "Cần đánh giá chất lượng để xác nhận route_tier. 0.5 × 0.1 = 0.05 chỉ cho input đã cache 100%, "
        "chưa bao gồm output và phí ghi. Batch chỉ dùng cho traffic is_batch=1 chấp nhận độ trễ.",
        "### Extension 3 — Kinh tế cache",
        "CSV không có prefix ID/số reads; giả định **4 reads/write** và phí ghi bổ sung "
        "**1.25 × giá input/1M token**, tách khỏi tiền input thường. "
        "Số token ghi ước lượng = cached tokens / reads; phí ghi không hưởng batch discount. "
        "Hòa vốn = write price / [input price × (1-read_discount) × batch multiplier].",
        table(["Tier", "Write USD/1M", "Reads hòa vốn sync", "Reads hòa vốn batch"],
              [(tier, f'{pin*m2_inference_levers.WRITE_PRICE_MULTIPLIER:.4f}',
                f'{pricing.cache_break_even_reads(pin*1.25,pin):.4f}',
                f'{pricing.cache_break_even_reads(pin*1.25,pin*0.5):.4f}')
               for tier, (pin, _) in m2_inference_levers.MODEL_PRICES.items()]),
        f'Optimized cũ bỏ qua writes: ${r2["original_optimized_daily"]:.6f}/ngày '
        f'(${pricing.dollars_per_million(r2["original_optimized_daily"],r2["total_tokens"]):.6f}/1M-token). '
        f'Tính writes: ${r2["optimized_daily"]:.6f}/ngày; write fee ${r2["write_cost_daily"]:.6f}/ngày.',
        table(["Reads/write giả định", "Request bật cache", "Write USD/ngày", "USD/ngày", "$/1M-token"],
              [(s["reads"], s["enabled_requests"], f'{s["write_cost"]:.6f}', f'{s["daily_cost"]:.6f}',
                f'{s["per_m"]:.6f}') for s in r2["cache_scenarios"]]),
        "Ít reads: bỏ cache để tránh trả phí ghi nhiều hơn savings; nhiều reads: phân bổ phí ghi "
        "qua nhiều lần đọc nên đơn giá giảm. Không gọi số reads giả định là phép đo thực tế.",
        "### Extension 4 — Ngân sách reasoning",
        table(["is_reasoning", "Requests (%)", "Tokens (%)", "USD/ngày (%)", "Wh/ngày (%)"],
              [(flag, f'{g["requests"]} ({g["request_share"]:.2%})',
                f'{g["tokens"]:,} ({g["token_share"]:.2%})',
                f'{g["cost"]:.6f} ({g["cost_share"]:.2%})', f'{g["wh"]:.2f} ({g["energy_share"]:.2%})')
               for flag, g in budget["groups"].items()]),
        f'Cap 10%: đổi **{budget["changed_requests"]} request**; USD '
        f'**{budget["before_cost"]:.6f} → {budget["after_cost"]:.6f}**; Wh '
        f'**{budget["before_wh"]:.2f} → {budget["after_wh"]:.2f}**. '
        f'Savings **${budget["saved_usd"]:.6f} và {budget["saved_wh"]:.2f} Wh**.',
        "Traffic đã dưới 10% thì savings bằng 0. Giữ nguyên input/output/model; nếu vượt cap, "
        "chỉ bỏ multiplier năng lượng 80× ở request dư, giữ request output dài nhất làm proxy độ phức tạp. "
        "Đây là counterfactual, không đảm bảo giữ chất lượng. Không nhân tiền với 80×; "
        "token output reasoning đã dài hơn trong CSV. Quy tắc triển khai: chỉ reasoning khi task phức tạp "
        "hoặc confidence thấp qua đánh giá, tối đa 10% traffic; scores đó chưa có trong dữ liệu.",
        "## M3 — Purchasing và Extension 1",
        "### Kế hoạch 30 ngày với pool reserved đã có",
        table(["Job", "Tier", "On-demand USD", "Optimized USD"],
              [(r["job_id"], r["tier"], f'{r["on_demand"]:.2f}', f'{r["optimized"]:.2f}')
               for r in r3["recommendations"]]),
        f'30 ngày: ${r3["on_demand_monthly"]:.2f} → ${r3["optimized_monthly"]:.2f}; '
        f'savings {r3["savings_pct"]:.1f}%. Reserved L4 18h/ngày vẫn tính 24h capacity.',
        "### Thời gian job thực tế, mua cam kết mới",
        "Dùng days trong CSV. Chi phí reserved tính đủ kỳ 365/1095 ngày × 24h, kể cả sau khi job xong; "
        "không giả định có job tiếp theo dùng phần dư. Nếu job vượt kỳ, mua nguyên số kỳ tiếp theo. "
        "Policy so tất cả tier hợp lệ, spot chỉ cho interruptible. Giá là catalog lab.",
        table(["GPU type", "Interruption events/GPU-hour (giả định)"],
              [(k, v) for k, v in pricing.INTERRUPTION_RATES.items()]),
        table(["Job", "Days", "Tier cũ → mới", "Estimate cũ USD", "OD USD", "Mới USD", "Lý do"],
              [(r["job_id"], r["days"], r["old_tier"] + " → " + r["tier"], f'{r["old_estimate"]:.2f}',
                f'{r["on_demand"]:.2f}', f'{r["optimized"]:.2f}', r["reason"])
               for r in r3["actual_recommendations"]]),
        f'Tổng actual-days: OD **${r3["actual_on_demand"]:.2f}**, policy mới '
        f'**${r3["actual_optimized"]:.2f}**, savings **{r3["actual_savings_pct"]:.2f}%**. '
        f'Estimate policy cũ trên cùng days **${r3["actual_old_estimate"]:.2f}**, '
        f'savings **{r3["actual_old_savings_pct"]:.2f}%**. '
        "Estimate cũ tính trên cùng days nhưng bỏ nghĩa vụ cam kết và dùng interruption chung 0.05. "
        "Policy mới có thể trông đắt hơn vì đã tính nghĩa vụ thật; không phải cứ tăng savings là đúng.",
        table(["Job", "OD USD", "Spot USD", "Reserved 1yr USD", "Reserved 3yr USD"],
              [(r["job_id"], f'{r["candidate_costs"]["on_demand"]:.2f}',
                f'{r["candidate_costs"]["spot"]:.2f}' if "spot" in r["candidate_costs"] else "không hợp lệ",
                f'{r["candidate_costs"]["reserved_1yr"]:.2f}', f'{r["candidate_costs"]["reserved_3yr"]:.2f}')
               for r in r3["actual_recommendations"]]),
        "### Matrix policy: GPU × duty × interruptible × duration",
        table(["GPU", "h/ngày", "Interruptible", "Days", "Tier"],
              [(g, h, int(intr), d, pricing.recommend_tier(h, intr, gpu_type=g, job_days=d, prices=cat[g]))
               for g in ("H100", "A10G", "L4") for h in (4, 24) for intr in (False, True) for d in (30, 365, 1095)]),
        "Spot effective hours = productive GPU-hours × (1 + checkpoint overhead + interruption rate × rework). "
        "Đó là thời gian trả thêm cho checkpoint/rework, không phải thêm sản lượng. "
        "Job infer 30 ngày chuyển reserved → on-demand khi mua mới vì không đủ dài để trả cam kết cả năm.",
        "## M4 — Allocation và FOCUS-style export",
        table(["Team", "USD/ngày", "% tổng"],
              [(k, f'{v:.6f}', f'{v/r4["total_daily"]:.2%}') for k, v in sorted(r4["by_team"].items(), key=lambda x:-x[1])]),
        f'Tag coverage team/project **{r4["tag_coverage"]:.2%}**; gate **80%**; chargeback ready '
        f'**{r4["chargeback_ready"]}**. Export **{r4["export_rows"]} request**, tổng BilledCost '
        f'**${r4["total_daily"]:.6f}/ngày**, bằng M2 optimized có writes.',
        "Đây là tập cột FOCUS-style dùng học tập, chưa là chứng nhận tuân thủ toàn bộ schema FOCUS. "
        "Chuẩn hóa cùng trường chi phí/tags giúp so nhiều provider mà không cần đổi định nghĩa tiền. "
        "Request thiếu project giữ nguyên để không che giấu coverage.",
        "## Extension 5 — Carbon-aware scheduling",
        "Chỉ interruptible=1; giữ nguyên productive GPU-hours của từng job, dùng **days thực tế**. "
        "Wh = catalog watts × GPU-hours; đây là ước tính GPU rated power, chưa có PUE/CPU/network "
        "hay checkpoint overhead. So cùng lượng công việc ở mọi vùng; giá điện không cộng thêm vào "
        "giá GPU thuê, vì có thể đã nằm trong hóa đơn nhà cung cấp. Region labels là dữ liệu minh họa, "
        "không khẳng định GPU/provider tương ứng có mặt ở vùng đó.",
        table(["Job", "GPU-hours", "Wh", "us-east-1 gCO2e", "Cleanest gCO2e", "Giảm gCO2e"],
              [(r["job_id"], f'{r["gpu_hours"]:.0f}', f'{r["wh"]:.0f}', f'{r["before_g"]:.2f}',
                f'{r["after_g"]:.2f}', f'{r["saved_g"]:.2f}') for r in r3["carbon_jobs"]]),
        table(["Region", "USD/kWh", "gCO2e/kWh", "Điện USD", "Carbon gCO2e"],
              [(r["region"], r["usd_kwh"], r["g_kwh"], f'{r["energy_usd"]:.2f}', f'{r["carbon_g"]:.2f}')
               for r in r3["regions"]]),
        f'Tổng giảm **{r3["carbon_saved_g"]:,.2f} gCO2e** '
        f'(**{r3["carbon_saved_g"]/sum(j["before_g"] for j in r3["carbon_jobs"]):.2%}**). '
        f'Sạch nhất **{r3["cleanest_region"]}**; '
        f'rẻ nhất **{r3["cheapest_region"]}**; cân bằng theo tổng price/max(price) + carbon/max(carbon) '
        f'với trọng số bằng nhau **{r3["balanced_region"]}**. Chưa có dữ liệu giờ để tối ưu theo giờ.',
        "Ưu tiên batch/train có thể di chuyển; kiểm tra latency, dữ liệu lưu trú và khả dụng GPU trước "
        "khi chọn vùng. Vùng sạch hơn có thể xa người dùng; job realtime giữ gần người dùng.",
        "## Khuyến nghị ưu tiên",
        "1. Bật cascade cho tác vụ đã kiểm định chất lượng; cache qua gate hòa vốn và batch cho eval. "
        "Theo dõi $/1M-token và chất lượng trước rollout.",
        "2. Dùng spot với checkpoint cho job interruptible; không mua cam kết mới cho job ngắn. "
        "Với pool reserved hiện hữu, theo dõi toàn bộ giờ cam kết và tái sử dụng capacity bỏ trống.",
        "3. Tắt idle on-demand/spot, benchmark các đề xuất right-sizing; giữ gate tagging 80%, "
        "giới hạn reasoning và chuyển batch/train đến vùng sạch khi latency cho phép.",
    ]
    before_path = Path(ROOT) / "outputs/before/baseline.json"
    hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
              for p in sorted((Path(ROOT) / "data").glob("*.csv"))}
    if before_path.exists():
        before = json.loads(before_path.read_text(encoding="utf-8"))
        same = hashes == before["data_sha256"]
        sections += ["## Bằng chứng trước/sau",
                     f'Seed=25; SHA-256 của bốn CSV trùng baseline: **{same}**. '
                     "Baseline được lưu trước khi sửa code trong before/baseline.json và các artifact before/.",
                     table(["Chỉ số", "Code gốc", "Sau sửa", "Giải thích"],
                           [("M2 USD/ngày", f'{before["m2"]["optimized_daily"]:.2f}', f'{r2["optimized_daily"]:.6f}', "Tính thêm cache writes"),
                            ("M3 optimized 30 ngày USD", str(before["m3"]["optimized_monthly"]), f'{r3["optimized_monthly"]:.2f}', "Reserved đủ 24h + rate theo GPU"),
                            ("M5 savings %", str(before["m5"]["total_savings_pct"]), f'{(1-optimized/baseline)*100:.2f}', "Không cộng trùng và nêu savings có điều kiện"),
                            ("FOCUS rows", "50", str(r4["export_rows"]), "Đối chiếu toàn bộ hóa đơn")])]
    md += "\n\n" + "\n\n".join(sections) + "\n"
    bonus_evidence = Path(ROOT) / "outputs/bonus/validation.json"
    if bonus_evidence.exists():
        bonus = json.loads(bonus_evidence.read_text(encoding="utf-8"))
        completed = [name for name in ("exporter", "docker", "model")
                     if bonus.get(name, {}).get("status") == "completed"]
        md += ("\n## Bonus — bằng chứng chạy riêng\n\n"
               "Tracker mock và các kiểm tra đã lưu: " + ", ".join(completed) + ". "
               "Đọc [report bonus](bonus/report.md) và [validation.json](bonus/validation.json) "
               "cho thời điểm/kết quả đã ghi; chạy bonus/verify.py --docker --model để kiểm tra lại. "
               "Chi phí bonus không cộng thêm vào ngân sách M1–M5.\n")
    out = Path(ROOT) / "outputs"
    out.mkdir(exist_ok=True)
    (out / "report.md").write_text(md, encoding="utf-8")
    png = report.savings_waterfall(levers, str(out / "savings.png"), baseline)
    result = {"baseline_monthly": baseline, "optimized_monthly": optimized, "levers": levers,
              "total_savings_pct": round((1-optimized/baseline)*100, 1),
              "without_conditional_optimized": proven_optimized, "adjustments": adjustments}
    evidence = {"data_sha256": hashes, "m1": r1,
                "m2": {k:v for k,v in r2.items() if k != "priced_rows"},
                "m3": r3, "m4": r4, "m5": result}
    (out / "after.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    best = max(levers, key=levers.get)
    lie_ids = {s["gpu_id"] for s in r1["lies"]}
    lie_impact = sum(s["rightsize_savings"] for s in adjustments if s["gpu_id"] in lie_ids)
    inference_resize = sum(s["monthly_savings"] for s in r1["right_sizing"])
    writeup = f"""# Bài viết — GPU FinOps, Lab 25

Dữ liệu mô phỏng seed=25: 7 GPU type, 11 GPU × 24h, 2.400 request và 8 job.
Bảng đầy đủ ở [report.md](report.md); kết quả trước sửa ở [before/baseline.json](before/baseline.json).

## 1. Baseline vs. Optimized

| Chỉ số | Baseline | Optimized |
|---|---|---|
| Chi phí kế hoạch 30 ngày (USD) | {baseline:,.2f} | {optimized:,.2f} |
| Inference (USD/1M-token) | {r2["baseline_per_m"]:.6f} | {r2["optimized_per_m"]:.6f} |

Tổng tiết kiệm dự kiến **{baseline-optimized:,.2f} USD ({1-optimized/baseline:.2%})**;
inference giữ {r2["total_tokens"]:,} token/ngày, giảm {r2["savings_pct"]:.1f}%.
Kế hoạch giả định pool reserved hiện hữu, tính đủ 24h/ngày. API và GPU chỉ cộng khi là hai khoản chi riêng;
không quy chi phí training theo token API. Bỏ hai lever GPU có điều kiện, optimized còn
{proven_optimized:,.2f} USD ({1-proven_optimized/baseline:.2%} savings).

## 2. Phân tích từng đòn bẩy

""" + table(["Lever", "USD/30 ngày", "% tổng savings"],
            [(name, f"{value:,.2f}", f"{value/(baseline-optimized):.2%}")
             for name, value in levers.items()]) + f"""

**{best}** đóng góp nhiều nhất theo USD vì ngân sách GPU lớn và spot/reserved giảm giá thuê.
Trong inference, cascade giảm {r2["stages"][0]["daily_cost"]-r2["stages"][1]["daily_cost"]:.6f} USD/ngày,
lớn hơn cache {r2["stages"][1]["daily_cost"]-r2["stages"][2]["daily_cost"]:.6f}
và batch {r2["stages"][2]["daily_cost"]-r2["stages"][3]["daily_cost"]:.6f},
do đa số request dùng model nhỏ. Cache tính cả writes; batch chỉ cho traffic chấp nhận độ trễ.
Right-sizing kiểm tra năng lực rồi tính theo rate sau purchasing; idle chỉ giảm giờ trả tiền
của on-demand/spot. Tính idle trước resize trên giờ còn lại để tránh cộng trùng.

## 3. GPU-Util Lie và tác động tài chính

""" + "\n".join(f'- **{s["gpu_id"]}**: util {s["gpu_util_pct"]:.1f}%, MFU {s["mfu"]:.3f}.'
                   for s in r1["lies"]) + f"""

Util đo thời gian kernel hoạt động; kernel có thể chờ bộ nhớ hoặc dùng ít tensor cores.
MFU thấp là tín hiệu cần profiler, chưa chứng minh nguyên nhân. Hai GPU bị flag có tiềm năng
right-sizing **{lie_impact:,.2f} USD/30 ngày** trong ánh xạ GPU → job giả định, gồm H100 → A100
và A10G → L4. Cần benchmark throughput; không quy toàn bộ phần FLOPs chưa dùng thành tiền thu hồi.
Idle là vấn đề riêng: fleet telemetry lãng phí {r1["idle_waste_daily"]*30:.2f} USD/30 ngày on-demand,
nhưng waterfall chỉ ghi {levers["Idle shutdown (conditional)"]:.2f} USD sau purchasing.

## 4. Năm phần mở rộng: kết quả và insight

1. **Tier policy:** so interruption theo GPU type (giả định) và toàn bộ nghĩa vụ reserved 365/1095 ngày.
   Trên days thực tế: {r3["actual_on_demand"]:.2f} → {r3["actual_optimized"]:.2f} USD,
   giảm {r3["actual_savings_pct"]:.2f}%. Job inference 30 ngày chọn on-demand khi mua mới;
   không so tổng kỳ actual-days với kỳ kế hoạch 30 ngày.
2. **Right-sizing MBU:** max VRAM ×1.10; peak BW/TFLOPs tại target 80%.
   A100 cần hơn 73 GB nên không thể thay bằng GPU 24GB. Hai A10G → L4 có tiềm năng
   **{inference_resize:.2f} USD/30 ngày on-demand**; bảng sau purchasing dùng rate khác.
   Chưa benchmark throughput/tương thích software; MBU thấp chưa chứng minh memory-bound.
3. **Cache:** CSV thiếu prefix IDs/reads: giả định 4 reads/write, phí ghi thêm 1.25× input price.
   Hòa vốn sync 1.389 reads, batch 2.778. Bỏ writes: {r2["original_optimized_daily"]:.6f} USD/ngày;
   có writes: {r2["optimized_daily"]:.6f}. Case 0.5/1 read tắt cache, 4/20 reads bật.
   Insight: cache phải bù phí ghi, không mặc định tiết kiệm ở mọi traffic.
4. **Reasoning:** {budget["groups"][1]["request_share"]:.2%} request nhưng
   {budget["groups"][1]["energy_share"]:.2%} năng lượng. Cap 10% đổi {budget["changed_requests"]} request:
   {budget["before_cost"]:.6f} → {budget["after_cost"]:.6f} USD/ngày,
   {budget["before_wh"]:.2f} → {budget["after_wh"]:.2f} Wh/ngày.
   Dưới cap nên savings bằng 0. Giữ tokens/model; multiplier 80× là giả định Wh, không phải tiền.
5. **Carbon scheduling:** cùng productive GPU-hours, days thực tế, Wh = catalog watts × GPU-hours.
   Chuyển interruptible us-east-1 → {r3["cleanest_region"]} giảm **{r3["carbon_saved_g"]:,.2f} gCO2e**.
   Điện rẻ nhất ở {r3["cheapest_region"]}, vùng cân bằng {r3["balanced_region"]}.
   Vùng sạch nhất không đồng nghĩa rẻ nhất; chưa tính PUE/CPU/network/checkpoint hoặc latency.

## 5. Ba hành động đầu tiên cho NimbusAI

1. Kiểm định chất lượng cascade rồi áp dụng cache đủ hòa vốn và batch; theo dõi USD/1M-token,
   chất lượng và latency để bảo đảm giảm tiền vẫn đáp ứng sản phẩm.
2. Checkpoint + spot cho job interruptible; mua reserved mới chỉ khi tính đủ kỳ cam kết có lợi.
   Tái sử dụng pool reserved hiện hữu và ưu tiên tắt idle on-demand/spot.
3. Benchmark right-sizing, duy trì tagging trước chargeback và chuyển batch/train đến vùng sạch
   khi latency/khả dụng cho phép. Chỉ reasoning cho task phức tạp/confidence thấp, cap 10%.

Tag coverage {r4["tag_coverage"]:.2%} vượt gate 80%; FOCUS-style export đủ {r4["export_rows"]} request,
tổng {r4["total_daily"]:.6f} USD/ngày khớp M2. Giá/điện/carbon là giả định lab; chưa có benchmark GPU,
chất lượng model hay đo điện thật. Savings GPU có điều kiện được ghi riêng trong report.
"""
    (out / "writeup.md").write_text(writeup, encoding="utf-8")
    if verbose:
        print("== M5 Optimization Report ==")
        print(f"Baseline ${baseline:,.2f} -> optimized ${optimized:,.2f}; savings {(1-optimized/baseline):.2%}")
        print(f"Inference ${r2['baseline_per_m']:.6f} -> ${r2['optimized_per_m']:.6f}/1M-token")
        for name, value in levers.items():
            print(f"  {name}: ${value:,.2f}")
        print("Written: outputs/report.md + outputs/writeup.md + outputs/after.json"
              + (" + outputs/savings.png" if png else " (PNG unavailable)"))
    return result


if __name__ == "__main__":
    run()
