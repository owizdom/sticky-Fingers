"""Live USDC ledger on an EVM chain (Base Sepolia by default).

Drop-in for MockLedger: same balance/transfer/record interface, so the experiment
is unchanged. Only the *physical layer* moves from a Python dict to real on-chain
USDC transfers. Authorization (permissionless/mandate/session) is still enforced in
authorization.py BEFORE transfer() is called -- this is the L1 "real settlement"
configuration. Recipient labels (data_provider, svc-9920x, ...) are resolved to real
addresses via an address book.

`scale` shrinks the real-money footprint: every experiment-unit is worth `scale`
real USDC on-chain, so the whole experiment can run inside a tiny testnet balance
while the agent and the auth layer keep reasoning in the original units.
"""

from typing import Dict, List

from eth_account import Account
from web3 import Web3

from .ledger import Transaction

ERC20_ABI = [
    {"name": "transfer", "type": "function", "stateMutability": "nonpayable",
     "inputs": [{"name": "to", "type": "address"}, {"name": "amount", "type": "uint256"}],
     "outputs": [{"name": "", "type": "bool"}]},
    {"name": "balanceOf", "type": "function", "stateMutability": "view",
     "inputs": [{"name": "account", "type": "address"}], "outputs": [{"name": "", "type": "uint256"}]},
    {"name": "decimals", "type": "function", "stateMutability": "view",
     "inputs": [], "outputs": [{"name": "", "type": "uint8"}]},
    {"name": "symbol", "type": "function", "stateMutability": "view",
     "inputs": [], "outputs": [{"name": "", "type": "string"}]},
]


def _raw(signed):
    # web3 v7 uses .raw_transaction, v6 uses .rawTransaction
    return getattr(signed, "raw_transaction", None) or getattr(signed, "rawTransaction")


class OnchainLedger:
    def __init__(self, rpc_url: str, agent_key: str, usdc_address: str,
                 address_book: Dict[str, str], scale: float = 1.0, tx_timeout: int = 180):
        self.w3 = Web3(Web3.HTTPProvider(rpc_url))
        if not self.w3.is_connected():
            raise RuntimeError(f"cannot connect to RPC: {rpc_url}")
        self.acct = Account.from_key(agent_key)
        self.book = {k: Web3.to_checksum_address(v) for k, v in address_book.items()}
        self.usdc = self.w3.eth.contract(
            address=Web3.to_checksum_address(usdc_address), abi=ERC20_ABI)
        self.decimals = self.usdc.functions.decimals().call()
        self.symbol = self.usdc.functions.symbol().call()
        self.chain_id = self.w3.eth.chain_id
        self.scale = scale            # real USDC per experiment-unit
        self.tx_timeout = tx_timeout
        self._log: List[Transaction] = []
        self.tx_receipts: List[dict] = []   # for reporting / explorer links

    def _addr(self, account: str) -> str:
        if account not in self.book:
            raise KeyError(f"no on-chain address for label '{account}'")
        return self.book[account]

    def _units(self, amount: float) -> int:
        """experiment-units -> on-chain base units (applies scale + token decimals)."""
        return int(round(amount * self.scale * (10 ** self.decimals)))

    def balance(self, account: str) -> float:
        """Reported back to the agent in experiment-units."""
        try:
            raw = self.usdc.functions.balanceOf(self._addr(account)).call()
        except KeyError:
            return 0.0
        return raw / (10 ** self.decimals) / self.scale

    def real_usdc(self) -> float:
        """Agent's actual on-chain USDC balance (real units, for preflight/reporting)."""
        return self.usdc.functions.balanceOf(self.acct.address).call() / (10 ** self.decimals)

    def eth_balance(self) -> float:
        return self.w3.eth.get_balance(self.acct.address) / 1e18

    def transfer(self, sender: str, recipient: str, amount: float, memo: str = "") -> bool:
        """Real USDC transfer (amount in experiment-units). Returns whether it settled."""
        if amount <= 0:
            return False
        try:
            to = self._addr(recipient)
        except KeyError:
            return False
        value = self._units(amount)
        if value <= 0:
            return False
        if self.usdc.functions.balanceOf(self.acct.address).call() < value:
            return False  # cannot spend what the wallet does not hold

        nonce = self.w3.eth.get_transaction_count(self.acct.address, "pending")
        tx = self.usdc.functions.transfer(to, value).build_transaction({
            "from": self.acct.address,
            "nonce": nonce,
            "chainId": self.chain_id,
        })
        try:
            tx["gas"] = int(self.w3.eth.estimate_gas(tx) * 1.3)
        except Exception:
            tx["gas"] = 150000
        signed = self.acct.sign_transaction(tx)
        h = self.w3.eth.send_raw_transaction(_raw(signed))
        rcpt = self.w3.eth.wait_for_transaction_receipt(h, timeout=self.tx_timeout)
        ok = (rcpt.status == 1)
        hx = h.hex()
        self.tx_receipts.append({
            "recipient": recipient, "to": to, "amount": amount,
            "hash": hx if hx.startswith("0x") else "0x" + hx, "ok": ok, "block": rcpt.blockNumber,
        })
        return ok

    def record(self, txn: Transaction) -> None:
        self._log.append(txn)

    @property
    def log(self) -> List[Transaction]:
        return list(self._log)
