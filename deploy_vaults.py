"""Deploy the three AgentVault enforcement contracts to Base mainnet, configure them
on-chain (mandate allowlist+caps, session budget), and fund each from the agent.

    ./venv/bin/python deploy_vaults.py

Writes live_vaults.json (gitignored). Owner == operator == agent key, so the agent
key can `withdraw` to recover funds at any time.
"""

import json
import os

from dotenv import load_dotenv

HERE = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(HERE, ".env"))

from eth_account import Account
from web3 import Web3

RPC = os.getenv("RPC_URL", "https://mainnet.base.org")
USDC = os.getenv("USDC_ADDRESS", "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913")
EXPLORER = os.getenv("EXPLORER_URL", "https://basescan.org")
SCALE = float(os.getenv("LIVE_SCALE", "0.002"))
DEC = 6


def units(u):
    return int(round(u * SCALE * (10 ** DEC)))


w3 = Web3(Web3.HTTPProvider(RPC))
acct = Account.from_key(os.environ["AGENT_PRIVATE_KEY"])
book = json.load(open(os.path.join(HERE, "live_addresses.json")))
art = json.load(open(os.path.join(HERE, "contracts/out/AgentVault.sol/AgentVault.json")))
abi, bytecode = art["abi"], art["bytecode"]["object"]

USDC_ABI = [
    {"name": "transfer", "type": "function", "stateMutability": "nonpayable",
     "inputs": [{"name": "to", "type": "address"}, {"name": "a", "type": "uint256"}],
     "outputs": [{"name": "", "type": "bool"}]},
    {"name": "balanceOf", "type": "function", "stateMutability": "view",
     "inputs": [{"name": "x", "type": "address"}], "outputs": [{"name": "", "type": "uint256"}]},
]
usdc = w3.eth.contract(address=Web3.to_checksum_address(USDC), abi=USDC_ABI)
Vault = w3.eth.contract(abi=abi, bytecode=bytecode)


def _raw(s):
    return getattr(s, "raw_transaction", None) or getattr(s, "rawTransaction")


def exec_tx(buildable):
    tx = buildable.build_transaction({
        "from": acct.address,
        "nonce": w3.eth.get_transaction_count(acct.address, "pending"),
        "chainId": w3.eth.chain_id,
    })
    signed = acct.sign_transaction(tx)
    h = w3.eth.send_raw_transaction(_raw(signed))
    return w3.eth.wait_for_transaction_receipt(h, timeout=180)


MODES = {"permissionless": 0, "mandate": 1, "session": 2}
vaults = {}
print(f"deploying from agent {acct.address}  (ETH {w3.eth.get_balance(acct.address)/1e18:.6f})")
for name, mode in MODES.items():
    r = exec_tx(Vault.constructor(Web3.to_checksum_address(USDC), acct.address, mode))
    vaults[name] = r.contractAddress
    print(f"  deployed {name:14} -> {r.contractAddress}")

# configure on-chain policy (scaled units)
mv = w3.eth.contract(address=vaults["mandate"], abi=abi)
dp = Web3.to_checksum_address(book["data_provider"])
exec_tx(mv.functions.setMandate([dp], units(1.0), units(1.0)))
print(f"  mandate: allow data_provider, perTx/total = {units(1.0)} base ({units(1.0)/1e6} USDC)")
sv = w3.eth.contract(address=vaults["session"], abi=abi)
exec_tx(sv.functions.setSession(units(3.0)))
print(f"  session: budget = {units(3.0)} base ({units(3.0)/1e6} USDC)")

# fund each vault (10 units = 0.02 USDC)
for name, addr in vaults.items():
    exec_tx(usdc.functions.transfer(Web3.to_checksum_address(addr), units(10.0)))
    print(f"  funded {name:14} {units(10.0)/1e6} USDC")

json.dump(vaults, open(os.path.join(HERE, "live_vaults.json"), "w"), indent=2)
print("\nsaved live_vaults.json")
for name, addr in vaults.items():
    bal = usdc.functions.balanceOf(Web3.to_checksum_address(addr)).call() / 1e6
    print(f"  {name:14} {addr}  USDC {bal}  {EXPLORER}/address/{addr}")
print(f"agent USDC left: {usdc.functions.balanceOf(acct.address).call()/1e6}")
