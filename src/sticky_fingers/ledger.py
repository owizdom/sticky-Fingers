"""A mock stablecoin ledger.

The ledger does pure accounting: it moves balances and keeps an immutable log of
every payment *attempt* (authorized or not, executed or not). It deliberately
knows nothing about authorization policy -- that lives in `authorization.py`.
Using a mock instead of live x402/testnet is intentional: an agent cannot tell a
real USDC transfer from a number in a JSON field, so for studying behavior the
mock is equivalent and avoids cost, latency, and flakiness.
"""

from dataclasses import dataclass
from typing import Dict, List


@dataclass
class Transaction:
    """A single payment attempt, recorded whether or not it settled."""

    sender: str
    recipient: str
    amount: float
    purpose: str
    memo: str
    authorized: bool      # did the authorization layer allow it?
    executed: bool        # did money actually move?
    reason: str           # the authorization layer's stated reason
    category: str         # "legit" | "attack" | "other" (set by the scenario)
    step: int             # order within the run


class MockLedger:
    def __init__(self, balances: Dict[str, float]):
        self._balances: Dict[str, float] = dict(balances)
        self._log: List[Transaction] = []

    def balance(self, account: str) -> float:
        return self._balances.get(account, 0.0)

    def transfer(self, sender: str, recipient: str, amount: float, memo: str = "") -> bool:
        """Move funds if physically possible. Returns whether it executed.

        This is the physical layer only (you cannot spend money you do not hold).
        Policy enforcement happens before this is ever called.
        """
        if amount <= 0:
            return False
        if self._balances.get(sender, 0.0) + 1e-9 < amount:
            return False
        self._balances[sender] = self._balances.get(sender, 0.0) - amount
        self._balances[recipient] = self._balances.get(recipient, 0.0) + amount
        return True

    def record(self, txn: Transaction) -> None:
        self._log.append(txn)

    @property
    def log(self) -> List[Transaction]:
        return list(self._log)
