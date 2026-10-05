import logging

from libtv_agent.logging_config import DiagnosticFormatter, configure_file_logging


def test_formatter_retains_operational_fields_without_uncontrolled_extras():
    record = logging.LogRecord("provider", logging.INFO, __file__, 1, "response", (), None)
    record.duration_ms = 125
    record.http_status = 429
    record.http_method = "GET"
    record.task_id = "private-task"
    record.provider = "token=private-provider"
    record.endpoint = "https://secret.invalid/path?token=private-token"
    record.prompt = "private-prompt"
    text = DiagnosticFormatter("%(message)s").format(record)
    assert '"duration_ms": 125' in text
    assert '"http_status": 429' in text
    assert '"http_method": "GET"' in text
    assert "private" not in text


def test_invalid_numeric_fields_are_not_logged():
    record = logging.LogRecord("provider", logging.INFO, __file__, 1, "response", (), None)
    record.duration_ms = float("nan")
    record.size_bytes = float("inf")
    record.count = -1
    record.http_status = "token=secret"
    assert DiagnosticFormatter("%(message)s").format(record) == "response"


def test_rotating_file_retains_safe_latency_and_redacts_secret(tmp_path):
    root = logging.getLogger()
    old_handlers, old_level = set(root.handlers), root.level
    path = tmp_path / "diagnostic.log"
    try:
        assert configure_file_logging(path) == path
        logging.getLogger("g1-diagnostic").info(
            "response token=private-value", extra={"duration_ms": 5, "prompt": "private-prompt"}
        )
        for handler in set(root.handlers) - old_handlers:
            handler.flush()
        text = path.read_text(encoding="utf-8")
        assert '"duration_ms": 5' in text
        assert "private-value" not in text and "private-prompt" not in text
    finally:
        for handler in set(root.handlers) - old_handlers:
            root.removeHandler(handler)
            handler.close()
        root.setLevel(old_level)


def test_file_logging_failure_can_be_reported_without_raising(tmp_path):
    errors = []
    missing_parent = tmp_path / "missing" / "diagnostic.log"

    # A directory at the target path makes the handler construction fail while
    # keeping the test independent of platform-specific permission behavior.
    missing_parent.parent.mkdir()
    missing_parent.mkdir()

    assert (
        configure_file_logging(missing_parent, failure_reporter=errors.append) is None
    )
    assert len(errors) == 1
    assert "unable to configure file logging" in errors[0]
    assert str(missing_parent) in errors[0]


def test_file_logging_reporter_failure_does_not_block_startup(tmp_path):
    missing_parent = tmp_path / "missing" / "diagnostic.log"
    missing_parent.parent.mkdir()
    missing_parent.mkdir()

    def broken_reporter(_message):
        raise RuntimeError("event log unavailable")

    assert configure_file_logging(missing_parent, failure_reporter=broken_reporter) is None
