from __future__ import annotations

from libtv_agent.adapters.kling_official_api import KlingOfficialApiAdapter
from libtv_agent.adapters.kling_official_cli import KlingOfficialCliAdapter
from libtv_agent.adapters.video_provider import VideoProviderAdapter
from libtv_agent.config import Settings


def create_kling_adapter(settings: Settings) -> VideoProviderAdapter:
    """Create the only adapter permitted to receive new production work."""
    return KlingOfficialApiAdapter(settings)


def create_kling_adapter_for_provider(
    settings: Settings,
    provider: str,
) -> VideoProviderAdapter:
    normalized = provider.strip().lower()
    if normalized in {"kling", settings.kling_api_provider_name.strip().lower()}:
        return KlingOfficialApiAdapter(settings)
    if normalized == settings.kling_cli_provider_name.strip().lower():
        # Historical attempts persist their concrete provider name. Keep the
        # adapter available for query/download recovery, never as the default.
        return KlingOfficialCliAdapter(settings)
    raise ValueError(f"unsupported Kling provider: {provider}")
