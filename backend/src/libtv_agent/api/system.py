from importlib.metadata import PackageNotFoundError, version

from fastapi import APIRouter, Request
from libtv_agent.api.dependencies import Session
from libtv_agent.config import Settings
from libtv_agent.domain.contracts import sha256_json
from libtv_agent.services.database_schema import inspect_database_schema
from libtv_agent.services.generation_safety import paid_generation_authorized

router = APIRouter(prefix="/system", tags=["system"])


def _runtime_version() -> str:
    try:
        return version("libtv-production-agent")
    except PackageNotFoundError:
        return "0.1.0"


def _config_revision(settings: Settings) -> str:
    return sha256_json(
        {
            "environment": settings.app_env,
            "deploymentId": settings.deployment_id,
            "aiAdapterMode": settings.ai_adapter_mode,
            "libtvAdapterMode": settings.libtv_adapter_mode,
            "libtvExecutionMode": settings.libtv_execution_mode,
            "paidGenerationEnabled": settings.paid_generation_enabled,
            "paidSubmissionsPaused": settings.paid_submissions_paused,
            "generationProvider": settings.active_kling_provider_name,
            "klingProviderBackend": settings.kling_provider_backend,
            "klingModel": settings.active_kling_model,
            "klingFallbackMode": settings.kling_storyboard_fallback_mode,
            "downloadConcurrency": settings.download_concurrency,
            "technicalValidationConcurrency": settings.technical_validation_concurrency,
            "outputRetentionDays": settings.output_retention_days,
        }
    )


@router.get("/status")
async def system_status(request: Request, session: Session) -> dict[str, object]:
    settings = request.app.state.settings
    connection = await session.connection()
    schema = await connection.run_sync(inspect_database_schema)
    schema_revision = ",".join(schema.current_revisions)
    if not schema_revision:
        schema_revision = f"metadata-equivalent:{','.join(schema.expected_revisions)}"
    kling_availability = request.app.state.kling_adapter.availability_snapshot()
    kling_capabilities = request.app.state.kling_adapter.capabilities_snapshot()
    return {
        "environment": settings.app_env,
        "sourceRevision": settings.deployment_source_revision,
        "schemaRevision": schema_revision,
        "configRevision": _config_revision(settings),
        "runtimeVersion": _runtime_version(),
        "libtvAdapter": settings.libtv_adapter_mode,
        "libtvExecutionMode": settings.libtv_execution_mode,
        "paidGenerationEnabled": settings.paid_generation_enabled,
        "paidGenerationAuthorized": paid_generation_authorized(settings),
        "paidGenerationBoundary": "libtv node <nodeKey> --project <projectUuid> --run",
        "openaiModel": settings.openai_model,
        "openaiConfigured": bool(settings.openai_api_key),
        "libtvConfigured": bool(settings.libtv_access_key),
        "outputRetentionDays": settings.output_retention_days,
        "downloadConcurrency": settings.download_concurrency,
        "technicalValidationConcurrency": settings.technical_validation_concurrency,
        "zipEnabled": False,
        "phaseOneUserId": settings.dev_user_id
        if settings.app_env in {"development", "test"}
        else None,
        "phaseOneAdminId": settings.dev_admin_id
        if settings.app_env in {"development", "test"}
        else None,
        "sharedAuthentication": settings.shared_authentication,
        "csrfCookieName": settings.csrf_cookie_name,
        "aiAdapter": settings.ai_adapter_mode,
        "kling": {
            "enabled": settings.kling_enabled,
            "backend": settings.kling_provider_backend,
            "provider": request.app.state.kling_adapter.get_provider_name(),
            "status": kling_availability.status,
            "available": kling_availability.available,
            "authenticated": kling_availability.authenticated,
            "reason": kling_availability.reason,
            "cliVersion": kling_availability.cli_version,
            "models": list(kling_capabilities.supported_models) if kling_capabilities else [],
            "supportsMultipleImages": (
                kling_capabilities.supports_multiple_images if kling_capabilities else False
            ),
            "imageInputLimit": (kling_capabilities.image_input_limit if kling_capabilities else 0),
            "fallbackMode": settings.kling_storyboard_fallback_mode,
        },
    }
