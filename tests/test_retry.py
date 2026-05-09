import asyncio

import pytest

from orchestration.failure.retry import FailureType, RetryConfig, retry_with_backoff


# ---------------------------------------------------------------------------
# FailureType.classify
# ---------------------------------------------------------------------------

def test_classify_rate_limit() -> None:
    assert FailureType.classify(Exception("rate limit exceeded")) == FailureType.TRANSIENT


def test_classify_429() -> None:
    assert FailureType.classify(Exception("HTTP 429 Too Many Requests")) == FailureType.TRANSIENT


def test_classify_timeout() -> None:
    assert FailureType.classify(Exception("connection timeout")) == FailureType.TRANSIENT


def test_classify_connection_error() -> None:
    assert FailureType.classify(Exception("connection refused")) == FailureType.TRANSIENT


def test_classify_json_error() -> None:
    assert FailureType.classify(Exception("json decode error")) == FailureType.SCHEMA


def test_classify_validation_error() -> None:
    assert FailureType.classify(Exception("pydantic validation error")) == FailureType.SCHEMA


def test_classify_parse_error() -> None:
    assert FailureType.classify(Exception("failed to parse output")) == FailureType.SCHEMA


def test_classify_blurry_image() -> None:
    assert FailureType.classify(Exception("image too blurry to assess")) == FailureType.INPUT_QUALITY


def test_classify_inaudible() -> None:
    assert FailureType.classify(Exception("audio inaudible")) == FailureType.INPUT_QUALITY


def test_classify_injection() -> None:
    assert FailureType.classify(Exception("adversarial injection detected")) == FailureType.ADVERSARIAL


def test_classify_unknown_defaults_to_hard_crash() -> None:
    assert FailureType.classify(Exception("unexpected segfault")) == FailureType.HARD_CRASH


def test_classify_is_case_insensitive() -> None:
    assert FailureType.classify(Exception("Rate Limit Exceeded")) == FailureType.TRANSIENT


# ---------------------------------------------------------------------------
# RetryConfig
# ---------------------------------------------------------------------------

def test_transient_is_retryable() -> None:
    assert RetryConfig.is_retryable(FailureType.TRANSIENT)


def test_schema_is_retryable() -> None:
    assert RetryConfig.is_retryable(FailureType.SCHEMA)


def test_input_quality_not_retryable() -> None:
    assert not RetryConfig.is_retryable(FailureType.INPUT_QUALITY)


def test_adversarial_not_retryable() -> None:
    assert not RetryConfig.is_retryable(FailureType.ADVERSARIAL)


def test_hard_crash_not_retryable() -> None:
    assert not RetryConfig.is_retryable(FailureType.HARD_CRASH)


def test_transient_max_attempts() -> None:
    assert RetryConfig.max_attempts(FailureType.TRANSIENT) == 3


def test_schema_max_attempts() -> None:
    assert RetryConfig.max_attempts(FailureType.SCHEMA) == 2


def test_backoff_increases_exponentially() -> None:
    b1 = RetryConfig.backoff_s(1)
    b2 = RetryConfig.backoff_s(2)
    b3 = RetryConfig.backoff_s(3)
    assert b1 < b2 < b3


def test_backoff_capped_at_30() -> None:
    assert RetryConfig.backoff_s(100) == 30.0


def test_backoff_attempt_1() -> None:
    assert RetryConfig.backoff_s(1) == 2.0


def test_backoff_attempt_2() -> None:
    assert RetryConfig.backoff_s(2) == 4.0


# ---------------------------------------------------------------------------
# retry_with_backoff — behaviour
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_succeeds_immediately_without_retry() -> None:
    calls = []

    async def fn() -> str:
        calls.append(1)
        return "ok"

    result = await retry_with_backoff(fn)
    assert result == "ok"
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_retries_transient_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    async def instant_sleep(_: float) -> None:
        pass

    monkeypatch.setattr("orchestration.failure.retry.asyncio.sleep", instant_sleep)
    calls = []

    async def fn() -> str:
        calls.append(1)
        if len(calls) < 3:
            raise Exception("rate limit exceeded")
        return "ok"

    result = await retry_with_backoff(fn, failure_types=(FailureType.TRANSIENT,))
    assert result == "ok"
    assert len(calls) == 3


@pytest.mark.asyncio
async def test_raises_after_max_attempts(monkeypatch: pytest.MonkeyPatch) -> None:
    async def instant_sleep(_: float) -> None:
        pass

    monkeypatch.setattr("orchestration.failure.retry.asyncio.sleep", instant_sleep)

    async def fn() -> str:
        raise Exception("rate limit exceeded")

    with pytest.raises(Exception, match="rate limit"):
        await retry_with_backoff(fn, failure_types=(FailureType.TRANSIENT,))


@pytest.mark.asyncio
async def test_does_not_retry_non_retryable_failure() -> None:
    calls = []

    async def fn() -> str:
        calls.append(1)
        raise Exception("unexpected segfault")

    with pytest.raises(Exception, match="segfault"):
        await retry_with_backoff(fn, failure_types=(FailureType.TRANSIENT,))

    assert len(calls) == 1
