from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from libtv_agent.adapters.libtv import LibTVAdapter, LibTVError
from libtv_agent.adapters.object_store import ObjectStore
from libtv_agent.domain.contracts import generation_intent_hash
from libtv_agent.domain.enums import (
    AttemptStatus,
    CanvasMutationState,
    OperationStatus,
    ParentTaskPhase,
    SagaStatus,
)
from libtv_agent.domain.models import (
    CanvasProject,
    GenerationAttempt,
    GenerationReferenceAsset,
    MaterializationOperation,
    MaterializationSaga,
    ModelSchemaSnapshot,
    ParentTask,
)
from libtv_agent.services.model_registry import map_generation_params
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


def _node_key(payload: dict[str, Any], *, kind: str) -> str:
    value = (
        payload.get("nodeKey")
        or payload.get("newNodeKey")
        or payload.get("groupNodeKey")
        or payload.get("id")
    )
    if not value:
        raise LibTVError(
            "LIBTV_CLI_CONTRACT_ERROR",
            f"LibTV {kind} response did not contain a node identity",
        )
    return str(value)


def _canonicalize_prompt_references(
    prompt: str,
    references: list[tuple[str, str]],
) -> str:
    canonical = prompt
    for name, node_key in references:
        canonical = canonical.replace(
            f'{{{{Node "{name}"}}}}',
            "{{Node " + node_key + "}}",
        )
    return canonical


async def allocate_canvas(
    session: AsyncSession, adapter: LibTVAdapter, task: ParentTask
) -> CanvasProject:
    if task.assigned_project_uuid:
        assigned = await session.scalar(
            select(CanvasProject).where(
                CanvasProject.user_id == task.user_id,
                CanvasProject.project_uuid == task.assigned_project_uuid,
            )
        )
        if assigned is not None:
            return assigned
    canvas = await session.scalar(
        select(CanvasProject)
        .where(
            CanvasProject.user_id == task.user_id,
            CanvasProject.mutation_state == CanvasMutationState.OPEN,
        )
        .with_for_update()
    )
    if canvas is None:
        remote = await adapter.create_project(f"PROD-{task.user_id.hex[:8]}-{task.id.hex[:8]}")
        canvas = CanvasProject(
            user_id=task.user_id,
            project_uuid=str(remote["uuid"]),
            reservation_opened_at=datetime.now(UTC),
            batch_opened_at=datetime.now(UTC),
        )
        session.add(canvas)
        await session.flush()
    if canvas.reserved_parent_count >= 10:
        canvas.mutation_state = CanvasMutationState.DRAINING
        canvas.state_version += 1
        await session.flush()
        return await allocate_canvas(session, adapter, task)
    canvas.reserved_parent_count += 1
    canvas.state_version += 1
    task.assigned_project_uuid = canvas.project_uuid
    return canvas


async def _run_operation(
    session: AsyncSession,
    saga: MaterializationSaga,
    step: str,
    identity: str,
    action: Callable[[], Awaitable[dict[str, Any]]],
) -> dict[str, Any]:
    operation = await session.scalar(
        select(MaterializationOperation).where(
            MaterializationOperation.saga_id == saga.id,
            MaterializationOperation.step_type == step,
        )
    )
    if operation is not None and operation.status == OperationStatus.VERIFIED:
        return operation.remote_snapshot_json or {}
    if operation is None:
        operation = MaterializationOperation(
            saga_id=saga.id,
            step_type=step,
            expected_remote_identity=identity,
            attempt_count=0,
        )
        session.add(operation)
    operation.status = OperationStatus.EXECUTING
    operation.attempt_count += 1
    operation.started_at = datetime.now(UTC)
    await session.commit()
    try:
        result = await action()
    except LibTVError as exc:
        operation.status = (
            OperationStatus.WRITE_UNCERTAIN if exc.uncertain else OperationStatus.RETRYABLE
        )
        operation.last_error_code = exc.code
        await session.commit()
        raise
    operation.remote_node_key = str(
        result.get("nodeKey")
        or result.get("newNodeKey")
        or result.get("groupNodeKey")
        or result.get("uuid")
        or result.get("id")
        or ""
    )
    operation.remote_snapshot_json = result
    operation.status = OperationStatus.VERIFIED
    operation.completed_at = datetime.now(UTC)
    await session.commit()
    return result


async def materialize_task(
    session: AsyncSession,
    adapter: LibTVAdapter,
    object_store: ObjectStore,
    task: ParentTask,
    staging_root: Path,
) -> list[GenerationAttempt]:
    canvas = await allocate_canvas(session, adapter, task)
    saga = await session.scalar(
        select(MaterializationSaga).where(MaterializationSaga.parent_task_id == task.id)
    )
    if saga is None:
        saga = MaterializationSaga(
            parent_task_id=task.id,
            project_uuid=canvas.project_uuid,
            status=SagaStatus.EXECUTING,
        )
        session.add(saga)
        await session.flush()
    variant_ids = [variant.id for variant in task.variants]
    existing_attempts = list(
        await session.scalars(
            select(GenerationAttempt)
            .where(GenerationAttempt.variant_id.in_(variant_ids))
            .order_by(GenerationAttempt.created_at.desc())
        )
    )
    attempts_by_variant: dict[Any, GenerationAttempt] = {}
    for existing_attempt in existing_attempts:
        attempts_by_variant.setdefault(existing_attempt.variant_id, existing_attempt)
    attempts: list[GenerationAttempt] = []
    for variant in task.variants:
        attempt = attempts_by_variant.get(variant.id)
        if attempt is None:
            attempt = GenerationAttempt(
                variant_id=variant.id,
                project_uuid=canvas.project_uuid,
                status=AttemptStatus.MATERIALIZING,
            )
            session.add(attempt)
        attempts.append(attempt)
    await session.commit()

    short = task.id.hex[:8]
    try:
        group = await _run_operation(
            session,
            saga,
            "CREATE_GROUP",
            f"G-{short}",
            lambda: adapter.create_group(project_uuid=canvas.project_uuid, name=f"G-{short}"),
        )
        group_key = _node_key(group, kind="group create")
        image_keys: list[str] = []
        ordered_assets = sorted(
            (asset for asset in task.assets if asset.used_for_generation),
            key=lambda item: item.order_no,
        )
        if not ordered_assets:
            raise LibTVError("INPUT_OBJECT_MISSING", "at least one storyboard asset is required")
        for asset in ordered_assets:
            name = f"IMG-{short}-{asset.order_no}-{asset.version}"
            if not asset.object_key:
                raise LibTVError("INPUT_OBJECT_MISSING", f"asset {asset.id} has no source object")
            local_path = await object_store.localize(
                asset.object_key,
                staging_root / str(task.id) / f"asset-{asset.order_no}.jpg",
            )
            image = await _run_operation(
                session,
                saga,
                f"UPLOAD_IMAGE_{asset.order_no}",
                name,
                lambda asset=asset, name=name, local_path=local_path: adapter.upload_image(
                    project_uuid=canvas.project_uuid,
                    group_node_key=group_key,
                    name=name,
                    path=local_path,
                    order=asset.order_no,
                ),
            )
            asset.libtv_node_key = _node_key(image, kind="image upload")
            asset.materialized_at = datetime.now(UTC)
            image_keys.append(asset.libtv_node_key)

        snapshot_ids = {
            variant.schema_snapshot_id
            for variant in task.variants
            if variant.schema_snapshot_id is not None
        }
        schema_snapshots = {
            snapshot.id: snapshot
            for snapshot in await session.scalars(
                select(ModelSchemaSnapshot).where(ModelSchemaSnapshot.id.in_(snapshot_ids))
            )
        }
        existing_references = list(
            await session.scalars(
                select(GenerationReferenceAsset).where(
                    GenerationReferenceAsset.generation_variant_id.in_(variant_ids)
                )
            )
        )
        references_by_variant_asset = {
            (reference.generation_variant_id, reference.asset_id): reference
            for reference in existing_references
        }
        for variant, attempt in zip(task.variants, attempts, strict=True):
            name = f"VID-{short}-{variant.variant_type.value}-{variant.revision}"
            video = await _run_operation(
                session,
                saga,
                f"CREATE_VIDEO_{variant.variant_type.value}",
                name,
                lambda name=name: adapter.create_video_node(
                    project_uuid=canvas.project_uuid,
                    group_node_key=group_key,
                    name=name,
                ),
            )
            node_key = _node_key(video, kind="video node create")
            snapshot = schema_snapshots.get(variant.schema_snapshot_id)
            if snapshot is None:
                raise LibTVError("SCHEMA_SNAPSHOT_MISSING", "frozen model schema is unavailable")
            params = map_generation_params(variant.generation_config_json, snapshot.schema_json)
            await _run_operation(
                session,
                saga,
                f"CONFIGURE_{variant.variant_type.value}",
                node_key,
                lambda node_key=node_key, variant=variant, params=params: (
                    adapter.configure_video_node(
                        project_uuid=canvas.project_uuid,
                        node_key=node_key,
                        prompt=variant.prompt_text,
                        params=params,
                        input_node_keys=image_keys,
                    )
                ),
            )
            snapshot = await adapter.read_node(project_uuid=canvas.project_uuid, node_key=node_key)
            expected_prompt = _canonicalize_prompt_references(
                variant.prompt_text,
                [
                    (f"IMG-{short}-{asset.order_no}-{asset.version}", remote_key)
                    for asset, remote_key in zip(ordered_assets, image_keys, strict=True)
                ],
            )
            if snapshot.get("inputNodeKeys") != image_keys or snapshot.get("prompt") not in {
                variant.prompt_text,
                expected_prompt,
            }:
                raise LibTVError(
                    "MATERIALIZATION_UNCERTAIN",
                    "remote node readback did not match frozen order or prompt",
                    uncertain=True,
                )
            attempt.group_node_key = group_key
            attempt.video_node_key = node_key
            attempt.intent_hash = generation_intent_hash(
                {
                    "userId": str(task.user_id),
                    "parentTaskId": str(task.id),
                    "variant": variant.variant_type.value,
                    "projectUuid": canvas.project_uuid,
                    "groupNodeKey": group_key,
                    "nodeKey": node_key,
                    "modelKey": variant.generation_config_json["modelKey"],
                    "schemaFingerprint": str(variant.schema_snapshot_id),
                    "referenceAssets": image_keys,
                    "promptHash": variant.prompt_hash,
                    "generationConfig": variant.generation_config_json,
                    "assetVersion": 1,
                    "promptVersion": variant.prompt_template_version,
                }
            )
            attempt.status = AttemptStatus.PREPARED
            attempt.state_version += 1
            for asset, remote_key in zip(ordered_assets, image_keys, strict=True):
                reference = references_by_variant_asset.get((variant.id, asset.id))
                if reference is None:
                    reference = GenerationReferenceAsset(
                        generation_variant_id=variant.id,
                        asset_id=asset.id,
                        order_no=asset.order_no,
                        remote_node_key=remote_key,
                    )
                    session.add(reference)
                    references_by_variant_asset[(variant.id, asset.id)] = reference
        saga.status = SagaStatus.VERIFIED
        saga.state_version += 1
        if canvas.mutation_state == CanvasMutationState.QUARANTINED:
            canvas.mutation_state = CanvasMutationState.OPEN
            canvas.state_version += 1
        canvas.prepared_video_count += len(attempts)
        task.phase = ParentTaskPhase.QUEUED
        task.phase_reason_code = None
        task.state_version += 1
        await session.commit()
        return attempts
    except LibTVError as exc:
        saga.status = SagaStatus.WRITE_UNCERTAIN if exc.uncertain else SagaStatus.MANUAL_REVIEW
        saga.state_version += 1
        if exc.uncertain:
            canvas.mutation_state = CanvasMutationState.QUARANTINED
        task.phase = ParentTaskPhase.ACTION_REQUIRED
        task.phase_reason_code = exc.code
        task.state_version += 1
        await session.commit()
        raise
    except Exception:
        saga.status = SagaStatus.MANUAL_REVIEW
        saga.state_version += 1
        task.phase = ParentTaskPhase.ACTION_REQUIRED
        task.phase_reason_code = "MATERIALIZATION_INTERNAL_ERROR"
        task.state_version += 1
        await session.commit()
        raise
