import asyncio
import logging
import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError, ProgrammingError

from libtv_agent import __version__
from libtv_agent.adapters.kling_official_cli import (
    KlingCliError,
)
from libtv_agent.adapters.kling_provider import create_kling_adapter
from libtv_agent.adapters.libtv import create_libtv_adapter
from libtv_agent.adapters.object_store import create_object_store
from libtv_agent.adapters.wavespeed import WaveSpeedAdapter
from libtv_agent.api.router import api_router
from libtv_agent.config import Settings, get_settings
from libtv_agent.db import Database
from libtv_agent.logging_config import configure_logging
from libtv_agent.services.analysis_lifecycle import recover_stale_analyses
from libtv_agent.services.bach_config import (
    bach_admin_config_signature,
    load_bach_admin_config,
)
from libtv_agent.services.confirmation_recovery import recover_stale_confirmation_claims
from libtv_agent.services.credentials import load_admin_credentials
from libtv_agent.services.feedback_learning import recover_feedback_learning_jobs
from libtv_agent.services.image_generations import refresh_active_batches
from libtv_agent.services.kling_config import (
    kling_admin_config_signature,
    load_kling_admin_config,
)
from libtv_agent.services.libtv_login import LibTVLoginManager
from libtv_agent.services.materialization_lifecycle import recover_stale_materializations
from libtv_agent.services.subject_elements import recover_subject_element_jobs
from libtv_agent.services.wavespeed_config import (
    load_wavespeed_admin_config,
    wavespeed_admin_config_signature,
)

logger = logging.getLogger(__name__)


async def _recover_stale_analyses(app: FastAPI) -> None:
    try:
        async with app.state.database.session_factory() as session:
            recovered = await recover_stale_analyses(session, app.state.settings)
            if recovered:
                logger.warning(
                    "recovered stale image analysis tasks",
                    extra={"task_ids": [str(task_id) for task_id in recovered]},
                )
    except Exception:
        # Recovery must not prevent liveness while a database is still starting up.
        logger.exception("stale image analysis recovery failed")


async def _recover_stale_materialization_tasks(app: FastAPI) -> None:
    try:
        async with app.state.database.session_factory() as session:
            recovered = await recover_stale_materializations(session, app.state.settings)
            if recovered:
                logger.warning(
                    "recovered stale materialization tasks",
                    extra={"task_ids": [str(task_id) for task_id in recovered]},
                )
    except Exception:
        # Recovery must not prevent liveness while a database is still starting up.
        logger.exception("stale materialization recovery failed")


async def _recover_stale_confirmation_claims(app: FastAPI) -> None:
    try:
        async with app.state.database.session_factory() as session:
            result = await recover_stale_confirmation_claims(session, app.state.settings)
            if any(result.values()):
                logger.warning(
                    "recovered stale confirmation claims",
                    extra={"confirmation_recovery": result},
                )
    except Exception:
        # A later runner sweep can retry recovery; startup must remain live.
        logger.exception("stale confirmation recovery failed")


async def _analysis_recovery_loop(app: FastAPI) -> None:
    while True:
        await asyncio.sleep(app.state.settings.analysis_recovery_poll_seconds)
        await _recover_stale_analyses(app)


async def _refresh_active_image_generation_batches(app: FastAPI) -> int:
    settings = app.state.settings
    if not settings.wavespeed_enabled or not settings.effective_wavespeed_api_key:
        return 0
    availability_snapshot = getattr(app.state.wavespeed_adapter, "availability_snapshot", None)
    if callable(availability_snapshot) and not availability_snapshot().available:
        return 0
    try:
        async with app.state.image_generation_refresh_lock:
            async with app.state.database.session_factory() as session:
                return await refresh_active_batches(session, app=app)
    except Exception:
        # Provider or database outages must not take down the API or stop later recovery attempts.
        logger.exception("active image generation recovery failed")
        return 0


async def _image_generation_recovery_loop(app: FastAPI) -> None:
    while True:
        await asyncio.sleep(app.state.settings.wavespeed_video_poll_interval_seconds)
        await _refresh_active_image_generation_batches(app)


async def _shutdown_analysis_jobs(app: FastAPI) -> None:
    jobs = set(app.state.analysis_jobs)
    if not jobs:
        return
    grace = app.state.settings.analysis_shutdown_grace_seconds
    done, pending = await asyncio.wait(jobs, timeout=grace)
    if pending:
        logger.info(
            "cancelling analysis jobs after shutdown grace period",
            extra={"pending_analysis_jobs": len(pending), "grace_seconds": grace},
        )
        for job in pending:
            job.cancel()
        cancelled, still_pending = await asyncio.wait(pending, timeout=grace)
        done |= cancelled
        if still_pending:
            logger.error(
                "analysis jobs ignored cancellation during shutdown",
                extra={"pending_analysis_jobs": len(still_pending), "grace_seconds": grace},
            )
    for job in done:
        if not job.cancelled():
            with suppress(Exception):
                job.exception()


async def _shutdown_confirmation_jobs(app: FastAPI) -> None:
    jobs = set(app.state.confirmation_jobs)
    if not jobs:
        return
    grace = app.state.settings.analysis_shutdown_grace_seconds
    done, pending = await asyncio.wait(jobs, timeout=grace)
    for job in pending:
        job.cancel()
    if pending:
        cancelled, still_pending = await asyncio.wait(pending, timeout=grace)
        done |= cancelled
        if still_pending:
            logger.error(
                "confirmation jobs ignored cancellation during shutdown",
                extra={"pending_confirmation_jobs": len(still_pending)},
            )
    for job in done:
        if not job.cancelled():
            with suppress(Exception):
                job.exception()


async def _shutdown_subject_element_jobs(app: FastAPI) -> None:
    jobs = set(app.state.subject_element_jobs)
    if not jobs:
        return
    grace = app.state.settings.analysis_shutdown_grace_seconds
    done, pending = await asyncio.wait(jobs, timeout=grace)
    for job in pending:
        job.cancel()
    if pending:
        cancelled, still_pending = await asyncio.wait(pending, timeout=grace)
        done |= cancelled
        if still_pending:
            logger.error(
                "subject element jobs ignored cancellation during shutdown",
                extra={"pending_subject_element_jobs": len(still_pending)},
            )
    for job in done:
        if not job.cancelled():
            with suppress(Exception):
                job.exception()


async def _shutdown_feedback_learning_jobs(app: FastAPI) -> None:
    jobs = set(app.state.feedback_learning_jobs)
    if not jobs:
        return
    grace = app.state.settings.analysis_shutdown_grace_seconds
    done, pending = await asyncio.wait(jobs, timeout=grace)
    for job in pending:
        job.cancel()
    if pending:
        cancelled, still_pending = await asyncio.wait(pending, timeout=grace)
        done |= cancelled
        if still_pending:
            logger.error(
                "feedback learning jobs ignored cancellation during shutdown",
                extra={"pending_feedback_learning_jobs": len(still_pending)},
            )
    for job in done:
        if not job.cancelled():
            with suppress(Exception):
                job.exception()


def create_app(settings: Settings | None = None) -> FastAPI:
    app_settings = settings or get_settings()
    app_settings.validate_shared_environment()
    load_admin_credentials(app_settings)
    load_kling_admin_config(app_settings)
    load_wavespeed_admin_config(app_settings)
    load_bach_admin_config(app_settings)
    configure_logging()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.database = Database(app_settings.database_url)
        await _recover_stale_analyses(app)
        await _recover_stale_materialization_tasks(app)
        await _recover_stale_confirmation_claims(app)
        try:
            recovered_subject_jobs = await recover_subject_element_jobs(app)
            if recovered_subject_jobs:
                logger.warning(
                    "recovered reusable Kling subject jobs",
                    extra={"recovered_subject_jobs": recovered_subject_jobs},
                )
        except Exception:
            # Database readiness remains the health endpoint's responsibility.
            logger.exception("reusable Kling subject job recovery failed")
        try:
            recovered_feedback_jobs = await recover_feedback_learning_jobs(app)
            if recovered_feedback_jobs:
                logger.info(
                    "recovered feedback learning jobs",
                    extra={"recovered_feedback_learning_jobs": recovered_feedback_jobs},
                )
        except Exception:
            logger.exception("feedback learning job recovery failed")
        if app_settings.kling_enabled:
            try:
                availability = await app.state.kling_adapter.check_availability()
                if availability.available:
                    await app.state.kling_adapter.refresh_capabilities(force=True)
            except KlingCliError as exc:
                logger.warning(
                    "Kling Provider capability refresh failed at startup: %s",
                    exc.code,
                )
        if app_settings.wavespeed_enabled:
            availability = await app.state.wavespeed_adapter.verify_credentials()
            if not availability.available:
                logger.warning(
                    "WaveSpeed read-only verification failed at startup: %s",
                    availability.status,
                )
        recovered_image_batches = await _refresh_active_image_generation_batches(app)
        if recovered_image_batches:
            logger.warning(
                "refreshed persisted WaveSpeed image batches",
                extra={"recovered_image_batches": recovered_image_batches},
            )
        recovery_task = asyncio.create_task(_analysis_recovery_loop(app))
        image_recovery_task = asyncio.create_task(_image_generation_recovery_loop(app))
        try:
            yield
        finally:
            await _shutdown_analysis_jobs(app)
            await _shutdown_confirmation_jobs(app)
            await _shutdown_subject_element_jobs(app)
            await _shutdown_feedback_learning_jobs(app)
            recovery_task.cancel()
            image_recovery_task.cancel()
            try:
                await recovery_task
            except asyncio.CancelledError:
                pass
            try:
                await image_recovery_task
            except asyncio.CancelledError:
                pass
            try:
                await app.state.libtv_login_manager.close()
            except Exception:
                # A failure while closing the login manager must not skip
                # database.dispose(); that would leak the engine on restart, and
                # this launcher restarts often.
                logger.exception("LibTV login manager shutdown failed")
            await app.state.database.dispose()

    app = FastAPI(
        title="固定视频生产 Agent API",
        version=__version__,
        lifespan=lifespan,
    )
    app.state.wavespeed_adapter = WaveSpeedAdapter(app_settings)
    app.state.libtv_adapter = create_libtv_adapter(app_settings)
    app.state.kling_adapter = create_kling_adapter(
        app_settings,
        wavespeed_client=app.state.wavespeed_adapter,
    )
    app.state.libtv_login_manager = LibTVLoginManager()
    app.state.object_store = create_object_store(app_settings)
    app.state.settings = app_settings
    app.state.kling_config_signature = kling_admin_config_signature(app_settings)
    app.state.wavespeed_config_signature = wavespeed_admin_config_signature(app_settings)
    app.state.bach_config_signature = bach_admin_config_signature(app_settings)
    app.state.analysis_jobs = set()
    app.state.confirmation_jobs = set()
    app.state.subject_element_jobs = set()
    app.state.subject_element_job_keys = set()
    app.state.image_generation_refresh_lock = asyncio.Lock()
    app.state.feedback_learning_jobs = set()
    app.state.feedback_learning_job_keys = set()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=app_settings.app_public_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "Idempotency-Key", "X-CSRF-Token", "X-User-Id"],
    )

    async def database_error_response(
        request: Request, exc: OperationalError | ProgrammingError
    ) -> JSONResponse:
        message = str(exc).lower()
        schema_error = any(
            marker in message
            for marker in (
                "no such table",
                "no such column",
                "undefined table",
                "undefined column",
                "does not exist",
            )
        )
        logger.error(
            "database request failed",
            extra={"path": request.url.path, "schema_error": schema_error},
            exc_info=(type(exc), exc, exc.__traceback__),
        )
        if schema_error:
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content={
                    "detail": {
                        "code": "DATABASE_SCHEMA_OUTDATED",
                        "message": "".join(
                            (
                                "数据库结构版本落后，服务未就绪。",
                                "请重启本地 API 以自动完成迁移。",
                            )
                        ),
                    }
                },
            )
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "detail": {
                    "code": "DATABASE_UNAVAILABLE",
                    "message": "数据库暂时不可用，请稍后重试。",
                }
            },
        )

    app.add_exception_handler(OperationalError, database_error_response)
    app.add_exception_handler(ProgrammingError, database_error_response)

    async def unhandled_error_response(request: Request, exc: Exception) -> JSONResponse:
        # Without this, an unexpected exception produced Starlette's bare
        # "Internal Server Error" body: no error code for the frontend to render
        # and no way to correlate a user report with a line in the log. The
        # traceback is still logged by the server itself; the id below is what
        # ties the two together.
        error_id = secrets.token_hex(8)
        logger.error(
            "unhandled request failure",
            extra={"path": request.url.path, "error_id": error_id},
            exc_info=(type(exc), exc, exc.__traceback__),
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "detail": {
                    "code": "INTERNAL_ERROR",
                    "errorId": error_id,
                    "message": "服务内部错误，请把错误编号连同操作步骤一起反馈。",
                }
            },
        )

    app.add_exception_handler(Exception, unhandled_error_response)

    @app.middleware("http")
    async def security_contract(request: Request, call_next):
        kling_config_signature = kling_admin_config_signature(app_settings)
        wavespeed_config_signature = wavespeed_admin_config_signature(app_settings)
        bach_config_signature = bach_admin_config_signature(app_settings)
        if kling_config_signature != app.state.kling_config_signature:
            try:
                load_kling_admin_config(app_settings)
                app.state.kling_adapter = create_kling_adapter(
                    app_settings,
                    wavespeed_client=app.state.wavespeed_adapter,
                )
            except Exception:
                logger.exception("rejected invalid Kling administrator configuration reload")
            finally:
                # Do not retry the same broken file on every request. A later file change
                # produces a new signature and is retried while the last valid adapter remains.
                app.state.kling_config_signature = kling_config_signature
        if wavespeed_config_signature != app.state.wavespeed_config_signature:
            try:
                load_wavespeed_admin_config(app_settings)
                app.state.wavespeed_adapter = WaveSpeedAdapter(app_settings)
                if app_settings.kling_provider_backend == "wavespeed":
                    app.state.kling_adapter = create_kling_adapter(
                        app_settings,
                        wavespeed_client=app.state.wavespeed_adapter,
                    )
            except Exception:
                logger.exception("rejected invalid WaveSpeed administrator configuration reload")
            finally:
                app.state.wavespeed_config_signature = wavespeed_config_signature
        if bach_config_signature != app.state.bach_config_signature:
            try:
                load_bach_admin_config(app_settings)
                if app_settings.kling_provider_backend == "bach":
                    app.state.kling_adapter = create_kling_adapter(
                        app_settings,
                        wavespeed_client=app.state.wavespeed_adapter,
                    )
            except Exception:
                logger.exception("rejected invalid Bach administrator configuration reload")
            finally:
                app.state.bach_config_signature = bach_config_signature
        shared = app_settings.shared_authentication
        unsafe = request.method in {"POST", "PUT", "PATCH", "DELETE"}
        login_path = request.url.path == "/api/v1/auth/login"
        if shared and unsafe and not login_path:
            cookie_token = request.cookies.get(app_settings.csrf_cookie_name)
            header_token = request.headers.get("X-CSRF-Token")
            if not cookie_token or not secrets.compare_digest(cookie_token, header_token or ""):
                return JSONResponse(
                    status_code=status.HTTP_403_FORBIDDEN,
                    content={"detail": {"code": "CSRF_REJECTED", "message": "CSRF token mismatch"}},
                )
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' blob: data:; media-src 'self' blob:; "
            "style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'"
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        return response

    app.include_router(api_router)
    return app
