import logging
import re

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
