from __future__ import annotations

from libtv_agent.adapters.kling_official_api import KlingOfficialApiAdapter
from libtv_agent.adapters.kling_official_cli import KlingOfficialCliAdapter
from libtv_agent.adapters.video_provider import VideoProviderAdapter
from libtv_agent.config import Settings


def create_kling_adapter(settings: Settings) -> VideoProviderAdapter:
    if settings.kling_provider_backend == "api":
        return KlingOfficialApiAdapter(settings)
    return KlingOfficialCliAdapter(settings)


def create_kling_adapter_for_provider(
    settings: Settings,
    provider: str,
) -> VideoProviderAdapter:
    normalized = provider.strip().lower()
    if normalized == settings.kling_api_provider_name.strip().lower():
        return KlingOfficialApiAdapter(settings)
    if normalized in {"kling", settings.kling_cli_provider_name.strip().lower()}:
        return KlingOfficialCliAdapter(settings)
    raise ValueError(f"unsupported Kling provider: {provider}")
