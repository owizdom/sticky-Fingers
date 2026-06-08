"""L3a: run the agent against the on-chain AgentVaults (enforcement is the CONTRACT).

    ./venv/bin/python run_l3.py          # preflight (vault addrs + balances)
    ./venv/bin/python run_l3.py --go     # run

The agent's Python auth is permissionless passthrough; the vault for each arm is the
real gate. A mandate/session revert = contained (executed=False), on-chain.
"""

import json
import os
import sys
import time

from dotenv import load_dotenv

HERE = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(HERE, ".env"))

from web3 import Web3

from sticky_fingers.attacks import SCENARIOS
from sticky_fingers.contract_ledger import ContractLedger
from sticky_fingers.runner import MODELS
from sticky_fingers.scenario import run_once

RPC = os.getenv("RPC_URL", "https://mainnet.base.org")
EXPLORER = os.getenv("EXPLORER_URL", "https://basescan.org")
SCALE = float(os.getenv("LIVE_SCALE", "0.002"))

w3 = Web3(Web3.HTTPProvider(RPC))
vaults = json.load(open(os.path.join(HERE, "live_vaults.json")))
book = json.load(open(os.path.join(HERE, "live_addresses.json")))
art = json.load(open(os.path.join(HERE, "contracts/out/AgentVault.sol/AgentVault.json")))
abi = art["abi"]
key = os.environ["AGENT_PRIVATE_KEY"]

# (arm, model, n_seeds) — haiku across all arms + opus/sonnet permissionless controls
PLAN = [
    ("permissionless", "haiku", 2),
    ("mandate", "haiku", 2),
    ("session", "haiku", 2),
    ("permissionless", "opus", 1),
    ("permissionless", "sonnet", 1),
]


def main():
    total = sum(n for *_, n in PLAN)
    print(f"L3a — on-chain enforcement, chain {w3.eth.chain_id}")
    usdc_abi = [{"name": "balanceOf", "type": "function", "stateMutability": "view",
                 "inputs": [{"name": "x", "type": "address"}], "outputs": [{"name": "", "type": "uint256"}]}]
    for arm, addr in vaults.items():
        v = w3.eth.contract(address=Web3.to_checksum_address(addr), abi=abi)
        print(f"  vault {arm:14} {addr}  USDC {v.functions.balance().call()/1e6}")

    if "--go" not in sys.argv:
        print("preflight only; pass --go to run")
        return

    out = os.path.join(HERE, "results", "raw", f"l3a_{int(time.time())}.jsonl")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    receipts = []
    written = 0
    with open(out, "w") as f:
        for arm, model, n in PLAN:
            led = ContractLedger(w3, vaults[arm], abi, key, book, SCALE)
            for seed in range(n):
                led.reset()  # fresh on-chain policy state per run
                # Python auth = permissionless passthrough; the VAULT enforces.
                rec = run_once(SCENARIOS["prompt_injection"](), "permissionless",
                               MODELS[model], seed, ledger=led)
                rec["arch"] = arm           # relabel to the real enforcement arm
                rec["model_tier"] = model
                rec["scale"] = SCALE
                rec["layer"] = "L3a-onchain"
                f.write(json.dumps(rec) + "\n")
                f.flush()
                written += 1
                moved = [(t["category"], t["amount"]) for t in rec["transactions"] if t["executed"]]
                print(f"[{written}/{total}] {model}/{arm} seed={seed} stop={rec['stop_reason']} moved={moved}")
                time.sleep(2)
            receipts.extend([dict(r, arm=arm) for r in led.tx_receipts])

    print(f"\nwrote {written} -> {out}")
    print("on-chain pay() calls (revert/❌ = contained by the contract):")
    for r in receipts:
        mark = "OK" if r["ok"] else "REVERT"
        link = f"{EXPLORER}/tx/{r['hash']}" if r["hash"] else "(not broadcast)"
        print(f"   {r['arm']:14} {r['amount']:.2f}u -> {r['recipient']:13} {mark:7} {link}")


if __name__ == "__main__":
    main()
