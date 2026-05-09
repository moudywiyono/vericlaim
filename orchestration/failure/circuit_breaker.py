from __future__ import annotations

import logging
import time
from collections import deque

logger = logging.getLogger(__name__)


class CircuitOpenError(Exception):
    """Raised when a circuit breaker is in the OPEN state."""


class CircuitBreaker:
    """
    Per-dependency circuit breaker.

    States: CLOSED (normal) → OPEN (failing fast) → HALF_OPEN (probing).
    Keyed by a string identifier (node name + external dependency).
    """

    def __init__(self, threshold: int = 5, window_s: float = 60.0, recovery_s: float = 30.0) -> None:
        self.threshold = threshold          # failures within window before opening
        self.window_s = window_s            # sliding window in seconds
        self.recovery_s = recovery_s        # time in OPEN before allowing a probe
        self._failures: deque[float] = deque()
        self._open_since: float | None = None
        self._state: str = "CLOSED"

    @property
    def state(self) -> str:
        return self._state

    def _prune_window(self) -> None:
        cutoff = time.monotonic() - self.window_s
        while self._failures and self._failures[0] < cutoff:
            self._failures.popleft()

    def _try_transition_to_half_open(self) -> None:
        if self._open_since is not None:
            if time.monotonic() - self._open_since >= self.recovery_s:
                self._state = "HALF_OPEN"
                logger.info("Circuit HALF_OPEN — probing")

    def record_success(self) -> None:
        if self._state == "HALF_OPEN":
            self._state = "CLOSED"
            self._failures.clear()
            self._open_since = None
            logger.info("Circuit CLOSED after successful probe")

    def record_failure(self) -> None:
        now = time.monotonic()
        self._failures.append(now)
        self._prune_window()

        if self._state == "HALF_OPEN":
            self._state = "OPEN"
            self._open_since = now
            logger.warning("Circuit re-OPEN after failed probe")
        elif len(self._failures) >= self.threshold:
            self._state = "OPEN"
            self._open_since = now
            logger.warning("Circuit OPEN after %d failures in %.0fs", self.threshold, self.window_s)

    def check(self) -> None:
        """Raise CircuitOpenError if the circuit should not let traffic through."""
        if self._state == "CLOSED":
            return
        if self._state == "OPEN":
            self._try_transition_to_half_open()
        if self._state == "OPEN":
            raise CircuitOpenError(f"Circuit is OPEN (tripped {self._open_since:.0f}s ago)")
        # HALF_OPEN: allow one probe through (caller must record success/failure)
