"""Read-only projection from current Creative Workflow records to CreativeState."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from libtv_agent.creative.state import (
    CreativeState,
    CreativeStateRevision,
    EvidenceRef,
    Provenance,
)
from libtv_agent.creative.state_adapters import (
    StoryboardSourceConflict,
    _mapping,
    adapt_camera_state,
    adapt_character_state,
    adapt_evidence_records,
    adapt_product_state,
    adapt_quality_state,
    adapt_scene_state,
    adapt_spatial_state,
    adapt_storyboard_state,
    validate_storyboard_state,
)
from libtv_agent.creative.state_revision import (
    calculate_locks_hash,
    calculate_source_snapshot_hash,
    seal_revision,
)


class ProjectionDiagnostic(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    severity: Literal["WARNING", "ERROR"]
    code: str = Field(min_length=1, max_length=120)
    message: str = Field(min_length=1, max_length=1000)
    source_refs: tuple[str, ...] = ()


class CreativeStateProjection(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, arbitrary_types_allowed=True)

    state: CreativeState | None = None
    revision: CreativeStateRevision | None = None
    diagnostics: tuple[ProjectionDiagnostic, ...] = ()

    @property
    def valid(self) -> bool:
        return self.state is not None and not any(
            item.severity == "ERROR" for item in self.diagnostics
        )

    @property
    def executable(self) -> bool:
        return self.state is not None and self.state.status == "READY" and self.valid


def _now(value: Any) -> str:
    if isinstance(value, datetime):
        timestamp = value if value.tzinfo else value.replace(tzinfo=UTC)
        return timestamp.astimezone(UTC).isoformat()
    if isinstance(value, str) and value.strip():
        return value
    return datetime.now(UTC).isoformat()


def _task_value(task: Mapping[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        if key in task and task[key] is not None:
            return task[key]
    return default


def _revision_ref(value: Any) -> str | None:
    if value is None:
        return None
    identifier = getattr(value, "character_id", None) or getattr(
        value, "scene_id", None
    ) or getattr(value, "spatial_id", None) or getattr(value, "camera_id", None)
    revision = getattr(value, "revision", None)
    if identifier is None or revision is None:
        return None
    return f"{identifier}:r{revision}"


def _diagnostic(
    diagnostics: list[ProjectionDiagnostic],
    severity: Literal["WARNING", "ERROR"],
    code: str,
    message: str,
    *source_refs: str,
) -> None:
    diagnostics.append(
        ProjectionDiagnostic(
            severity=severity,
            code=code,
            message=message,
            source_refs=tuple(source_refs),
        )
    )


def project_creative_state(
    *,
    creative_task: Mapping[str, Any],
    product_version: Mapping[str, Any],
    owner_id: str,
    source_assets: Sequence[Mapping[str, Any]] = (),
    records: Sequence[Mapping[str, Any]] = (),
    output_records: Sequence[Mapping[str, Any]] = (),
    intelligence_snapshot: Mapping[str, Any] | None = None,
    project_id: str | None = None,
) -> CreativeStateProjection:
    """Assemble a diagnostic projection without mutating its inputs."""
    task = _mapping(creative_task)
    product = _mapping(product_version)
    diagnostics: list[ProjectionDiagnostic] = []
    snapshot = _mapping(task.get("snapshot_json") or task.get("snapshot") or {})
    creative_state_id = str(
        _task_value(task, "creative_state_id", "creativeStateId", "id", default="creative-state")
    )
    task_owner = str(_task_value(task, "user_id", "userId", default=owner_id))
    if task_owner != owner_id:
        _diagnostic(
            diagnostics,
            "ERROR",
            "OWNER_MISMATCH",
            "creative task owner does not match the requested projection owner",
            creative_state_id,
        )
    snapshot_product = snapshot.get("product_version") or {}
    expected_product_version = str(
        product.get("product_version_id")
        or product.get("productVersionId")
        or product.get("id")
        or ""
    )
    snapshot_product_version = str(
        _mapping(snapshot_product).get("product_version_id")
        or _mapping(snapshot_product).get("productVersionId")
        or _mapping(snapshot_product).get("id")
        or ""
    )
    if snapshot_product_version and expected_product_version and (
        snapshot_product_version != expected_product_version
    ):
        _diagnostic(
            diagnostics,
            "ERROR",
            "PRODUCT_VERSION_CONFLICT",
            "task snapshot and supplied ProductVersion identify different versions",
            creative_state_id,
            expected_product_version,
            snapshot_product_version,
        )
    projected_assets = tuple(source_assets)
    snapshot_asset = snapshot.get("asset")
    if not projected_assets and isinstance(snapshot_asset, Mapping):
        projected_assets = (snapshot_asset,)
    product_state = adapt_product_state(
        product,
        owner_id=owner_id,
        source_assets=projected_assets,
    )
    if product_state.truth.facts_revision < 1:
        _diagnostic(
            diagnostics,
            "ERROR",
            "FACTS_REVISION_INVALID",
            "ProductState facts_revision must be positive",
            expected_product_version,
        )

    intelligence = _mapping(intelligence_snapshot) if intelligence_snapshot else {}
    character = adapt_character_state(
        intelligence.get("characterDNA") or intelligence.get("character_dna")
    )
    scene = adapt_scene_state(intelligence.get("sceneDNA") or intelligence.get("scene_dna"))
    camera = adapt_camera_state(intelligence.get("cameraDNA") or intelligence.get("camera_dna"))
    spatial = adapt_spatial_state(
        intelligence.get("spatialDNA")
        or intelligence.get("spatial_dna")
        or intelligence.get("spatialReference")
    )
    try:
        storyboard, shots = adapt_storyboard_state(
            {**snapshot, "creative_task_id": creative_state_id},
            product_version_id=product_state.product_version_id,
            character_revision=_revision_ref(character),
            scene_revision=_revision_ref(scene),
            spatial_revision=_revision_ref(spatial),
            camera_revision=_revision_ref(camera),
        )
    except StoryboardSourceConflict as exc:
        _diagnostic(diagnostics, "ERROR", exc.code, str(exc), exc.shot_id)
        return CreativeStateProjection(diagnostics=tuple(diagnostics))
    for shot in shots:
        if "selected_source_candidate" in shot.unresolved_references:
            _diagnostic(
                diagnostics,
                "WARNING",
                "SELECTED_SOURCE_UNRESOLVED",
                "selected candidate lacks a matching explicit shot/package source",
                shot.shot_id,
            )
    if not shots:
        _diagnostic(
            diagnostics,
            "WARNING",
            "STORYBOARD_MISSING",
            "no storyboard package is available; the projection remains draft-only",
            creative_state_id,
        )
    if character is None:
        _diagnostic(
            diagnostics,
            "WARNING",
            "CHARACTER_UNRESOLVED",
            "character reference is unresolved; no identity was invented",
            creative_state_id,
        )
    if scene is None:
        _diagnostic(
            diagnostics,
            "WARNING",
            "SCENE_UNRESOLVED",
            "scene reference is unresolved; no environment was invented",
            creative_state_id,
        )
    if spatial is None or not spatial.provider_submission_allowed:
        _diagnostic(
            diagnostics,
            "WARNING",
            "SPATIAL_SUBMISSION_BLOCKED",
            (
                "spatial reference is unresolved or not validated; provider "
                "submission remains blocked"
            ),
            creative_state_id,
        )
    storyboard_validation = validate_storyboard_state(
        storyboard,
        shots,
        product_revision=product_state.product_version_id,
        character_revision=_revision_ref(character),
        scene_revision=_revision_ref(scene),
        spatial=spatial,
        camera_revision=_revision_ref(camera),
    )
    for issue in storyboard_validation.issues:
        if not any(
            diagnostic.code == issue.code
            and diagnostic.source_refs == (
                (issue.shot_id,) if issue.shot_id else (creative_state_id,)
            )
            for diagnostic in diagnostics
        ):
            _diagnostic(
                diagnostics,
                issue.severity,
                issue.code,
                issue.message,
                issue.shot_id or creative_state_id,
            )
    record_maps = [_mapping(item) for item in records]
    evidence = (*adapt_evidence_records(record_maps),)
    quality = adapt_quality_state(record_maps, output_records=output_records)
    state_version = int(_task_value(task, "state_version", "stateVersion", default=0))
    revision_number = int(
        _task_value(
            task,
            "current_revision",
            "currentRevision",
            default=(
                snapshot.get("package", {}).get("revision", 1)
                if isinstance(snapshot.get("package"), Mapping)
                else 1
            ),
        )
    )
    package_ids = [
        shot.prompt_refs.image_prompt_revision
        for shot in shots
        if shot.prompt_refs.image_prompt_revision is not None
    ]
    if len(package_ids) != len(set(package_ids)):
        _diagnostic(
            diagnostics,
            "ERROR",
            "PACKAGE_ID_CONFLICT",
            "storyboard contains duplicate package IDs",
            creative_state_id,
        )
    status = "BLOCKED" if (
        any(item.severity == "ERROR" for item in diagnostics)
        or not storyboard_validation.executable
    ) else (
        "READY" if shots else "DRAFT"
    )
    revision = CreativeStateRevision(
        creative_state_id=creative_state_id,
        revision=revision_number,
        parent_revision=(
            revision_number - 1 if revision_number > 1 else None
        ),
        state_version=state_version,
        facts_revision=product_state.truth.facts_revision,
        content_hash="0" * 64,
        locks_hash=calculate_locks_hash(product_state),
        source_snapshot_hash=calculate_source_snapshot_hash(product_state),
        created_by=owner_id,
        created_at=_now(
            _task_value(task, "updated_at", "updatedAt", "created_at", "createdAt")
        ),
        reason="read-only projection from existing Creative Workflow records",
        product=product_state,
        character=character,
        scene=scene,
        spatial=spatial,
        camera=camera,
        storyboard=storyboard,
        shots=shots,
        quality=quality,
        evidence=tuple(
            EvidenceRef(
                evidence_id=f"creative-record:{item.evidence_id}",
                source_kind=item.source_kind,
                source_id=item.source_id,
                statement=item.statement,
                status=item.status,
            )
            for item in evidence
        ),
        provenance=Provenance(
            source_systems=("CreativeTask", "ProductVersion", "CreativeRecord"),
            source_record_ids=(creative_state_id, product_state.product_version_id),
            legacy_snapshot=True,
        ),
    )
    revision = seal_revision(revision)
    state = CreativeState.from_revision(
        revision,
        owner_id=owner_id,
        project_id=project_id,
        status=status,
    )
    return CreativeStateProjection(
        state=state,
        revision=revision,
        diagnostics=tuple(diagnostics),
    )
