from __future__ import annotations

from typing import Literal

from libtv_agent.config import Settings

ProviderKind = Literal["libtv", "kling"]


def provider_kind(provider: str, settings: Settings) -> ProviderKind | None:
    normalized = provider.strip().lower()
    if normalized == "libtv":
        return "libtv"
    if normalized in {name.strip().lower() for name in settings.kling_provider_names}:
        return "kling"
    return None


def provider_capacity_scope(provider: str, settings: Settings) -> str | None:
    kind = provider_kind(provider, settings)
    return f"provider:{kind}" if kind else None
