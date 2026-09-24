import logging
import json
import math
import re
from logging.handlers import RotatingFileHandler
from pathlib import Path

_REDACTIONS = (
    re.compile(r"(?i)data:image/[^\s;,]+(?:;[^,\s]+)?,[^\s\"'<>]+"),
    # Keep the URL path for diagnosis, never its access-bearing query string.
    re.compile(r"(?i)(https?://[^\s?\"'<>]+\?)[^\s\"'<>]+"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b"),
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/-]+=*"),
    re.compile(
        r"(?i)(api[_-]?key|access[_-]?key|secret|password|token)"
        r"([\"']?\s*[=:]\s*)"
        r"(?:\"[^\"]*\"|'[^']*'|[^\s,;&]+)"
    ),
    re.compile(r"(?i)(X-Amz-(?:Signature|Credential|Security-Token)=)[^&\s]+"),
)


def redact_text(value: str) -> str:
    redacted = value
    for pattern in _REDACTIONS:
        if pattern.groups:
            group_count = pattern.groups
            redacted = pattern.sub(
                lambda match, count=group_count: (
                    f"{match.group(1)}{match.group(2) if count > 1 else ''}[REDACTED]"
                ),
                redacted,
            )
        else:
            redacted = pattern.sub("[REDACTED]", redacted)
    return redacted


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact_text(record.getMessage())
        record.args = ()
        # Format before handlers append traceback text, without changing the exception.
        if record.exc_info and not record.exc_text:
            record.exc_text = logging.Formatter().formatException(record.exc_info)
        if record.exc_text:
            record.exc_text = redact_text(record.exc_text)
        if record.stack_info:
            record.stack_info = redact_text(record.stack_info)
        return True


class DiagnosticFormatter(logging.Formatter):
    """Expose bounded operational fields, never arbitrary LogRecord extras."""

    def format(self, record: logging.LogRecord) -> str:
        fields = {}
        for key in ("duration_ms", "size_bytes", "count", "http_status"):
            value = getattr(record, key, None)
            if type(value) in (int, float) and math.isfinite(value) and value >= 0:
                fields[key] = value
        method = getattr(record, "http_method", None)
        if method in {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"}:
            fields["http_method"] = method
        rendered = redact_text(super().format(record))
        if fields:
            rendered += " " + json.dumps(fields, sort_keys=True, allow_nan=False)
        return rendered


def configure_logging() -> None:
    root = logging.getLogger()
    if not root.handlers:
        logging.basicConfig(level=logging.INFO)
    for handler in root.handlers:
        if not any(isinstance(item, RedactingFilter) for item in handler.filters):
            handler.addFilter(RedactingFilter())


def configure_file_logging(
    path: Path,
    *,
    level: int = logging.INFO,
    max_bytes: int = 5 * 1024 * 1024,
    backup_count: int = 3,
) -> Path | None:
    """Attach a UTF-8 rotating file handler to the root logger.

    The Runner is launched in a hidden window with no stdout/stderr redirection
    (deliberately: see the note in scripts/start-local-api.ps1), so before this
    existed every ``logger.exception`` from the runner service loop went to
    ``logging.lastResort`` -> stderr -> a hidden console. Its redirected log
    files stayed at 0 bytes and the single most important diagnostic in the
    system was simply lost.

    Returns the log path on success, or None when the location cannot be
    written (for example when var\\ points at an offline data volume). Logging
    setup must never be the reason the runner fails to start.
    """
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(
            path,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
    except OSError:
        return None
    handler.setLevel(level)
    handler.setFormatter(
        DiagnosticFormatter(
            fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S%z",
        )
    )
    handler.addFilter(RedactingFilter())
    root = logging.getLogger()
    if not root.handlers:
        root.addHandler(logging.StreamHandler())
    root.addHandler(handler)
    root.setLevel(min(level, root.level or level))
    return path
