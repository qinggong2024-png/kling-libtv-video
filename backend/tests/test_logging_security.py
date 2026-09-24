import io
import logging

import pytest
from libtv_agent.logging_config import RedactingFilter, configure_logging, redact_text


@pytest.mark.parametrize(
    "source,secret",
    [
        ('{"api_key": "test-private-key"}', "test-private-key"),
        ("{'password': 'test-private-password'}", "test-private-password"),
        ("https://cdn.test/output?Signature=private-signature&Expires=123", "private-signature"),
        ("https://cdn.test/output?X-Goog-Signature=private-google", "private-google"),
        ("data:image/png;base64,cHJpdmF0ZS1yZWZlcmVuY2U=", "cHJpdmF0ZS1yZWZlcmVuY2U="),
    ],
)
def test_structured_credentials_and_media_are_redacted(source, secret):
    assert secret not in redact_text(source)


def test_exception_and_stack_are_redacted_without_mutating_exception():
    output = io.StringIO()
    handler = logging.StreamHandler(output)
    handler.addFilter(RedactingFilter())
    error = ValueError("token=exception-private")
    try:
        raise error
    except ValueError:
        import sys

        record = logging.LogRecord(
            "security-test", logging.ERROR, __file__, 1, "failure", (), sys.exc_info()
        )
    record.stack_info = "token=stack-private"
    handler.handle(record)
    assert "exception-private" not in output.getvalue()
    assert "stack-private" not in output.getvalue()
    assert "ValueError" in output.getvalue()
    assert str(error) == "token=exception-private"


def test_cached_exception_text_is_redacted():
    record = logging.LogRecord("security-test", logging.ERROR, __file__, 1, "failure", (), None)
    record.exc_text = "ValueError: token=cached-private"
    RedactingFilter().filter(record)
    assert "cached-private" not in record.exc_text


def test_logging_configuration_is_idempotent():
    root = logging.getLogger()
    handler = logging.StreamHandler(io.StringIO())
    root.addHandler(handler)
    try:
        configure_logging()
        configure_logging()
        assert sum(isinstance(item, RedactingFilter) for item in handler.filters) == 1
    finally:
        root.removeHandler(handler)
