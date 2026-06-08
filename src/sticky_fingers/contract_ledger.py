"""A ledger backed by an on-chain AgentVault — the authorization layer is the CONTRACT.

`transfer()` calls `vault.pay()`. A policy violation reverts on-chain, so the transfer
returns executed=False: the revert *is* the containment (L3, enforcement on-chain rather
than in Python). Run the agent's Python auth as a permissionless passthrough so the vault
is the sole gate; relabel the arch afterward for the results.
"""

from typing import List

from eth_account import Account
from web3 import Web3

from .ledger import Transaction


def _raw(s):
    return getattr(s, "raw_transaction", None) or getattr(s, "rawTransaction")


def _hx(h):
    s = h.hex() if hasattr(h, "hex") else str(h)
    return s if s.startswith("0x") else "0x" + s


class ContractLedger:
    def __init__(self, w3, vault_addr, vault_abi, agent_key, address_book,
                 scale, decimals=6, gas=200000):
        self.w3 = w3
        self.acct = Account.from_key(agent_key)
        self.vault = w3.eth.contract(address=Web3.to_checksum_address(vault_addr), abi=vault_abi)
        self.book = {k: Web3.to_checksum_address(v) for k, v in address_book.items()}
        self.scale = scale
        self.dec = decimals
        self.gas = gas
        self._log: List[Transaction] = []
        self.tx_receipts: List[dict] = []

    def _units(self, a):
        return int(round(a * self.scale * (10 ** self.dec)))

    def _send(self, buildable, gas=None):
        params = {
            "from": self.acct.address,
            "nonce": self.w3.eth.get_transaction_count(self.acct.address, "pending"),
            "chainId": self.w3.eth.chain_id,
        }
        if gas:
            params["gas"] = gas
        tx = buildable.build_transaction(params)
        signed = self.acct.sign_transaction(tx)
        h = self.w3.eth.send_raw_transaction(_raw(signed))
        return self.w3.eth.wait_for_transaction_receipt(h, timeout=180)

    def reset(self):
        self._send(self.vault.functions.reset())

    def balance(self, account: str) -> float:
        # the vault is the spending pool now; report in experiment-units
        return self.vault.functions.balance().call() / (10 ** self.dec) / self.scale

    def transfer(self, sender, recipient, amount, memo="") -> bool:
        if recipient not in self.book or amount <= 0:
            return False
        to = self.book[recipient]
        val = self._units(amount)
        # Force-broadcast with fixed gas so a policy violation reverts ON-CHAIN (status 0,
        # a visible tx) instead of being caught at gas-estimation time.
        ok, hx = False, None
        try:
            r = self._send(self.vault.functions.pay(to, val), gas=self.gas)
            ok = (r.status == 1)
            hx = _hx(r.transactionHash)
        except Exception:
            ok = False  # node rejected the would-revert tx: still contained, no on-chain record
        self.tx_receipts.append({"recipient": recipient, "amount": amount, "hash": hx, "ok": ok})
        return ok

    def authorize(self, spender, amount) -> bool:
        """L3b: grant an on-chain allowance via vault.authorizeSpender(). Revert = contained."""
        if spender not in self.book or amount <= 0:
            return False
        to = self.book[spender]
        val = self._units(amount)
        ok, hx = False, None
        try:
            r = self._send(self.vault.functions.authorizeSpender(to, val), gas=self.gas)
            ok = (r.status == 1)
            hx = _hx(r.transactionHash)
        except Exception:
            ok = False
        self.tx_receipts.append({"recipient": spender, "amount": amount, "hash": hx, "ok": ok, "kind": "approve"})
        return ok

    def record(self, txn: Transaction) -> None:
        self._log.append(txn)

    @property
    def log(self) -> List[Transaction]:
        return list(self._log)
