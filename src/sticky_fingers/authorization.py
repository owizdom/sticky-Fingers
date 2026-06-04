"""The independent variable: three payment-authorization architectures.

All three implement one interface -- `authorize(payment) -> Decision` -- which is
the single chokepoint every payment routes through. `commit(payment)` is called
only after a payment actually executes, so internal counters never drift when a
transfer is authorized but fails for lack of funds.

  * Permissionless (x402-like): no policy. Payment is its own authorization.
  * Mandate (AP2-like): restricts WHO and HOW MUCH per the issued mandate.
  * Session (MPP-like): restricts the TOTAL drawn against a pre-authorized budget.

Swapping the architecture is the only thing that changes between arms; the model,
prompt, task, tools, and attack are held constant.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Set

_EPS = 1e-9


@dataclass
class Payment:
    sender: str
    recipient: str
    amount: float
    purpose: str = ""
    memo: str = ""


@dataclass
class Decision:
    allowed: bool
    reason: str


class AuthorizationLayer(ABC):
    name: str = "base"

    @abstractmethod
    def authorize(self, payment: Payment) -> Decision:
        ...

    def commit(self, payment: Payment) -> None:
        """Update internal state after a payment has actually executed."""
        return None


class Permissionless(AuthorizationLayer):
    """x402-like: anonymous, stateless, no scope. Payment is authentication."""

    name = "permissionless"

    def authorize(self, payment: Payment) -> Decision:
        return Decision(True, "permissionless: payment is its own authorization")


class Mandate(AuthorizationLayer):
    """AP2-like: a signed mandate bounding recipients, per-tx size, and total."""

    name = "mandate"

    def __init__(self, allowed_recipients: Set[str], max_total: float, max_per_tx: float):
        self.allowed_recipients = set(allowed_recipients)
        self.max_total = max_total
        self.max_per_tx = max_per_tx
        self.spent = 0.0

    def authorize(self, payment: Payment) -> Decision:
        if payment.recipient not in self.allowed_recipients:
            return Decision(False, f"recipient '{payment.recipient}' not authorized by mandate")
        if payment.amount > self.max_per_tx + _EPS:
            return Decision(False, f"amount {payment.amount} exceeds per-tx cap {self.max_per_tx}")
        if self.spent + payment.amount > self.max_total + _EPS:
            return Decision(False, f"would exceed mandate total {self.max_total} (spent {self.spent})")
        return Decision(True, "within mandate")

    def commit(self, payment: Payment) -> None:
        self.spent += payment.amount


class Session(AuthorizationLayer):
    """MPP-like: one pre-authorized budget, drawn down per payment. Caps total
    loss but does not restrict who gets paid."""

    name = "session"

    def __init__(self, budget: float):
        self.budget = budget
        self.drawn = 0.0

    def authorize(self, payment: Payment) -> Decision:
        if self.drawn + payment.amount > self.budget + _EPS:
            return Decision(False, f"exceeds session budget {self.budget} (drawn {self.drawn})")
        return Decision(True, "within session budget")

    def commit(self, payment: Payment) -> None:
        self.drawn += payment.amount


def make_layer(arch: str, **kwargs) -> AuthorizationLayer:
    if arch == "permissionless":
        return Permissionless()
    if arch == "mandate":
        return Mandate(kwargs["allowed_recipients"], kwargs["max_total"], kwargs["max_per_tx"])
    if arch == "session":
        return Session(kwargs["budget"])
    raise ValueError(f"unknown architecture: {arch}")
