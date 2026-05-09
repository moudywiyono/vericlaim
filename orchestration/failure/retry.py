from __future__ import annotations

import asyncio
import logging
from enum import Enum
from typing import Any, Callable, Coroutine, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class FailureType(str, Enum):
    TRANSIENT = "transient"       # 429, timeout, network error — retry
    SCHEMA = "schema"             # bad structured output — retry with error in context
    INPUT_QUALITY = "input_quality"  # blurry image, inaudible audio — no retry
    ADVERSARIAL = "adversarial"   # detected injection or OOD — escalate
    HARD_CRASH = "hard_crash"     # unexpected exception — no retry

    @classmethod
    def classify(cls, exc: Exception) -> "FailureType":
        msg = str(exc).lower()
        if "rate limit" in msg or "429" in msg or "timeout" in msg or "connection" in msg:
            return cls.TRANSIENT
        if "json" in msg or "validation" in msg or "schema" in msg or "parse" in msg:
            return cls.SCHEMA
        if "blurry" in msg or "inaudible" in msg or "quality" in msg:
            return cls.INPUT_QUALITY
        if "injection" in msg or "adversarial" in msg:
            return cls.ADVERSARIAL
        return cls.HARD_CRASH


class RetryConfig:
    _max_attempts: dict[FailureType, int] = {
        FailureType.TRANSIENT: 3,
        FailureType.SCHEMA: 2,
        FailureType.INPUT_QUALITY: 1,
        FailureType.ADVERSARIAL: 1,
        FailureType.HARD_CRASH: 1,
    }

    @classmethod
    def max_attempts(cls, failure_type: FailureType) -> int:
        return cls._max_attempts[failure_type]

    @classmethod
    def is_retryable(cls, failure_type: FailureType) -> bool:
        return failure_type in (FailureType.TRANSIENT, FailureType.SCHEMA)

    @classmethod
    def backoff_s(cls, attempt: int) -> float:
        """Exponential backoff capped at 30s."""
        return min(2 ** attempt, 30.0)


async def retry_with_backoff(
    fn: Callable[..., Coroutine[Any, Any, T]],
    *args: Any,
    failure_types: tuple[FailureType, ...] = (FailureType.TRANSIENT,),
    **kwargs: Any,
) -> T:
    """
    Run an async callable with retry logic for the specified failure types.
    Raises the final exception if all attempts are exhausted.
    """
    max_att = max(RetryConfig.max_attempts(ft) for ft in failure_types)
    last_exc: Exception | None = None

    for attempt in range(1, max_att + 1):
        try:
            return await fn(*args, **kwargs)
        except Exception as e:
            ft = FailureType.classify(e)
            if ft not in failure_types or attempt == max_att:
                raise
            last_exc = e
            backoff = RetryConfig.backoff_s(attempt)
            logger.warning("Attempt %d/%d failed (%s), retrying in %.1fs: %s",
                           attempt, max_att, ft.value, backoff, e)
            await asyncio.sleep(backoff)

    raise last_exc or RuntimeError("retry_with_backoff exhausted with no exception")
