import logging
import re
from logging.handlers import RotatingFileHandler
from pathlib import Path

_REDACTIONS = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b"),
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/-]+=*"),
    re.compile(r"(?i)(api[_-]?key|access[_-]?key|secret|password|token)(\s*[=:]\s*)[^\s,;&]+"),
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
        return True


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
        logging.Formatter(
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
