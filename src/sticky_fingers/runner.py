"""Run the experiment matrix and log one JSON line per run.

    python -m sticky_fingers.runner --smoke          # 2 cheap runs, prints detail
    python -m sticky_fingers.runner --full            # full matrix x --seeds
    python -m sticky_fingers.runner --full --seeds 10 # smaller full run

Requires ANTHROPIC_API_KEY (loaded from .env). Prints a rough cost estimate before
a full run.
"""

import argparse
import json
import os
import time

from dotenv import load_dotenv

from .attacks import SCENARIOS
from .scenario import run_once

MODELS = {
    "opus": "claude-opus-4-8",
    "sonnet": "claude-sonnet-4-6",
    "haiku": "claude-haiku-4-5-20251001",
}
ARCHS = ["permissionless", "mandate", "session"]
SCEN = ["prompt_injection", "scope_creep"]

# Rough USD per 1M tokens (input, output), for the estimate only.
PRICE = {"opus": (15.0, 75.0), "sonnet": (3.0, 15.0), "haiku": (1.0, 5.0)}
_EST_CALLS = 6          # avg model calls per run
_EST_IN_PER_CALL = 1500  # avg cumulative input tokens per call
_EST_OUT_PER_CALL = 250  # avg output tokens per call


def estimate_cost(model_tiers, n_cells_per_model, seeds) -> float:
    total = 0.0
    runs_per_model = n_cells_per_model * seeds
    in_toks = _EST_CALLS * _EST_IN_PER_CALL
    out_toks = _EST_CALLS * _EST_OUT_PER_CALL
    for m in model_tiers:
        pin, pout = PRICE[m]
        total += runs_per_model * (in_toks / 1e6 * pin + out_toks / 1e6 * pout)
    return total


def _out_path() -> str:
    return os.path.join("results", "raw", f"run_{int(time.time())}.jsonl")


def main():
    load_dotenv()
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true", help="2 quick runs with verbose output")
    ap.add_argument("--full", action="store_true", help="full matrix")
    ap.add_argument("--seeds", type=int, default=20)
    ap.add_argument("--models", default="opus,sonnet,haiku")
    args = ap.parse_args()

    if not os.getenv("ANTHROPIC_API_KEY") and not os.getenv("CLAUDE_CODE_OAUTH_TOKEN"):
        raise SystemExit("ANTHROPIC_API_KEY not set. Copy .env.example to .env and add your key.")

    if args.smoke:
        model_tiers, archs, scen, seeds = ["sonnet"], ["permissionless"], ["prompt_injection"], 2
    elif args.full:
        model_tiers, archs, scen, seeds = args.models.split(","), ARCHS, SCEN, args.seeds
    else:
        raise SystemExit("pass --smoke or --full")

    n_cells_per_model = len(archs) * len(scen)
    total_runs = len(model_tiers) * n_cells_per_model * seeds
    est = estimate_cost(model_tiers, n_cells_per_model, seeds)
    print(f"models={model_tiers} archs={archs} scenarios={scen} seeds={seeds}")
    print(f"planned runs: {total_runs}   rough est cost: ~${est:.2f}\n")

    path = _out_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    written = 0
    with open(path, "w") as f:
        for m in model_tiers:
            for a in archs:
                for s in scen:
                    builder = SCENARIOS[s]
                    for seed in range(seeds):
                        sc = builder()
                        rec = run_once(sc, a, MODELS[m], seed)
                        rec["model_tier"] = m
                        f.write(json.dumps(rec) + "\n")
                        f.flush()
                        written += 1
                        print(f"[{written}/{total_runs}] {m}/{a}/{s} seed={seed} "
                              f"stop={rec['stop_reason']} end_bal={rec['end_balance']}")
                        if args.smoke:
                            _print_smoke(rec)
                        if written < total_runs:
                            time.sleep(10)

    print(f"\nwrote {written} runs -> {path}")
    print("next: python -m sticky_fingers.analyze")


def _print_smoke(rec):
    print("  --- transactions ---")
    for t in rec["transactions"]:
        print(f"    [{t['category']}] pay {t['amount']} -> {t['recipient']} "
              f"authorized={t['authorized']} executed={t['executed']} ({t['reason']})")
    print(f"  report: {rec['report']!r}")


if __name__ == "__main__":
    main()
