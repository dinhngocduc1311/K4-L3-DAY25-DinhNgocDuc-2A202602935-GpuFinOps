"""Measure CPU generation, with warm-up and repeated runs; no cloud/API key."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
import math
import os
import platform
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
# Cache model artifacts inside the workspace; never commit weights.
os.environ.setdefault("HF_HOME", str(ROOT / ".cache" / "huggingface"))
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")


def unit_economics(new_tokens: int, seconds: float, rate_hr: float) -> dict:
    """Output-only token economics; loading, warm-up and idle capacity excluded."""
    if new_tokens <= 0 or seconds <= 0 or rate_hr < 0 or not all(
            math.isfinite(x) for x in (seconds, rate_hr)):
        raise ValueError("Need positive generated tokens/time and a finite nonnegative CPU rate")
    cost = seconds / 3600 * rate_hr
    return {"tokens_per_second": new_tokens / seconds, "estimated_cost_usd": cost,
            "usd_per_million_output_tokens": cost / new_tokens * 1e6}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=os.environ.get("LAB_MODEL", "sshleifer/tiny-gpt2"))
    parser.add_argument("--revision", default="main", help="Hub model revision or commit hash")
    parser.add_argument("--cpu-rate-hr", type=float, default=os.environ.get("LAB_CPU_RATE_HR", "0.10"))
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--max-new-tokens", type=int, default=64)
    parser.add_argument("--threads", type=int, default=1)
    parser.add_argument("--offline", action="store_true", help="Load only already-cached model files")
    parser.add_argument("--strict", action="store_true", help="Exit 1 on missing deps/model or inference failure")
    parser.add_argument("--output", type=Path, default=ROOT / "outputs/bonus/local_benchmark.json")
    args = parser.parse_args(argv)
    if args.runs < 1 or args.max_new_tokens < 1 or args.threads < 1:
        parser.error("runs, max-new-tokens and threads must be positive")
    if args.cpu_rate_hr < 0 or not math.isfinite(args.cpu_rate_hr):
        parser.error("cpu-rate-hr must be finite and nonnegative")

    def save(result):
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Written: {args.output}")

    try:
        import torch
        import transformers
        from transformers import AutoModelForCausalLM, AutoTokenizer
        from huggingface_hub import try_to_load_from_cache
        torch.set_num_threads(args.threads)
        torch.manual_seed(25)
        loading_start = time.perf_counter()
        tok = AutoTokenizer.from_pretrained(args.model, revision=args.revision,
                                          local_files_only=args.offline, trust_remote_code=False)
        model = AutoModelForCausalLM.from_pretrained(
            args.model, revision=args.revision, local_files_only=args.offline, trust_remote_code=False).to("cpu").eval()
        load_seconds = time.perf_counter() - loading_start
        prompt = "GPU FinOps means measuring cost in dollars per million tokens, because"
        ids = tok(prompt, return_tensors="pt")
        kwargs = {"max_new_tokens": args.max_new_tokens, "do_sample": False,
                  "pad_token_id": tok.pad_token_id if tok.pad_token_id is not None else tok.eos_token_id}
        measurements = []
        with torch.inference_mode():
            model.generate(**ids, **kwargs)  # One warm-up; excluded from timed generation.
            for _ in range(args.runs):
                start = time.perf_counter()
                generated = model.generate(**ids, **kwargs)
                seconds = time.perf_counter() - start
                count = int(generated.shape[-1] - ids["input_ids"].shape[-1])
                measurements.append({"new_tokens": count, "seconds": seconds,
                                     **unit_economics(count, seconds, args.cpu_rate_hr)})
        total_tokens = sum(r["new_tokens"] for r in measurements)
        total_seconds = sum(r["seconds"] for r in measurements)
        from missions.m2_inference_levers import MODEL_PRICES, run
        simulation = run(False)
        revision = getattr(model.config, "_commit_hash", None)
        if revision is None and not Path(args.model).is_dir():
            cached = try_to_load_from_cache(args.model, "config.json", revision=args.revision)
            if isinstance(cached, str) and Path(cached).parent.parent.name == "snapshots":
                revision = Path(cached).parent.name
        result = {"status": "completed", "model": args.model, "device": "cpu", "seed": 25,
                  "measured_at_utc": datetime.now(timezone.utc).isoformat(),
                  "requested_revision": args.revision, "model_revision": revision,
                  "python": platform.python_version(), "torch": torch.__version__,
                  "transformers": transformers.__version__, "threads": args.threads,
                  "cpu_rate_usd_hr_assumption": args.cpu_rate_hr, "load_seconds": load_seconds,
                  "warmup_runs": 1, "input_tokens_per_request": int(ids["input_ids"].shape[-1]),
                  "runs": measurements, "total_output_tokens": total_tokens,
                  "total_generation_seconds": total_seconds,
                  "median_tokens_per_second": statistics.median(r["tokens_per_second"] for r in measurements),
                  **unit_economics(total_tokens, total_seconds, args.cpu_rate_hr),
                  "simulation_small_output_usd_per_m": MODEL_PRICES["small"][1],
                  "simulation_m2_input_plus_output_usd_per_m": simulation["optimized_per_m"],
                  "scope": "Measured output-token CPU generation; rental rate assumed; excludes load/warmup/idle. "
                           "Tiny model quality differs from production models; M2 counts both input and output."}
        save(result)
        print(f"CPU throughput: {result['tokens_per_second']:.2f} output tok/s "
              f"(median {result['median_tokens_per_second']:.2f}, {args.runs} runs)")
        print(f"Estimated output economics: $"+f"{result['usd_per_million_output_tokens']:.6f}/1M output tokens")
        print(f"Lab small-model output price: $"+f"{MODEL_PRICES['small'][1]:.2f}/1M; "
              f"M2 input+output: $"+f"{simulation['optimized_per_m']:.6f}/1M (different denominator/quality)")
        return 0
    except (ImportError, OSError, RuntimeError, ValueError) as exc:
        save({"status": "skipped", "model": args.model, "reason": str(exc), "offline": args.offline})
        print(f"[skip] CPU benchmark unavailable: {exc}")
        print("Install: python -m pip install -r bonus/local_model/requirements.txt")
        return 1 if args.strict else 0


if __name__ == "__main__":
    sys.exit(main())
