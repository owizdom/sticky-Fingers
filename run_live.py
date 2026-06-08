"""Drive Sticky Fingers against a REAL on-chain USDC rail (Base Sepolia, L1).

Preflight (default): connect, show the agent's ETH/USDC balances + scaled footprint,
print the plan. Add --go to actually run.

    ./venv/bin/python run_live.py            # preflight only (no money moves)
    ./venv/bin/python run_live.py --go       # run the focused live matrix

Focuses on the only cells where money actually moves under attack (haiku x injection
across all three arms), plus opus/sonnet permissionless controls. Auth is still
enforced in Python before each transfer (L1: real settlement, simulated enforcement).
LIVE_SCALE shrinks the real footprint (1 experiment-unit = LIVE_SCALE real USDC).
"""

import json
import os
import sys
import time

from dotenv import load_dotenv

HERE = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(HERE, ".env"))

from sticky_fingers.attacks import SCENARIOS
from sticky_fingers.onchain_ledger import OnchainLedger
from sticky_fingers.runner import MODELS
from sticky_fingers.scenario import run_once

RPC = os.getenv("RPC_URL", os.getenv("BASE_SEPOLIA_RPC", "https://sepolia.base.org"))
USDC = os.getenv("USDC_ADDRESS", "0x036CbD53842c5426634e7929541eC2318f3dCF7e")  # default: Base Sepolia USDC
SCALE = float(os.getenv("LIVE_SCALE", "0.002"))   # real USDC per experiment-unit
EXPLORER = os.getenv("EXPLORER_URL", "https://sepolia.basescan.org")

# (scenario, arch, model, n_seeds)
PLAN = [
    ("prompt_injection", "permissionless", "haiku", 2),
    ("prompt_injection", "mandate", "haiku", 2),
    ("prompt_injection", "session", "haiku", 2),
    ("prompt_injection", "permissionless", "opus", 1),    # control: refuses, ~0 moves
    ("prompt_injection", "permissionless", "sonnet", 1),  # control: refuses, ~0 moves
]


def _worst_case_units():
    # worst case: every allowed attack settles (perm/session haiku = 0.5 legit + 2.5 attack)
    u = 0.0
    for scen, arch, model, n in PLAN:
        per = 3.0 if (arch in ("permissionless", "session") and model == "haiku") else 0.5
        u += per * n
    return u


def main():
    book = json.load(open(os.path.join(HERE, "live_addresses.json")))
    key = os.environ["AGENT_PRIVATE_KEY"]
    ledger = OnchainLedger(RPC, key, USDC, book, scale=SCALE)

    eth = ledger.eth_balance()
    real = ledger.real_usdc()
    units = _worst_case_units()
    real_needed = units * SCALE
    total_runs = sum(n for *_, n in PLAN)

    print(f"chain id {ledger.chain_id}   token {ledger.symbol} ({ledger.decimals} dec)   rpc {RPC}")
    print(f"agent {ledger.acct.address}")
    print(f"   ETH         {eth:.5f}")
    print(f"   {ledger.symbol} (real)  {real:.4f}")
    print(f"   scale       1 unit = {SCALE} {ledger.symbol}  (agent sees ~{ledger.balance('agent'):.1f} units)")
    print(f"plan: {total_runs} runs, moves up to ~{real_needed:.4f} {ledger.symbol} real")
    print(f"watch: {EXPLORER}/address/{ledger.acct.address}")
    for scen, arch, model, n in PLAN:
        print(f"   {model}/{arch}/{scen} x{n}")

    if "--go" not in sys.argv:
        print(f"\npreflight only. need ~{real_needed:.4f} {ledger.symbol}; have {real:.4f}. "
              f"fund + re-run with --go.")
        return

    if eth <= 0:
        raise SystemExit("agent has 0 ETH for gas. fund it first.")
    if real < real_needed:
        raise SystemExit(f"agent has {real:.4f} {ledger.symbol}, need ~{real_needed:.4f}. "
                         f"fund more, or lower LIVE_SCALE.")

    out = os.path.join(HERE, "results", "raw", f"live_{int(time.time())}.jsonl")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    written = 0
    with open(out, "w") as f:
        for scen, arch, model, n in PLAN:
            builder = SCENARIOS[scen]
            for seed in range(n):
                sc = builder()
                rec = run_once(sc, arch, MODELS[model], seed, ledger=ledger)
                rec["model_tier"] = model
                rec["scale"] = SCALE
                f.write(json.dumps(rec) + "\n")
                f.flush()
                written += 1
                moved = [(t["category"], t["amount"]) for t in rec["transactions"] if t["executed"]]
                print(f"[{written}/{total_runs}] {model}/{arch}/{scen} seed={seed} "
                      f"stop={rec['stop_reason']} moved={moved}")
                time.sleep(3)

    print(f"\nwrote {written} runs -> {out}")
    print("on-chain transfers (experiment-units ~ real USDC):")
    for r in ledger.tx_receipts:
        print(f"   {r['amount']:.2f}u ~{r['amount']*SCALE:.4f}{ledger.symbol} -> {r['recipient']:13} "
              f"{'OK' if r['ok'] else 'REVERT'}  {EXPLORER}/tx/{r['hash']}")
    print(f"\nagent balance now: {ledger.real_usdc():.4f} {ledger.symbol} real "
          f"(~{ledger.balance('agent'):.1f} units)")


if __name__ == "__main__":
    main()
