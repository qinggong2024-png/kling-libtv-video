from __future__ import annotations

from typing import Any

from libtv_agent.domain.models import GenerationAttempt


def record_provider_error(
    attempt: GenerationAttempt,
    *,
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
    retryable: bool | None = None,
) -> None:
    """Persist the safe, user-readable portion of a provider failure."""

    attempt.last_error_code = code[:80]
    attempt.error_message = message[:4000]
    attempt.provider_error_details_json = dict(details or {})
    attempt.provider_error_retryable = retryable


def clear_provider_error(attempt: GenerationAttempt) -> None:
    attempt.last_error_code = None
    attempt.error_message = None
    attempt.provider_error_details_json = None
    attempt.provider_error_retryable = None
