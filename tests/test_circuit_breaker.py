import time

import pytest

from orchestration.failure.circuit_breaker import CircuitBreaker, CircuitOpenError


# ---------------------------------------------------------------------------
# Initial state
# ---------------------------------------------------------------------------

def test_starts_closed() -> None:
    cb = CircuitBreaker()
    assert cb.state == "CLOSED"


def test_check_passes_when_closed() -> None:
    cb = CircuitBreaker()
    cb.check()  # should not raise


# ---------------------------------------------------------------------------
# CLOSED → OPEN transition
# ---------------------------------------------------------------------------

def test_opens_after_threshold_failures() -> None:
    cb = CircuitBreaker(threshold=3)
    for _ in range(3):
        cb.record_failure()
    assert cb.state == "OPEN"


def test_does_not_open_before_threshold() -> None:
    cb = CircuitBreaker(threshold=3)
    cb.record_failure()
    cb.record_failure()
    assert cb.state == "CLOSED"


def test_check_raises_when_open() -> None:
    cb = CircuitBreaker(threshold=1)
    cb.record_failure()
    with pytest.raises(CircuitOpenError):
        cb.check()


# ---------------------------------------------------------------------------
# OPEN → HALF_OPEN transition
# ---------------------------------------------------------------------------

def test_transitions_to_half_open_after_recovery_window(monkeypatch: pytest.MonkeyPatch) -> None:
    cb = CircuitBreaker(threshold=1, recovery_s=5.0)
    cb.record_failure()
    assert cb.state == "OPEN"

    # Advance time past recovery window
    original_monotonic = time.monotonic
    monkeypatch.setattr(time, "monotonic", lambda: original_monotonic() + 10.0)

    cb._try_transition_to_half_open()
    assert cb.state == "HALF_OPEN"


def test_does_not_transition_before_recovery_window(monkeypatch: pytest.MonkeyPatch) -> None:
    cb = CircuitBreaker(threshold=1, recovery_s=60.0)
    cb.record_failure()
    assert cb.state == "OPEN"

    # Only 1 second has passed
    original_monotonic = time.monotonic
    monkeypatch.setattr(time, "monotonic", lambda: original_monotonic() + 1.0)

    cb._try_transition_to_half_open()
    assert cb.state == "OPEN"


# ---------------------------------------------------------------------------
# HALF_OPEN → CLOSED / OPEN transitions
# ---------------------------------------------------------------------------

def test_closes_after_successful_probe(monkeypatch: pytest.MonkeyPatch) -> None:
    cb = CircuitBreaker(threshold=1, recovery_s=0.0)
    cb.record_failure()

    frozen = time.monotonic() + 1.0
    monkeypatch.setattr(time, "monotonic", lambda: frozen)
    cb._try_transition_to_half_open()
    assert cb.state == "HALF_OPEN"

    cb.record_success()
    assert cb.state == "CLOSED"


def test_reopens_after_failed_probe(monkeypatch: pytest.MonkeyPatch) -> None:
    cb = CircuitBreaker(threshold=1, recovery_s=0.0)
    cb.record_failure()

    frozen = time.monotonic() + 1.0
    monkeypatch.setattr(time, "monotonic", lambda: frozen)
    cb._try_transition_to_half_open()
    assert cb.state == "HALF_OPEN"

    cb.record_failure()
    assert cb.state == "OPEN"


# ---------------------------------------------------------------------------
# Sliding window
# ---------------------------------------------------------------------------

def test_old_failures_fall_out_of_window(monkeypatch: pytest.MonkeyPatch) -> None:
    cb = CircuitBreaker(threshold=3, window_s=10.0)
    original = time.monotonic

    # Record 2 failures at t=0
    cb.record_failure()
    cb.record_failure()

    # Advance time past the window
    monkeypatch.setattr(time, "monotonic", lambda: original() + 15.0)

    # This failure is the only one in the new window — should not open
    cb.record_failure()
    assert cb.state == "CLOSED"


def test_success_clears_failure_count_after_half_open(monkeypatch: pytest.MonkeyPatch) -> None:
    cb = CircuitBreaker(threshold=1, recovery_s=0.0)
    cb.record_failure()

    frozen = time.monotonic() + 1.0
    monkeypatch.setattr(time, "monotonic", lambda: frozen)
    cb._try_transition_to_half_open()
    cb.record_success()

    assert cb.state == "CLOSED"
    assert len(cb._failures) == 0
