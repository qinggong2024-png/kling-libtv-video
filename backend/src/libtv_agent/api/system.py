from fastapi import APIRouter, Request
from libtv_agent.services.generation_safety import paid_generation_authorized

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/status")
async def system_status(request: Request) -> dict[str, object]:
    settings = request.app.state.settings
    kling_availability = request.app.state.kling_adapter.availability_snapshot()
    kling_capabilities = request.app.state.kling_adapter.capabilities_snapshot()
    standard_video_durations = [str(value) for value in range(3, 16)]
    capability_defaults = {
        "api": {
            "imageInputLimit": 7,
            "supportsMultipleImages": True,
            "videoDurations": standard_video_durations,
            "tailImageVideoDurations": standard_video_durations,
        },
        "wavespeed": {
            "imageInputLimit": 7,
            "supportsMultipleImages": True,
            "videoDurations": standard_video_durations,
            "tailImageVideoDurations": standard_video_durations,
        },
        "bach": {
            "imageInputLimit": 2,
            "supportsMultipleImages": False,
            "videoDurations": [str(value) for value in range(1, 9)],
            "tailImageVideoDurations": [str(value) for value in range(1, 7)],
        },
    }
    active_defaults = capability_defaults.get(
        settings.kling_provider_backend,
        {
            "imageInputLimit": 0,
            "supportsMultipleImages": False,
            "videoDurations": standard_video_durations,
            "tailImageVideoDurations": standard_video_durations,
        },
    )
    active_model = settings.active_kling_model
    video_generation = {
        "enabled": settings.kling_enabled,
        "backend": settings.kling_provider_backend,
        "provider": request.app.state.kling_adapter.get_provider_name(),
        "model": active_model,
        "status": kling_availability.status,
        "available": kling_availability.available,
        "authenticated": kling_availability.authenticated,
        "reason": kling_availability.reason,
        "cliVersion": kling_availability.cli_version,
        "models": (
            list(kling_capabilities.supported_models)
            if kling_capabilities
            else ([active_model] if active_model else [])
        ),
        "supportsMultipleImages": (
            kling_capabilities.supports_multiple_images
            if kling_capabilities
            else active_defaults["supportsMultipleImages"]
        ),
        "imageInputLimit": (
            kling_capabilities.image_input_limit
            if kling_capabilities
            else active_defaults["imageInputLimit"]
        ),
        "videoDurations": (
            list(kling_capabilities.video_durations)
            if kling_capabilities and kling_capabilities.video_durations
            else active_defaults["videoDurations"]
        ),
        "tailImageVideoDurations": (
            list(kling_capabilities.tail_image_video_durations)
            if kling_capabilities and kling_capabilities.tail_image_video_durations
            else (
                list(kling_capabilities.video_durations)
                if kling_capabilities and kling_capabilities.video_durations
                else active_defaults["tailImageVideoDurations"]
            )
        ),
        "fallbackMode": settings.kling_storyboard_fallback_mode,
    }
    return {
        "environment": settings.app_env,
        "sourceRevision": settings.deployment_source_revision,
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
        "videoGeneration": video_generation,
        # Retained for older frontends while they migrate to the provider-neutral field.
        "kling": video_generation,
    }
