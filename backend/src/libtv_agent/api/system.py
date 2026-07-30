from fastapi import APIRouter, Request
from libtv_agent.services.generation_safety import paid_generation_authorized

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/status")
async def system_status(request: Request) -> dict[str, object]:
    settings = request.app.state.settings
    kling_availability = request.app.state.kling_adapter.availability_snapshot()
    kling_capabilities = request.app.state.kling_adapter.capabilities_snapshot()
    return {
        "environment": settings.app_env,
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
            "backend": "api",
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
