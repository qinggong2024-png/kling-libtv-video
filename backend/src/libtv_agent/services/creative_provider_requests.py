"""Immutable dry-run/replay requests; no Provider, billing, or task creation.

Adapter parameters retain the existing payload field names. Media is expressed
as ordered object-key bindings, never as invented URLs or local paths. A future
authorized adapter must revalidate, materialize, and bind those inputs separately.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Annotated, Any, Literal

from libtv_agent.creative.text_contract import validate_text_contract
from libtv_agent.creative.visual_plan import (
    VisualPlan,
    VisualPlanRejected,
    assert_reference_budget,
    assert_visual_inputs,
    assert_visual_plan_current,
    compile_visual_video_prompt,
)
from libtv_agent.creative.workflow import digest
from libtv_agent.domain.models import (
    CreativeRecord,
    CreativeTask,
    ImageGenerationBatch,
    ImageGenerationItem,
    ImageGenerationOutput,
    Product,
    ProductVersion,
    StagedUpload,
    User,
)
from libtv_agent.services.creative_image_bridge import (
    CreativeImageBridgeRejected,
    plan_creative_image_bridge,
)
from libtv_agent.services.creative_video_bridge import (
    CreativeVideoBridgeRejected,
    plan_creative_video_bridge,
)
from libtv_agent.services.image_generations import build_prediction_payload
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
ExecutionSlot = Annotated[str, Field(pattern=r"^(FIRST_FRAME|SHOT_(0[1-9]|[12]\d|3[01]))$")]
RunMode = Literal["dry-run", "replay"]


class CreativeProviderRequestRejected(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class FrozenContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ImageProviderOptions(FrozenContract):
    provider: Literal["gpt", "nanobanana"] = "gpt"
    aspect_ratio: str = Field(default="9:16", pattern=r"^[1-9]\d*:[1-9]\d*$")
    resolution: Literal["1k", "2k", "4k"] = "2k"
    quality: Literal["low", "medium", "high"] | None = None
    output_format: Literal["png", "jpeg"] = "png"

    @model_validator(mode="after")
    def quality_supported(self) -> ImageProviderOptions:
        if self.provider == "nanobanana" and self.quality is not None:
            raise ValueError("Nano Banana does not support quality")
        return self


class VideoProviderOptions(FrozenContract):
    # Concrete adapter/model selection is explicit; no live capability discovery.
    provider: Literal["kling_official_api", "wavespeed_video", "bach"]
    model: str = Field(min_length=1)
    duration: int = Field(default=5, ge=3, le=15)
    aspect_ratio: Literal["9:16", "16:9", "1:1"] = "9:16"
    resolution: str | None = None
    audio: Literal["on", "off"] = "off"
    multi_shot: bool = Field(default=False, strict=True)


class SourceMapping(FrozenContract):
    package_revision_id: str
    candidate_id: str
    shot_id: str
    batch_id: str
    item_id: str
    output_id: str


class CanonicalProduct(FrozenContract):
    product_id: str
    product_version_id: str
    owner_id: str
    object_key: str = Field(min_length=1)
    sha256: Sha256
    evidence_status: Literal["OBSERVED_REFERENCE"] = "OBSERVED_REFERENCE"
    license_status: Literal["UNVERIFIED"] = "UNVERIFIED"
    materialized: Literal[True] = True


class ProviderReference(FrozenContract):
    role: Literal["PRODUCT", "FIRST_FRAME", "STORYBOARD"]
    order: int = Field(ge=1)
    adapter_field: Literal[
        "images", "first_frame_path", "refer_image_paths", "product_reference_paths"
    ]
    object_key: str = Field(min_length=1)
    sha256: Sha256
    source_mapping: SourceMapping | None = None
    keyframe_id: str | None = None
    product_view: Literal["front", "side", "back"] | None = None
    actual_submitted: Literal[False] = False
    provider_accepted: Literal[False] = False


class LockedProviderPrompt(FrozenContract):
    prompt: str = Field(min_length=1, max_length=3072)
    prompt_hash: Sha256
    preservation_hash: Sha256
    locks_hash: Sha256
    text_contract_hash: Sha256
    # Canonical JSON avoids retaining a mutable nested text-contract dictionary.
    text_contract_json: str


class ImagePredictionParameters(FrozenContract):
    prompt: str
    aspect_ratio: str
    resolution: str
    output_format: str
    quality: str | None = None
    enable_web_search: Literal[False] | None = None
    enable_image_search: Literal[False] | None = None


class VideoRequestParameters(FrozenContract):
    prompt: str
    model: str
    duration: int
    aspect_ratio: str
    resolution: str | None
    audio: str
    multi_shot: bool = False
    fallback_mode: Literal["disabled"] = "disabled"
    task_trace_id: str
    external_task_id: str


class ProviderRequestContract(FrozenContract):
    schema_version: Literal["creative-provider-request.v1"] = "creative-provider-request.v1"
    run_mode: RunMode = "dry-run"
    creative_task_id: str
    owner_id: str
    state_version: int
    package_revision_id: str
    shot_id: ExecutionSlot
    source_mapping: SourceMapping
    canonical_product: CanonicalProduct
    locked_prompt: LockedProviderPrompt
    references: tuple[ProviderReference, ...]
    idempotency_key: str
    bridge_validity_token: Sha256
    evidence_hash: Sha256
    request_hash: Sha256
    qualification_scope: Literal["OFFLINE_SYNTHETIC_ONLY"] = "OFFLINE_SYNTHETIC_ONLY"
    actual_submitted: Literal[False] = False
    provider_submission_allowed: Literal[False] = False
    ordinary_output_qualified: Literal[False] = False
    deliverable_eligible: Literal[False] = False
    media_binding_required: Literal[True] = True
    provider_capabilities_verified: Literal[False] = False


class CreativeImageProviderRequest(ProviderRequestContract):
    request_kind: Literal["image"] = "image"
    adapter_kind: Literal["wavespeed_prediction"] = "wavespeed_prediction"
    provider: Literal["gpt", "nanobanana"]
    model: str
    mode: Literal["edit"] = "edit"
    options: ImageProviderOptions
    adapter_parameters: ImagePredictionParameters


class CreativeVideoProviderRequest(ProviderRequestContract):
    request_kind: Literal["video"] = "video"
    adapter_kind: Literal["VideoGenerationRequest"] = "VideoGenerationRequest"
    execution_mode: Literal["director_fixed"] = "director_fixed"
    provider: str
    model: str
    options: VideoProviderOptions
    adapter_parameters: VideoRequestParameters


def _mapping(package_id: str, candidate_id: str, shot_id: str, source: Any) -> SourceMapping:
    return SourceMapping(
        package_revision_id=package_id,
        candidate_id=candidate_id,
        shot_id=shot_id,
        batch_id=source.batch_id,
        item_id=source.item_id,
        output_id=source.output_id,
    )


def _canonical(task: CreativeTask) -> CanonicalProduct:
    asset = task.snapshot_json["asset"]
    if asset.get("materialized") is not True:
        raise CreativeProviderRequestRejected("ASSET_NOT_MATERIALIZED")
    return CanonicalProduct(
        product_id=str(task.product_id),
        product_version_id=task.snapshot_json["product_version"]["product_version_id"],
        owner_id=str(task.user_id),
        object_key=asset["object_key"],
        sha256=asset["sha256"],
    )


def _locked(task: CreativeTask, package_id: str) -> LockedProviderPrompt:
    snapshot = task.snapshot_json
    stored = snapshot["package_contracts"][package_id]
    frozen = stored["text_contract"]
    package = snapshot["package"]
    if package["package_id"] != package_id:
        package = next(
            p for p in snapshot["storyboard"]["packages"].values()
            if p["package_id"] == package_id
        )
    result = validate_text_contract(
        snapshot["plan"], package, frozen, stored["registry_snapshot"], snapshot["facts_snapshot"]
    )
    if not result["valid"]:
        raise CreativeProviderRequestRejected("TEXT_CONTRACT_REJECTED")
    _visual_package(current_plan=snapshot["plan"], package=package)
    prompt = package["prompt"]
    if not prompt.strip() or len(prompt) > 3072:
        raise CreativeProviderRequestRejected("LOCKED_PROMPT_INVALID")
    return LockedProviderPrompt(
        prompt=prompt,
        prompt_hash=digest(prompt),
        preservation_hash=package["preservation_hash"],
        locks_hash=package["locks_hash"],
        text_contract_hash=frozen["contract_hash"],
        text_contract_json=json.dumps(frozen, sort_keys=True, separators=(",", ":")),
    )


def _visual_package(*, current_plan: dict, package: dict) -> VisualPlan:
    stored = package.get("visual_plan")
    if stored is None:
        # Historical text stays readable; submission requires a new frozen plan.
        raise CreativeProviderRequestRejected("VISUAL_PLAN_REQUIRED")
    direction = dict(next(
        item for item in current_plan["directions"]
        if item["id"] == current_plan["selected_direction"]
    ))
    user_locks = current_plan.get("locks", {}).get("user_locks", {})
    for key in ("photo_intent", "operator", "capture_reason", "attention", "body_state"):
        if isinstance(user_locks.get(key), str) and user_locks[key].strip():
            direction[key] = user_locks[key]
    locked_camera = user_locks.get("camera") or user_locks.get("framing")
    if isinstance(locked_camera, str) and locked_camera.strip():
        direction["camera"] = locked_camera
    try:
        visual = assert_visual_plan_current(current_plan, direction, stored)
        if visual.unresolved:
            raise VisualPlanRejected(visual.unresolved[0])
        if visual.missing_product_views:
            raise VisualPlanRejected("PRODUCT_VIEW_EVIDENCE_REQUIRED")
        if visual.budget_exceeded:
            raise VisualPlanRejected("VIDEO_REFERENCE_BUDGET_EXCEEDED")
        if any(item.role != "product" for item in visual.reservations):
            raise VisualPlanRejected("ADDITIONAL_REFERENCE_BINDING_REQUIRED")
        if current_plan.get("script_beats") is None and (
            len(visual.keyframes) != 1 or len(visual.shots) != 1
        ):
            raise VisualPlanRejected("DIRECTOR_MULTI_KEYFRAME_BINDING_REQUIRED")
        return visual
    except VisualPlanRejected as exc:
        raise CreativeProviderRequestRejected(exc.code) from exc


def _package(task: CreativeTask, package_id: str) -> dict:
    packages = [task.snapshot_json["package"],
                *task.snapshot_json.get("storyboard", {}).get("packages", {}).values()]
    return next(p for p in packages if p["package_id"] == package_id)


async def _product_references(
    session: AsyncSession, task: CreativeTask, visual: VisualPlan, *,
    field: str, start_order: int,
) -> tuple[ProviderReference, ...]:
    canonical = _canonical(task)
    refs = [ProviderReference(
        role="PRODUCT", order=start_order, adapter_field=field,
        object_key=canonical.object_key, sha256=canonical.sha256,
        product_view="front",
    )]
    plan = task.snapshot_json["plan"]
    version = task.snapshot_json["product_version"]
    view_sources = version.get("truth_fields", {}).get("product_view_uploads", {})
    required_views = {m.garment_view for beat in visual.beats for m in beat.moments} - {"front"}
    for view in sorted(required_views):
        stored = plan.get("product_reference_assets", {}).get(view, {})
        if not stored or view_sources.get(view) != stored.get("upload_id"):
            raise CreativeProviderRequestRejected("ADDITIONAL_REFERENCE_BINDING_REQUIRED")
        upload = await session.scalar(select(StagedUpload).where(
            StagedUpload.id == uuid.UUID(stored["upload_id"]), StagedUpload.user_id == task.user_id,
            StagedUpload.source_image_output_id.is_(None),
        ).execution_options(populate_existing=True))
        if (
            upload is None or upload.object_key != stored.get("object_key")
            or upload.sha256 != stored.get("sha256")
            or upload.sha256 != plan.get("product_view_evidence", {}).get(view)
            or upload.object_key not in version.get("source_asset_references", [])
        ):
            raise CreativeProviderRequestRejected("PRODUCT_VIEW_REFERENCE_STALE")
        refs.append(ProviderReference(
            role="PRODUCT", order=start_order + len(refs), adapter_field=field,
            object_key=upload.object_key, sha256=upload.sha256,
            product_view=view,
        ))
    if {r.sha256 for r in refs} != {r.source_id for r in visual.reservations}:
        raise CreativeProviderRequestRejected("REFERENCE_RESERVATIONS_NOT_BOUND")
    return tuple(refs)

async def _current_task(session: AsyncSession, task_id: uuid.UUID) -> CreativeTask:
    task = await session.scalar(
        select(CreativeTask).where(CreativeTask.id == task_id)
        .execution_options(populate_existing=True)
    )
    if task is None:
        raise CreativeProviderRequestRejected("TASK_NOT_FOUND")
    return task


async def _evidence_hash(
    session: AsyncSession, task: CreativeTask, mappings: tuple[SourceMapping, ...]
) -> str:
    # The video bridge token omits some mutable batch/item/output metadata.
    # Capture it here so even a still-valid changed source invalidates replay.
    media = []
    for mapping in mappings:
        row = (await session.execute(
            select(ImageGenerationBatch, ImageGenerationItem, ImageGenerationOutput)
            .join(ImageGenerationItem, ImageGenerationItem.batch_id == ImageGenerationBatch.id)
            .join(ImageGenerationOutput, ImageGenerationOutput.item_id == ImageGenerationItem.id)
            .where(
                ImageGenerationBatch.id == uuid.UUID(mapping.batch_id),
                ImageGenerationItem.id == uuid.UUID(mapping.item_id),
                ImageGenerationOutput.id == uuid.UUID(mapping.output_id),
            ).execution_options(populate_existing=True)
        )).one()
        media.append([
            {column.name: getattr(entity, column.name) for column in entity.__table__.columns}
            for entity in row
        ])
    records = list(await session.scalars(
        select(CreativeRecord).where(CreativeRecord.task_id == task.id)
        .order_by(CreativeRecord.id).execution_options(populate_existing=True)
    ))
    user = (await session.execute(
        select(User.id, User.role, User.is_active).where(User.id == task.user_id)
    )).one_or_none()
    if user is None or not user.is_active:
        raise CreativeProviderRequestRejected("OWNER_INACTIVE")
    product = (await session.execute(
        select(Product.__table__).where(Product.id == task.product_id)
    )).mappings().one()
    version = (await session.execute(
        select(ProductVersion.__table__).where(
            ProductVersion.id == uuid.UUID(
                task.snapshot_json["product_version"]["product_version_id"]
            )
        )
    )).mappings().one()
    for mapping in mappings:
        stored = task.snapshot_json["package_contracts"][mapping.package_revision_id]
        frozen = stored["text_contract"]
        if not any(
            record.kind == "text_contract"
            and record.record_key == mapping.package_revision_id
            and record.payload_json == frozen and record.content_hash == digest(frozen)
            for record in records
        ):
            raise CreativeProviderRequestRejected("TEXT_CONTRACT_EVIDENCE_MISMATCH")
    evidence = {
        "task": task.snapshot_json,
        "product": dict(product),
        "product_version": dict(version),
        "owner": {"id": str(user.id), "role": user.role, "is_active": user.is_active},
        "media": media,
        "records": [
            {"id": str(record.id), "kind": record.kind, "key": record.record_key,
             "content_hash": record.content_hash, "payload": record.payload_json}
            for record in records
        ],
    }
    # ORM UUIDs, datetimes and enum values are not accepted by workflow.digest.
    return hashlib.sha256(json.dumps(
        evidence, sort_keys=True, separators=(",", ":"), default=str
    ).encode()).hexdigest()


async def _verify_references(references: tuple[ProviderReference, ...], object_store: Any) -> None:
    checked = set()
    with TemporaryDirectory(prefix="creative-request-") as directory:
        for reference in references:
            identity = (reference.object_key, reference.sha256)
            if identity in checked:
                continue
            if not await object_store.exists(reference.object_key):
                raise CreativeProviderRequestRejected("REFERENCE_MISSING")
            path = await object_store.localize(
                reference.object_key, Path(directory) / str(reference.order)
            )
            if hashlib.sha256(path.read_bytes()).hexdigest() != reference.sha256:
                raise CreativeProviderRequestRejected("REFERENCE_HASH_MISMATCH")
            checked.add(identity)


def _sealed(request: Any) -> Any:
    return request.model_copy(update={
        "request_hash": digest(request.model_dump(mode="json", exclude={"request_hash"}))
    })


async def compile_creative_image_request(
    session: AsyncSession,
    task: CreativeTask,
    *,
    owner_id: uuid.UUID,
    object_store: Any,
    options: ImageProviderOptions | None = None,
    run_mode: RunMode = "dry-run",
    now: datetime | None = None,
    shot_id: str = "FIRST_FRAME",
) -> CreativeImageProviderRequest:
    options = options or ImageProviderOptions()
    try:
        if shot_id == "FIRST_FRAME":
            bridge = await plan_creative_image_bridge(
                session, task, owner_id=owner_id, object_store=object_store, now=now
            )
            package_id, candidate_id, source = (
                bridge.package_revision_id, bridge.candidate_id, bridge.source_mapping,
            )
        else:
            bridge = await plan_creative_video_bridge(
                session, task, owner_id=owner_id, object_store=object_store, now=now,
                only_storyboard_slot=shot_id,
            )
            source = bridge.storyboard
            assert source is not None
            package_id, candidate_id = source.package_revision_id, source.candidate_id
    except (CreativeImageBridgeRejected, CreativeVideoBridgeRejected) as exc:
        raise CreativeProviderRequestRejected(exc.code) from exc
    current = await _current_task(session, task.id)
    canonical = _canonical(current)
    locked = _locked(current, package_id)
    mapping = _mapping(package_id, candidate_id, shot_id, source)
    visual = _visual_package(
        current_plan=current.snapshot_json["plan"], package=_package(current, package_id),
    )
    references = await _product_references(session, current, visual, field="images", start_order=1)
    if shot_id != "FIRST_FRAME":
        first = bridge.first_frame
        references += (ProviderReference(
            role="FIRST_FRAME", order=len(references) + 1, adapter_field="images",
            object_key=first.object_key, sha256=first.output_sha256,
            source_mapping=_mapping(
                first.package_revision_id, first.candidate_id, first.shot_id, first,
            ),
        ),)
    await _verify_references(references, object_store)
    # Only real object keys are passed to infer edit mode. The images field is
    # removed; these keys must never be sent as URLs to submit_prediction.
    model, parameters = build_prediction_payload(
        provider=options.provider, prompt=locked.prompt,
        image_urls=[reference.object_key for reference in references],
        aspect_ratio=options.aspect_ratio, resolution=options.resolution,
        quality=options.quality, output_format=options.output_format,
    )
    parameters.pop("images")
    return _sealed(CreativeImageProviderRequest(
        creative_task_id=bridge.creative_task_id, owner_id=bridge.owner_id,
        state_version=bridge.state_version, package_revision_id=package_id,
        shot_id=shot_id, source_mapping=mapping, canonical_product=canonical,
        locked_prompt=locked, references=references, run_mode=run_mode,
        idempotency_key=f"creative-provider:image:{task.id}:{package_id}:{shot_id}",
        bridge_validity_token=bridge.validity_token,
        evidence_hash=await _evidence_hash(session, current, (mapping,)),
        request_hash="0" * 64, provider=options.provider, model=model, options=options,
        adapter_parameters=ImagePredictionParameters.model_validate(parameters),
    ))


async def compile_creative_video_request(
    session: AsyncSession,
    task: CreativeTask,
    *,
    owner_id: uuid.UUID,
    object_store: Any,
    options: VideoProviderOptions,
    run_mode: RunMode = "dry-run",
    now: datetime | None = None,
) -> CreativeVideoProviderRequest:
    try:
        bridge = await plan_creative_video_bridge(
            session, task, owner_id=owner_id, object_store=object_store, now=now
        )
    except CreativeVideoBridgeRejected as exc:
        raise CreativeProviderRequestRejected(exc.code) from exc
    current = await _current_task(session, task.id)
    canonical = _canonical(current)
    locked = _locked(current, bridge.package_revision_id)
    first = _mapping(
        bridge.first_frame.package_revision_id, bridge.first_frame.candidate_id,
        "FIRST_FRAME", bridge.first_frame,
    )
    source = bridge.storyboard or bridge.first_frame
    storyboard = _mapping(source.package_revision_id, source.candidate_id, source.shot_id, source)
    # Same wire order as KlingOfficialApiAdapter._request_image_inputs:
    # first frame, scene reference, product reference. Shared bytes keep roles.
    references = (
        ProviderReference(
            role="FIRST_FRAME", order=1, adapter_field="first_frame_path",
            object_key=bridge.first_frame.object_key, sha256=bridge.first_frame.output_sha256,
            source_mapping=first,
            keyframe_id=bridge.first_frame.keyframe_id,
        ),
        *(ProviderReference(
            role="STORYBOARD", order=index, adapter_field="refer_image_paths",
            object_key=s.object_key, sha256=s.output_sha256, keyframe_id=s.keyframe_id,
            source_mapping=_mapping(s.package_revision_id, s.candidate_id, s.shot_id, s),
        ) for index, s in enumerate(
            bridge.keyframe_sources[1:] if bridge.keyframe_sources else (source,), 2,
        ) if source is not bridge.first_frame),
    )
    package = _package(current, bridge.package_revision_id)
    visual = _visual_package(current_plan=current.snapshot_json["plan"], package=package)
    references += await _product_references(
        session, current, visual, field="product_reference_paths",
        start_order=len(references) + 1,
    )
    key_slots = (
        {r.keyframe_id: r.order for r in references if r.keyframe_id is not None}
        if bridge.keyframe_sources else {"K01": 1}
    )
    try:
        assert_reference_budget("kling", len(references))
        assert_visual_inputs(
            visual, key_slots, actual_slot_count=len(references), profile="kling",
        )
        if options.multi_shot != (len(visual.shots) > 1):
            raise VisualPlanRejected("VIDEO_SHOT_MODE_MISMATCH")
        if bridge.keyframe_sources and abs(
            sum(b.duration_seconds for b in visual.beats) - options.duration
        ) > 1e-6:
            raise VisualPlanRejected("VIDEO_DURATION_MISMATCH")
        timeline = compile_visual_video_prompt(
            visual, duration_seconds=options.duration, key_slots=key_slots,
        )
        roles = (
            "\n@image_2 is reviewed storyboard context; @image_3 is canonical "
            "product design only. Neither introduces an extra shot."
        ) if not bridge.keyframe_sources else "\n" + " ".join(
            f"@image_{r.order} is original {r.product_view} product design only, "
            "not another shot."
            for r in references if r.role == "PRODUCT"
        )
        if options.provider != "kling_official_api":
            timeline = timeline.replace("@image_", "reference image ")
            roles = roles.replace("@image_", "reference image ")
        video_prompt = (
            timeline + "\n" + (package.get("video_prompt_context") or locked.prompt) + roles
        )
        if len(video_prompt) > 3072:
            raise VisualPlanRejected("COMPILED_VIDEO_PROMPT_TOO_LONG")
    except VisualPlanRejected as exc:
        raise CreativeProviderRequestRejected(exc.code) from exc
    await _verify_references(references, object_store)
    identity = f"creative-provider:video:{task.id}:{bridge.package_revision_id}:SHOT_01"
    return _sealed(CreativeVideoProviderRequest(
        creative_task_id=bridge.creative_task_id, owner_id=bridge.owner_id,
        state_version=bridge.state_version, package_revision_id=bridge.package_revision_id,
        shot_id="SHOT_01", source_mapping=storyboard, canonical_product=canonical,
        locked_prompt=locked, references=references, run_mode=run_mode,
        idempotency_key=identity, bridge_validity_token=bridge.validity_token,
        evidence_hash=await _evidence_hash(session, current, tuple(
            r.source_mapping for r in references if r.source_mapping is not None
        )),
        request_hash="0" * 64, provider=options.provider, model=options.model, options=options,
        adapter_parameters=VideoRequestParameters(
            prompt=video_prompt, model=options.model, duration=options.duration,
            aspect_ratio=options.aspect_ratio, resolution=options.resolution,
            audio=options.audio, task_trace_id=task.id.hex,
            external_task_id=f"creative-{digest(identity)}",
            multi_shot=options.multi_shot,
        ),
    ))


async def assert_creative_provider_request_current(
    session: AsyncSession,
    task: CreativeTask,
    request: CreativeImageProviderRequest | CreativeVideoProviderRequest,
    *,
    owner_id: uuid.UUID,
    object_store: Any,
    now: datetime | None = None,
) -> CreativeImageProviderRequest | CreativeVideoProviderRequest:
    """Replay only after rebuilding from current persisted evidence and bytes."""
    if request.creative_task_id != str(task.id) or request.owner_id != str(owner_id):
        raise CreativeProviderRequestRejected("PROVIDER_REQUEST_STALE")
    common = {"owner_id": owner_id, "object_store": object_store,
              "run_mode": request.run_mode, "now": now}
    if isinstance(request, CreativeImageProviderRequest):
        current = await compile_creative_image_request(
            session, task, options=request.options, shot_id=request.shot_id, **common
        )
    else:
        current = await compile_creative_video_request(
            session, task, options=request.options, **common
        )
    if current != request:
        raise CreativeProviderRequestRejected("PROVIDER_REQUEST_STALE")
    return current
