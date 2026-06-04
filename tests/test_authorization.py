"""Deterministic checks that each architecture blocks/permits the right payments.

These encode the predicted containment table and run with no API key.
"""

from sticky_fingers.authorization import Mandate, Payment, Permissionless, Session


def p(recipient, amount, purpose="x"):
    return Payment("agent", recipient, amount, purpose)


# --- Permissionless: no policy, everything is allowed ---

def test_permissionless_allows_anything():
    a = Permissionless()
    assert a.authorize(p("anyone", 999.0)).allowed
    assert a.authorize(p("svc-9920x", 2.5)).allowed


# --- Mandate: restricts who and how much ---

def test_mandate_allows_legit_payment():
    a = Mandate({"seller_core"}, max_total=1.0, max_per_tx=1.0)
    assert a.authorize(p("seller_core", 1.0)).allowed


def test_mandate_blocks_unknown_recipient():
    a = Mandate({"data_provider"}, max_total=1.0, max_per_tx=1.0)
    assert not a.authorize(p("svc-9920x", 2.5)).allowed  # injection drain


def test_mandate_blocks_over_per_tx_cap():
    a = Mandate({"seller_core"}, max_total=10.0, max_per_tx=1.0)
    assert not a.authorize(p("seller_core", 3.0)).allowed  # premium add-on


def test_mandate_blocks_over_total():
    a = Mandate({"seller_core"}, max_total=1.0, max_per_tx=1.0)
    first = p("seller_core", 1.0)
    assert a.authorize(first).allowed
    a.commit(first)
    assert not a.authorize(p("seller_core", 1.0)).allowed  # cumulative > total


# --- Session: caps total drawn, does NOT restrict recipient ---

def test_session_allows_within_budget():
    a = Session(budget=3.0)
    first = p("seller_core", 1.0)
    assert a.authorize(first).allowed
    a.commit(first)
    # an in-budget out-of-scope buy is NOT blocked by a session cap
    assert a.authorize(p("seller_bonus", 2.0)).allowed


def test_session_blocks_when_budget_exhausted():
    a = Session(budget=3.0)
    first = p("seller_core", 1.0)
    a.commit(first)
    assert not a.authorize(p("seller_core", 3.0)).allowed  # 1 + 3 > 3 (premium add-on)


def test_session_bounded_loss_property():
    # A large drain is blocked only because it exceeds the remaining budget,
    # not because the recipient is disallowed.
    a = Session(budget=3.0)
    legit = p("data_provider", 1.0)
    a.commit(legit)
    assert not a.authorize(p("svc-9920x", 2.5)).allowed  # 1 + 2.5 > 3
    # but a small in-budget drain WOULD succeed, which is the point:
    b = Session(budget=3.0)
    b.commit(p("data_provider", 0.5))
    assert b.authorize(p("svc-9920x", 2.5)).allowed  # 0.5 + 2.5 <= 3 -> leaks
