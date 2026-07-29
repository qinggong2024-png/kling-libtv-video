import base64
import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

from libtv_agent.config import Settings

_FIELDS = {
    "libtvAccessKey": "libtv_access_key",
    "modelApiKey": "openai_api_key",
    "modelBaseUrl": "openai_base_url",
}
_DPAPI_FORMAT = "dpapi-machine-v1"
_CRYPTPROTECT_UI_FORBIDDEN = 0x1
_CRYPTPROTECT_LOCAL_MACHINE = 0x4


def _normalize_value(key: str, value: str) -> str:
    normalized = value.strip()
    if key != "modelBaseUrl":
        if len(normalized) < 8 or len(normalized) > 4096:
            raise ValueError(f"{key} must contain between 8 and 4096 characters")
        return normalized

    if len(normalized) > 2048:
        raise ValueError("modelBaseUrl must contain at most 2048 characters")
    parsed = urlsplit(normalized)
    loopback = parsed.hostname in {"localhost", "127.0.0.1", "::1"}
    if parsed.scheme != "https" and not (parsed.scheme == "http" and loopback):
        raise ValueError("modelBaseUrl must use HTTPS; HTTP is allowed only for localhost")
    if not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("modelBaseUrl must be an absolute URL without embedded credentials")
    if parsed.query or parsed.fragment:
        raise ValueError("modelBaseUrl cannot contain a query string or fragment")
    return normalized.rstrip("/")


def _read(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("administrator credentials file is invalid")
    if payload.get("format") == _DPAPI_FORMAT:
        if os.name != "nt" or not isinstance(payload.get("payload"), str):
            raise ValueError("DPAPI administrator credentials require Windows")
        try:
            import win32crypt

            encrypted = base64.b64decode(payload["payload"], validate=True)
            _, decrypted = win32crypt.CryptUnprotectData(
                encrypted, None, None, None, _CRYPTPROTECT_UI_FORBIDDEN
            )
            payload = json.loads(decrypted.decode("utf-8"))
        except Exception as exc:
            raise ValueError("administrator credentials could not be decrypted") from exc
        if not isinstance(payload, dict):
            raise ValueError("decrypted administrator credentials are invalid")
    return {
        key: value
        for key, value in payload.items()
        if key in _FIELDS and isinstance(value, str) and value
    }


def _serialize(values: dict[str, str]) -> str:
    plaintext = json.dumps(values, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
    if os.name != "nt":
        return plaintext.decode("utf-8")
    try:
        import win32crypt

        encrypted = win32crypt.CryptProtectData(
            plaintext,
            "LibTV administrator credentials",
            None,
            None,
            None,
            _CRYPTPROTECT_UI_FORBIDDEN | _CRYPTPROTECT_LOCAL_MACHINE,
        )
    except Exception as exc:
        raise RuntimeError("Windows DPAPI could not protect administrator credentials") from exc
    return json.dumps(
        {
            "format": _DPAPI_FORMAT,
            "payload": base64.b64encode(encrypted).decode("ascii"),
        },
        ensure_ascii=True,
        separators=(",", ":"),
    )


def _secure_file(path: Path, settings: Settings) -> None:
    os.chmod(path, 0o600)
    if os.name != "nt":
        return
    try:
        import win32api

        current_user = win32api.GetUserNameEx(win32api.NameSamCompatible)
        subprocess.run(
            [
                "icacls.exe",
                str(path),
                "/inheritance:r",
                "/grant:r",
                f"{current_user}:(F)",
                "SYSTEM:(F)",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        runner_acl = subprocess.run(
            ["icacls.exe", str(path), "/grant:r", f"{settings.runner_service_account}:(R)"],
            check=False,
            capture_output=True,
            text=True,
        )
        if runner_acl.returncode != 0 and settings.app_env in {"staging", "production"}:
            raise RuntimeError("Runner service account ACL could not be applied")
    except Exception as exc:
        if settings.app_env in {"staging", "production"}:
            raise RuntimeError("administrator credential ACL hardening failed") from exc


def _apply(settings: Settings, values: dict[str, str]) -> None:
    for external_name, setting_name in _FIELDS.items():
        value = values.get(external_name)
        if value:
            setattr(settings, setting_name, value)
    if settings.libtv_access_key:
        os.environ["LIBTV_ACCESS_KEY"] = settings.libtv_access_key
    else:
        os.environ.pop("LIBTV_ACCESS_KEY", None)


def load_admin_credentials(settings: Settings) -> None:
    _apply(settings, _read(settings.admin_credentials_file))


def credential_status(settings: Settings) -> dict[str, object]:
    path = settings.admin_credentials_file
    modified = (
        datetime.fromtimestamp(path.stat().st_mtime, UTC).isoformat() if path.is_file() else None
    )
    return {
        "libtvConfigured": bool(settings.libtv_access_key),
        "modelConfigured": bool(settings.openai_api_key),
        "modelBaseUrl": settings.openai_base_url,
        "updatedAt": modified,
    }


def update_admin_credentials(
    settings: Settings, updates: dict[str, str | None]
) -> dict[str, object]:
    unknown = set(updates) - _FIELDS.keys()
    if unknown:
        raise ValueError("unsupported administrator credential")
    stored = _read(settings.admin_credentials_file)
    for key, value in updates.items():
        if value is None:
            stored.pop(key, None)
            setattr(settings, _FIELDS[key], None)
            continue
        normalized = _normalize_value(key, value)
        stored[key] = normalized
        setattr(settings, _FIELDS[key], normalized)

    path = settings.admin_credentials_file
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.{os.getpid()}.tmp")
    temporary.write_text(_serialize(stored), encoding="utf-8")
    _secure_file(temporary, settings)
    temporary.replace(path)
    _secure_file(path, settings)
    _apply(settings, stored)
    return credential_status(settings)
