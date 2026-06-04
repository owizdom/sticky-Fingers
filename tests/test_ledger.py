from sticky_fingers.ledger import MockLedger, Transaction


def test_transfer_moves_funds():
    ledger = MockLedger({"a": 10.0})
    assert ledger.transfer("a", "b", 3.0)
    assert ledger.balance("a") == 7.0
    assert ledger.balance("b") == 3.0


def test_insufficient_funds_blocks_transfer():
    ledger = MockLedger({"a": 1.0})
    assert not ledger.transfer("a", "b", 5.0)
    assert ledger.balance("a") == 1.0
    assert ledger.balance("b") == 0.0


def test_nonpositive_amount_rejected():
    ledger = MockLedger({"a": 5.0})
    assert not ledger.transfer("a", "b", 0.0)
    assert not ledger.transfer("a", "b", -2.0)


def test_log_records_attempts():
    ledger = MockLedger({"a": 10.0})
    txn = Transaction("a", "b", 1.0, "p", "m", True, True, "ok", "legit", 0)
    ledger.record(txn)
    assert len(ledger.log) == 1
    assert ledger.log[0].recipient == "b"
