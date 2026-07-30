import asyncio
import base64
import uuid
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from libtv_agent.adapters.kling_official_cli import KlingCliError
from libtv_agent.adapters.object_store import ObjectStore
from libtv_agent.adapters.openai_analysis import (
    AnalysisImageInput,
    AnalysisResult,
    FakeAnalysisAdapter,
    OpenAIAnalysisAdapter,
    ReplayAnalysisAdapter,
)
from libtv_agent.adapters.video_provider import VideoProviderAdapter
from libtv_agent.config import Settings
from libtv_agent.domain.contracts import ordered_assets_hash, sha256_json
from libtv_agent.domain.enums import ParentTaskPhase, VariantKind
from libtv_agent.domain.models import (
    Asset,
    AuditEvent,
    ModelSchemaSnapshot,
    ParentTask,
    VisualFactCache,
)
from libtv_agent.services.analysis_lifecycle import (
    ANALYSIS_STAGE_COMPLETED,
    ANALYSIS_STAGE_PREPARING_IMAGES,
    ANALYSIS_STAGE_PROVIDER_RUNNING,
    ANALYSIS_STAGE_VALIDATING,
    StaleAnalysisRunError,
    touch_analysis_run,
)
from libtv_agent.services.feedback import load_feedback_guidance
from libtv_agent.services.model_registry import refresh_model_registry
from libtv_agent.services.prompts import (
    PROMPT_TEMPLATE_VERSION,
    calculate_timeline,
    count_ab_differences,
    normalize_analysis_motion,
    render_prompt,
    select_mode_type,
    select_prompt_max_chars,
    validate_ab_action_difference,
    validate_required_coverage,
)
from libtv_agent.services.risk import decide_consistency
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

FAKE_SCHEMA = {
    "maxMediaCount": 7,
    "maxPromptLength": 2000,
    "modeTypes": ["singleImage2video", "mixed2video"],
    "fields": {
        "model": {"originalField": "model"},
        "modeType": {"originalField": "modeType"},
        "quality": {"originalField": "quality", "enum": ["high"]},
        "duration": {"originalField": "duration", "enum": [10]},
        "aspectRatio": {"originalField": "aspectRatio", "enum": ["9:16"]},
        "sound": {"originalField": "sound", "enum": ["off"]},
    },
}

ANALYSIS_PROMPT_VERSION = "analysis-v2.6.0"
ANALYSIS_PROMPT_PATH = Path(__file__).parents[3] / "contracts" / "analysis-prompt-v2.6.0.txt"
ANALYSIS_IMAGE_CONCURRENCY = 4
VISUAL_FACT_CACHE_TTL = timedelta(days=30)
ANALYSIS_HEARTBEAT_SECONDS = 30


def render_analysis_prompt(
    asset_ids: list[str], user_requirement: str, product_asset_ids: list[str] | None = None
) -> str:
    template = ANALYSIS_PROMPT_PATH.read_text(encoding="utf-8")
    if ANALYSIS_PROMPT_VERSION not in template:
        raise RuntimeError("analysis prompt version marker is missing")
    manifest = "\n".join(
        f"- assetId={asset_id}; order={order}; role=STORYBOARD"
        for order, asset_id in enumerate(asset_ids, start=1)
    )
    product_ids = product_asset_ids or []
    if product_ids:
        manifest += "\n" + "\n".join(
            f"- assetId={asset_id}; role=PRODUCT_REFERENCE; referenceOrder={order}"
            for order, asset_id in enumerate(product_ids, start=1)
        )
    return template.replace("{{ASSET_MANIFEST}}", manifest).replace(
        "{{USER_REQUIREMENT}}", user_requirement.strip() or "(none)"
    )


async def _analysis_image_url(
    object_store: ObjectStore, object_key: str, asset_id: str, artifact_root: Path
) -> str:
    signed = await object_store.presign_get(object_key, expires_seconds=300)
    if signed:
        return signed
    localized = await object_store.localize(
        object_key, artifact_root / "cache" / "analysis" / f"{asset_id}.jpg"
    )
    payload = await asyncio.to_thread(localized.read_bytes)
    if not payload:
        raise ValueError(f"asset {asset_id} is empty")
    return "data:image/jpeg;base64," + base64.b64encode(payload).decode("ascii")


def _replace_asset_ids(value: Any, replacements: dict[str, str]) -> Any:
    if isinstance(value, str):
        return replacements.get(value, value)
    if isinstance(value, list):
        return [_replace_asset_ids(item, replacements) for item in value]
    if isinstance(value, dict):
        return {key: _replace_asset_ids(item, replacements) for key, item in value.items()}
    return value


def _cache_entry_is_current(entry: VisualFactCache, now: datetime) -> bool:
    if entry.expires_at is None:
        return True
    expires_at = entry.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    return expires_at > now


async def _prepare_analysis_images(
    session: AsyncSession,
    task_id: uuid.UUID,
    analysis_run_id: uuid.UUID,
    object_store: ObjectStore,
    assets: list[Asset],
    artifact_root: Path,
) -> list[AnalysisImageInput]:
    semaphore = asyncio.Semaphore(ANALYSIS_IMAGE_CONCURRENCY)

    async def prepare(index: int, asset: Asset) -> AnalysisImageInput:
        if not asset.object_key:
            raise ValueError(f"asset {asset.id} has no analysis object")
        async with semaphore:
            image_url = await _analysis_image_url(
                object_store, asset.object_key, str(asset.id), artifact_root
            )
        return AnalysisImageInput(
            asset_id=str(asset.id),
            order=index,
            role="PRODUCT_REFERENCE" if asset.role == "PRODUCT" else "STORYBOARD",
            image_url=image_url,
        )

    preparation_task = asyncio.gather(
        *(prepare(index, asset) for index, asset in enumerate(assets, start=1))
    )
    try:
        while True:
            done, _ = await asyncio.wait({preparation_task}, timeout=ANALYSIS_HEARTBEAT_SECONDS)
            if done:
                return list(await preparation_task)
            await touch_analysis_run(
                session,
                task_id,
                analysis_run_id,
                ANALYSIS_STAGE_PREPARING_IMAGES,
            )
    except BaseException:
        preparation_task.cancel()
        with suppress(asyncio.CancelledError):
            await preparation_task
        raise


async def _schema_snapshot(
    session: AsyncSession,
    settings: Settings,
    *,
    generation_provider: str,
    storyboard_count: int,
    kling_adapter: VideoProviderAdapter | None,
) -> ModelSchemaSnapshot:
    if generation_provider == "kling":
        if kling_adapter is None:
            raise KlingCliError("KLING_CAPABILITY_FETCH_FAILED", "Kling adapter is unavailable")
        capabilities = await kling_adapter.refresh_capabilities()
        if (
            storyboard_count > capabilities.image_input_limit
            and settings.kling_storyboard_fallback_mode != "first_last_frame"
        ):
            raise KlingCliError(
                "KLING_MULTI_STORYBOARD_UNSUPPORTED",
                (
                    "Current Kling provider cannot accept all ordered storyboard images; "
                    "explicit first_last_frame fallback is disabled"
                ),
            )
        model = settings.active_kling_model or next(iter(capabilities.supported_models), None)
        if model is None:
            raise KlingCliError(
                "KLING_CAPABILITY_UNSUPPORTED",
                "Current Kling account exposes no image-to-video model",
            )
        max_media = (
            storyboard_count
            if settings.kling_storyboard_fallback_mode == "first_last_frame"
            else capabilities.image_input_limit
        )
        schema = {
            "provider": kling_adapter.get_provider_name(),
            "modelKey": model,
            "maxMediaCount": max_media,
            "maxPromptLength": 3072 if settings.kling_provider_backend == "api" else 2000,
            "modeTypes": ["singleImage2video", "mixed2video"],
            "modeMediaRanges": {
                "singleImage2video": [1, 1],
                "mixed2video": [1, max_media],
            },
            "fields": {
                "duration": {"enum": list(capabilities.video_durations)},
                "aspectRatio": {"enum": list(capabilities.aspect_ratios)},
            },
            "rawCapabilities": capabilities.raw_capabilities,
        }
        fingerprint = sha256_json(schema)
        snapshot = await session.scalar(
            select(ModelSchemaSnapshot).where(
                ModelSchemaSnapshot.compatibility_fingerprint == fingerprint
            )
        )
        if snapshot is None:
            snapshot = ModelSchemaSnapshot(
                cli_version=capabilities.cli_version,
                account_id=settings.deployment_id,
                model_key=model,
                schema_json=schema,
                compatibility_fingerprint=fingerprint,
                fetched_at=capabilities.checked_at,
                expires_at=capabilities.checked_at
                + timedelta(seconds=settings.kling_cli_capability_cache_seconds),
            )
            session.add(snapshot)
            await session.flush()
        return snapshot
    if settings.libtv_adapter_mode == "real":
        return await refresh_model_registry(session, settings)
    fingerprint = sha256_json(FAKE_SCHEMA)
    snapshot = await session.scalar(
        select(ModelSchemaSnapshot).where(
            ModelSchemaSnapshot.compatibility_fingerprint == fingerprint
        )
    )
    if snapshot is None:
        snapshot = ModelSchemaSnapshot(
            cli_version="1.1.1",
            account_id="offline",
            model_key="kling-v3-omni",
            schema_json=FAKE_SCHEMA,
            compatibility_fingerprint=fingerprint,
            expires_at=datetime.now(UTC) + timedelta(minutes=30),
        )
        session.add(snapshot)
        await session.flush()
    return snapshot


async def _store_visual_fact_cache(
    session: AsyncSession,
    *,
    cache_key: str,
    ordered_storyboard_hash: str,
    model_version: str,
    schema_version: str,
    facts_json: dict[str, Any],
    expires_at: datetime,
) -> None:
    values = {
        "cache_key": cache_key,
        "ordered_storyboard_hash": ordered_storyboard_hash,
        "model_version": model_version,
        "schema_version": schema_version,
        "facts_json": facts_json,
        "expires_at": expires_at,
    }
    insert_factory = (
        sqlite_insert if session.get_bind().dialect.name == "sqlite" else postgresql_insert
    )
    statement = insert_factory(VisualFactCache).values(**values)
    await session.execute(
        statement.on_conflict_do_update(
            index_elements=["cache_key"],
            set_={key: value for key, value in values.items() if key != "cache_key"},
        )
    )


async def _await_provider_with_heartbeat(
    session: AsyncSession,
    task_id: uuid.UUID,
    analysis_run_id: uuid.UUID,
    adapter: FakeAnalysisAdapter | ReplayAnalysisAdapter | OpenAIAnalysisAdapter,
    prompt: str,
    images: list[AnalysisImageInput],
):
    provider_task = asyncio.create_task(adapter.analyze(prompt, images))
    try:
        while True:
            done, _ = await asyncio.wait({provider_task}, timeout=ANALYSIS_HEARTBEAT_SECONDS)
            if done:
                return await provider_task
            await touch_analysis_run(
                session,
                task_id,
                analysis_run_id,
                ANALYSIS_STAGE_PROVIDER_RUNNING,
            )
    except BaseException:
        provider_task.cancel()
        with suppress(asyncio.CancelledError):
            await provider_task
        raise


def _validated_analysis_timelines(
    analysis_json: dict[str, Any], required_asset_ids: list[str]
) -> dict[VariantKind, list[Any]]:
    plans = {
        VariantKind.STABLE: analysis_json["stablePlan"],
        VariantKind.DYNAMIC: analysis_json["dynamicPlan"],
    }
    timelines = {kind: calculate_timeline(plan["shots"], 10.0) for kind, plan in plans.items()}
    for timeline in timelines.values():
        validate_required_coverage(timeline, required_asset_ids)
    validate_ab_action_difference(timelines[VariantKind.STABLE], timelines[VariantKind.DYNAMIC])
    if count_ab_differences(timelines[VariantKind.STABLE], timelines[VariantKind.DYNAMIC]) < 2:
        raise ValueError("stable and dynamic plans must differ in at least two dimensions")
    return timelines


def _analysis_fallback_model(settings: Settings, primary_model: str) -> str | None:
    fallback_model = (settings.openai_analysis_fallback_model or "").strip()
    return fallback_model if fallback_model and fallback_model != primary_model else None


async def _run_openai_analysis_request(
    session: AsyncSession,
    task: ParentTask,
    settings: Settings,
    analysis_run_id: uuid.UUID,
    model: str,
    reasoning_effort: str,
    max_output_tokens: int,
    prompt: str,
    images: list[AnalysisImageInput],
    asset_ids: list[str],
) -> AnalysisResult:
    adapter = OpenAIAnalysisAdapter(
        settings.model_copy(
            update={
                "openai_model": model,
                "openai_reasoning_effort": reasoning_effort,
                "openai_analysis_max_output_tokens": max_output_tokens,
            }
        )
    )
    correlation_id = analysis_run_id.hex
    session.add(
        AuditEvent(
            action="OPENAI_ANALYSIS_REQUEST_STARTED",
            entity_type="ParentTask",
            entity_id=str(task.id),
            reason=model,
            correlation_id=correlation_id,
            evidence_refs_json=[
                ANALYSIS_PROMPT_VERSION,
                f"analysisRun:{analysis_run_id}",
                *asset_ids,
            ],
        )
    )
    await session.commit()
    try:
        result = await _await_provider_with_heartbeat(
            session,
            task.id,
            analysis_run_id,
            adapter,
            prompt,
            images,
        )
    except Exception as exc:
        await touch_analysis_run(
            session,
            task.id,
            analysis_run_id,
            ANALYSIS_STAGE_PROVIDER_RUNNING,
        )
        session.add(
            AuditEvent(
                action="OPENAI_ANALYSIS_REQUEST_FAILED",
                entity_type="ParentTask",
                entity_id=str(task.id),
                reason=type(exc).__name__,
                correlation_id=correlation_id,
                evidence_refs_json=[
                    ANALYSIS_PROMPT_VERSION,
                    f"analysisRun:{analysis_run_id}",
                    f"model:{model}",
                ],
            )
        )
        await session.commit()
        raise
    response_id = adapter.provider_response_id
    session.add(
        AuditEvent(
            action="OPENAI_ANALYSIS_REQUEST_SUCCEEDED",
            entity_type="ParentTask",
            entity_id=str(task.id),
            reason=model,
            correlation_id=correlation_id,
            evidence_refs_json=[
                ANALYSIS_PROMPT_VERSION,
                f"analysisRun:{analysis_run_id}",
                *([f"response:{response_id}"] if response_id else []),
            ],
        )
    )
    await session.commit()
    return result


async def analyze_task(
    session: AsyncSession,
    task: ParentTask,
    settings: Settings,
    object_store: ObjectStore,
    kling_adapter: VideoProviderAdapter | None = None,
    *,
    analysis_run_id: uuid.UUID,
) -> None:
    if task.phase != ParentTaskPhase.ANALYZING or task.analysis_run_id != analysis_run_id:
        raise StaleAnalysisRunError(f"analysis run {analysis_run_id} is no longer current")
    await touch_analysis_run(
        session,
        task.id,
        analysis_run_id,
        ANALYSIS_STAGE_PREPARING_IMAGES,
    )

    ordered = sorted(
        (asset for asset in task.assets if asset.used_for_analysis and asset.role != "PRODUCT"),
        key=lambda item: item.order_no,
    )
    product_references = sorted(
        (asset for asset in task.assets if asset.used_for_analysis and asset.role == "PRODUCT"),
        key=lambda item: item.order_no,
    )
    if not ordered:
        raise ValueError("at least one storyboard image is required")
    preference_snapshot = next(
        (
            variant.generation_config_json
            for variant in task.variants
            if variant.generation_config_json
        ),
        {},
    )
    analysis_model = str(preference_snapshot.get("analysisModel") or settings.openai_model)
    generation_provider = str(preference_snapshot.get("generationProvider") or "libtv")
    if generation_provider not in {"libtv", "kling"}:
        raise ValueError("selected generation provider is unavailable")
    if generation_provider == "kling" and not settings.kling_enabled:
        raise KlingCliError("KLING_CAPABILITY_UNSUPPORTED", "Kling Provider is disabled")
    fallback_model = _analysis_fallback_model(settings, analysis_model)
    ordered_hash = ordered_assets_hash(
        {"assetId": str(asset.id), "sha256": asset.sha256, "order": asset.order_no}
        for asset in ordered
    )
    storyboard_content_hash = ordered_assets_hash(
        {"sha256": asset.sha256, "order": index, "role": "STORYBOARD"}
        for index, asset in enumerate(ordered, start=1)
    )
    product_content_hash = ordered_assets_hash(
        {"sha256": asset.sha256, "order": index, "role": "PRODUCT_REFERENCE"}
        for index, asset in enumerate(product_references, start=1)
    )
    normalized_requirement = " ".join(task.user_requirement_raw.split())
    cache_key = sha256_json(
        {
            "orderedStoryboardContentHash": storyboard_content_hash,
            "productReferenceContentHash": product_content_hash,
            "userRequirementNormalized": normalized_requirement,
            "modelVersion": analysis_model,
            "fallbackModelVersion": fallback_model,
            "reasoningEffort": settings.openai_reasoning_effort,
            "fallbackReasoningEffort": settings.openai_analysis_fallback_reasoning_effort,
            "verbosity": settings.openai_analysis_verbosity,
            "maxOutputTokens": settings.openai_analysis_max_output_tokens,
            "fallbackMaxOutputTokens": settings.openai_analysis_fallback_max_output_tokens,
            "schemaVersion": "2.2",
            "analysisPromptVersion": ANALYSIS_PROMPT_VERSION,
        }
    )
    asset_ids = [str(asset.id) for asset in ordered]
    product_asset_ids = [str(asset.id) for asset in product_references]
    required_ids = [str(asset.id) for asset in ordered if asset.required]
    canonical_to_current = {
        **{f"STORYBOARD_{index}": asset_id for index, asset_id in enumerate(asset_ids, start=1)},
        **{
            f"PRODUCT_{index}": asset_id
            for index, asset_id in enumerate(product_asset_ids, start=1)
        },
    }
    cache_entry = await session.get(VisualFactCache, cache_key)
    now = datetime.now(UTC)
    if cache_entry is not None and _cache_entry_is_current(cache_entry, now):
        analysis_json = _replace_asset_ids(cache_entry.facts_json, canonical_to_current)
        await touch_analysis_run(
            session,
            task.id,
            analysis_run_id,
            ANALYSIS_STAGE_VALIDATING,
        )
    else:
        if settings.ai_adapter_mode == "replay":
            adapter = ReplayAnalysisAdapter(settings.ai_replay_fixture, asset_ids)
        elif settings.ai_adapter_mode == "fake":
            adapter = FakeAnalysisAdapter(asset_ids, task.user_requirement_raw)
        images = await _prepare_analysis_images(
            session,
            task.id,
            analysis_run_id,
            object_store,
            [*ordered, *product_references],
            settings.artifact_root,
        )
        await touch_analysis_run(
            session,
            task.id,
            analysis_run_id,
            ANALYSIS_STAGE_PROVIDER_RUNNING,
        )
        prompt = render_analysis_prompt(asset_ids, task.user_requirement_raw, product_asset_ids)
        if settings.ai_adapter_mode == "openai":
            try:
                result = await _run_openai_analysis_request(
                    session,
                    task,
                    settings,
                    analysis_run_id,
                    analysis_model,
                    settings.openai_reasoning_effort,
                    settings.openai_analysis_max_output_tokens,
                    prompt,
                    images,
                    asset_ids,
                )
                analysis_json = normalize_analysis_motion(
                    result.model_dump(mode="json", by_alias=True)
                )
                _validated_analysis_timelines(analysis_json, required_ids)
            except (RuntimeError, ValueError) as exc:
                if fallback_model is None:
                    raise
                session.add(
                    AuditEvent(
                        action="OPENAI_ANALYSIS_FALLBACK_STARTED",
                        entity_type="ParentTask",
                        entity_id=str(task.id),
                        reason=type(exc).__name__,
                        correlation_id=analysis_run_id.hex,
                        evidence_refs_json=[
                            ANALYSIS_PROMPT_VERSION,
                            f"analysisRun:{analysis_run_id}",
                            f"primaryModel:{analysis_model}",
                            f"fallbackModel:{fallback_model}",
                        ],
                    )
                )
                await session.commit()
                result = await _run_openai_analysis_request(
                    session,
                    task,
                    settings,
                    analysis_run_id,
                    fallback_model,
                    settings.openai_analysis_fallback_reasoning_effort,
                    settings.openai_analysis_fallback_max_output_tokens,
                    prompt,
                    images,
                    asset_ids,
                )
                analysis_json = normalize_analysis_motion(
                    result.model_dump(mode="json", by_alias=True)
                )
                _validated_analysis_timelines(analysis_json, required_ids)
        else:
            result = await _await_provider_with_heartbeat(
                session,
                task.id,
                analysis_run_id,
                adapter,
                prompt,
                images,
            )
            analysis_json = normalize_analysis_motion(result.model_dump(mode="json", by_alias=True))
            _validated_analysis_timelines(analysis_json, required_ids)
        current_to_canonical = {value: key for key, value in canonical_to_current.items()}
        cached_facts = _replace_asset_ids(analysis_json, current_to_canonical)
        await _store_visual_fact_cache(
            session,
            cache_key=cache_key,
            ordered_storyboard_hash=storyboard_content_hash,
            model_version=result.model_version,
            schema_version=result.schema_version,
            facts_json=cached_facts,
            expires_at=now + VISUAL_FACT_CACHE_TTL,
        )
        await touch_analysis_run(
            session,
            task.id,
            analysis_run_id,
            ANALYSIS_STAGE_VALIDATING,
        )

    analysis_json = normalize_analysis_motion(analysis_json)
    snapshot = await _schema_snapshot(
        session,
        settings,
        generation_provider=generation_provider,
        storyboard_count=len(ordered),
        kling_adapter=kling_adapter,
    )
    normalized_user_requirement = analysis_json["userRequirementNormalized"]
    consistency_level = decide_consistency(analysis_json)
    timelines = _validated_analysis_timelines(analysis_json, required_ids)
    mode_type = select_mode_type(len(ordered), snapshot.schema_json)
    model_key = snapshot.model_key if generation_provider == "kling" else "kling-v3-omni"
    config = {
        "preset": "DEFAULT_10S_9X16",
        "analysisModel": analysis_model,
        "generationProvider": generation_provider,
        "model": model_key if generation_provider == "kling" else "Kling O3",
        "modelKey": model_key,
        "modeType": mode_type,
        "quality": "high",
        "duration": 10,
        "aspectRatio": "9:16",
        "sound": "off",
        "smartStoryboard": len(ordered) > 1,
        "count": 1,
    }
    task_short = task.id.hex[:8]
    node_names = [f"IMG-{task_short}-{asset.order_no}-{asset.version}" for asset in ordered]
    feedback_guidance = await load_feedback_guidance(
        session,
        user_id=task.user_id,
        analysis_result=analysis_json,
    )
    prompt_max_chars = select_prompt_max_chars(
        generation_provider,
        int(snapshot.schema_json["maxPromptLength"]),
    )
    for variant in task.variants:
        variant.prompt_text = render_prompt(
            variant.variant_type,
            timelines[variant.variant_type],
            node_names,
            normalized_user_requirement,
            prompt_max_chars,
            feedback_guidance[variant.variant_type],
            garment_category=str(analysis_json.get("garmentFacts", {}).get("category", "")),
            storyboard_facts=list(analysis_json.get("storyboardFacts", [])),
        )
        variant.prompt_hash = sha256_json(variant.prompt_text)
        variant.prompt_template_version = PROMPT_TEMPLATE_VERSION
        variant.generation_config_json = config
        variant.generation_config_hash = sha256_json(config)
        variant.ordered_storyboard_assets_hash = ordered_hash
        variant.schema_snapshot_id = snapshot.id
    completed_at = datetime.now(UTC)
    analysis_elapsed_seconds = 0.0
    if task.analysis_started_at is not None:
        analysis_started_at = task.analysis_started_at
        if analysis_started_at.tzinfo is None:
            analysis_started_at = analysis_started_at.replace(tzinfo=UTC)
        analysis_elapsed_seconds = max(
            0.0,
            (completed_at - analysis_started_at.astimezone(UTC)).total_seconds(),
        )
    completed = await session.scalar(
        update(ParentTask)
        .where(
            ParentTask.id == task.id,
            ParentTask.phase == ParentTaskPhase.ANALYZING,
            ParentTask.analysis_run_id == analysis_run_id,
        )
        .values(
            phase=ParentTaskPhase.AWAITING_CONFIRMATION,
            phase_reason_code=None,
            analysis_result_json=analysis_json,
            analysis_result_hash=sha256_json(analysis_json),
            user_requirement_normalized=normalized_user_requirement,
            consistency_level=consistency_level,
            analysis_run_id=None,
            analysis_stage=ANALYSIS_STAGE_COMPLETED,
            analysis_heartbeat_at=completed_at,
            analysis_duration_seconds=(
                ParentTask.analysis_duration_seconds + analysis_elapsed_seconds
            ),
            state_version=ParentTask.state_version + 1,
            updated_at=completed_at,
        )
        .returning(ParentTask.id)
        .execution_options(synchronize_session=False)
    )
    if completed is None:
        await session.rollback()
        raise StaleAnalysisRunError(f"analysis run {analysis_run_id} is no longer current")
    await session.commit()
