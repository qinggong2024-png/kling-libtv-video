"""Append-only human feedback; never updates execution or approval state."""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, NoReturn

from libtv_agent.creative.human_review import (
    REVIEW_SCHEMA,
    HumanReviewEnvelope,
    HumanReviewExport,
    HumanReviewList,
    HumanReviewQuery,
    HumanReviewRecord,
    HumanReviewRequest,
    HumanReviewSubject,
)
from libtv_agent.creative.media_qualification import is_offline_synthetic_output
from libtv_agent.domain.contracts import canonical_json, sha256_json
from libtv_agent.domain.enums import DownloadStatus, UserRole
from libtv_agent.domain.models import (
    AuditEvent,
    CreativeTask,
    DownloadArtifact,
    GenerationAttempt,
    GenerationVariant,
    ImageGenerationBatch,
    ImageGenerationItem,
    ImageGenerationOutput,
    ParentTask,
    User,
)
from libtv_agent.services.idempotency import (
    IdempotencyConflictError,
    IdempotencyInProgressError,
    load_idempotent_response,
    store_idempotent_response,
)
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

ACTION = "HUMAN_PRODUCTION_REVIEW_V1"
PREFIX = "human-review:v1:"
ENTITY_TYPE = "human_production_review_subject"
MAX_ENVELOPE_BYTES = 16_384
_HASH = re.compile(r"^[0-9a-fA-F]{64}$")


class HumanReviewError(RuntimeError):
    def __init__(self, code: str, status_code: int = 409) -> None:
        self.code = code
        self.status_code = status_code
        super().__init__(code)


def fail(code: str, status_code: int = 409) -> NoReturn:
    raise HumanReviewError(code, status_code)


def _dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _hash(value: Any) -> str | None:
    return value.lower() if isinstance(value, str) and _HASH.fullmatch(value) else None


def _synthetic(mode: str, *values: Any) -> bool:
    if mode in {"fake", "replay"}:
        return True
    for value in values:
        if isinstance(value, str):
            if value.lower() in {"fake", "replay", "synthetic", "offline", "offline_synthetic"}:
                return True
            if value.lower().startswith(("fake:", "replay:")):
                return True
        elif isinstance(value, dict):
            if any(value.get(key) is True for key in ("synthetic", "offlineSynthetic")):
                return True
            if any(
                str(value.get(key, "")).upper() == "OFFLINE_SYNTHETIC_ONLY"
                for key in ("qualification", "qualificationScope", "qualification_scope")
            ):
                return True
            if any(_synthetic("", entry) for entry in value.values()):
                return True
        elif isinstance(value, list) and any(_synthetic("", entry) for entry in value):
            return True
    return False


def _uuid(value: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError:
        fail("HUMAN_REVIEW_SUBJECT_NOT_FOUND", 404)


def _provenance(*sources: dict) -> dict:
    result: dict[str, Any] = {}
    for source in sources:
        for target, aliases in (
            ("package_id", ("packageId", "package_id")),
            ("package_revision", ("packageRevision", "package_revision", "revision")),
            ("input_hash", ("inputHash", "input_hash", "sourceHash", "source_hash")),
            ("prompt_hash", ("promptHash", "prompt_hash")),
        ):
            for alias in aliases:
                value = source.get(alias)
                if target.endswith("_hash"):
                    value = _hash(value)
                elif target == "package_revision":
                    value = value if type(value) is int and value >= 1 else None
                else:
                    value = value if isinstance(value, str) and 0 < len(value) <= 160 else None
                if value is not None:
                    result.setdefault(target, value)
    return result


@dataclass(frozen=True)
class ResolvedSubject:
    subject: HumanReviewSubject
    owner_id: uuid.UUID
    ready: bool


def _check_task(query: HumanReviewQuery, task_id: uuid.UUID) -> None:
    if query.task_id is not None and query.task_id != task_id:
        fail("HUMAN_REVIEW_SUBJECT_NOT_FOUND", 404)


async def _image(
    session: AsyncSession, owner_id: uuid.UUID, output_id: str,
) -> tuple[ImageGenerationOutput, ImageGenerationItem, ImageGenerationBatch]:
    row = (await session.execute(
        select(ImageGenerationOutput, ImageGenerationItem, ImageGenerationBatch)
        .join(ImageGenerationItem, ImageGenerationItem.id == ImageGenerationOutput.item_id)
        .join(ImageGenerationBatch, ImageGenerationBatch.id == ImageGenerationItem.batch_id)
        .where(
            ImageGenerationOutput.id == _uuid(output_id), ImageGenerationBatch.user_id == owner_id,
        )
        .execution_options(populate_existing=True)
    )).first()
    if row is None:
        fail("HUMAN_REVIEW_SUBJECT_NOT_FOUND", 404)
    return row[0], row[1], row[2]


async def check_owner(
    session: AsyncSession, owner_id: uuid.UUID, query: HumanReviewQuery,
) -> None:
    """Replay checks access without requiring the old output hash to remain current."""
    if query.subject_type == "DIRECTOR_CANDIDATE":
        task = await session.scalar(
            select(CreativeTask).where(
                CreativeTask.id == query.task_id, CreativeTask.user_id == owner_id,
            ).execution_options(populate_existing=True)
        )
        if task is None:
            fail("HUMAN_REVIEW_SUBJECT_NOT_FOUND", 404)
        snapshot = _dict(task.snapshot_json)
        if not any(
            isinstance(candidate, dict) and candidate.get("candidate_id") == query.subject_id
            for values in (
                snapshot.get("candidates", []),
                _dict(snapshot.get("storyboard")).get("candidates", []),
            )
            if isinstance(values, list) for candidate in values
        ):
            fail("HUMAN_REVIEW_SUBJECT_NOT_FOUND", 404)
        return
    if query.subject_type == "IMAGE_OUTPUT":
        statement = (
            select(ImageGenerationBatch.id)
            .join(ImageGenerationItem, ImageGenerationItem.batch_id == ImageGenerationBatch.id)
            .join(ImageGenerationOutput, ImageGenerationOutput.item_id == ImageGenerationItem.id)
            .where(
                ImageGenerationOutput.id == _uuid(query.subject_id),
                ImageGenerationBatch.user_id == owner_id,
            )
        )
    else:
        statement = (
            select(ParentTask.id)
            .join(GenerationVariant, GenerationVariant.parent_task_id == ParentTask.id)
            .where(GenerationVariant.id == _uuid(query.subject_id), ParentTask.user_id == owner_id)
        )
    task_id = await session.scalar(statement)
    if task_id is None:
        fail("HUMAN_REVIEW_SUBJECT_NOT_FOUND", 404)
    _check_task(query, task_id)


async def resolve_subject(
    session: AsyncSession, owner_id: uuid.UUID, query: HumanReviewQuery, *, mode: str,
) -> ResolvedSubject:
    if query.subject_type == "IMAGE_OUTPUT":
        output, item, batch = await _image(session, owner_id, query.subject_id)
        _check_task(query, batch.id)
        provenance = _provenance(_dict(item.request_json), _dict(batch.request_json))
        provenance.setdefault("prompt_hash", hashlib.sha256(item.prompt.encode()).hexdigest())
        subject = HumanReviewSubject(
            subject_type=query.subject_type, subject_id=str(output.id), task_id=batch.id,
            output_hash=_hash(output.sha256),
            synthetic=mode in {"fake", "replay"} or is_offline_synthetic_output(
                output, item=item, batch=batch,
            ) or _synthetic(mode, item.request_json, batch.request_json, item.raw_response_json),
            **provenance,
        )
        return ResolvedSubject(subject, owner_id, bool(output.object_key and subject.output_hash))
    if query.subject_type == "VIDEO_VARIANT":
        row = (await session.execute(
            select(GenerationVariant, ParentTask)
            .join(ParentTask, ParentTask.id == GenerationVariant.parent_task_id)
            .where(GenerationVariant.id == _uuid(query.subject_id), ParentTask.user_id == owner_id)
            .execution_options(populate_existing=True)
        )).first()
        if row is None:
            fail("HUMAN_REVIEW_SUBJECT_NOT_FOUND", 404)
        variant, task = row
        _check_task(query, task.id)
        artifact_rows = (await session.execute(
            select(DownloadArtifact, GenerationAttempt)
            .join(GenerationAttempt, GenerationAttempt.id == DownloadArtifact.attempt_id)
            .where(
                GenerationAttempt.variant_id == variant.id,
                DownloadArtifact.status == DownloadStatus.READY,
                DownloadArtifact.deleted_at.is_(None),
                DownloadArtifact.deletion_pending_at.is_(None),
            )
            .order_by(
                DownloadArtifact.created_at.desc(), GenerationAttempt.created_at.desc(),
                DownloadArtifact.revision.desc(), DownloadArtifact.id.desc(),
            )
            .execution_options(populate_existing=True)
        )).all()
        artifact_row = next((
            row for row in artifact_rows
            if row[0].object_key and row[0].object_key.strip() and _hash(row[0].sha256)
        ), None)
        artifact, attempt = artifact_row if artifact_row else (None, None)
        config = _dict(variant.generation_config_json)
        provenance = _provenance(config, _dict(task.settings_json), _dict(task.compiled_plan_json))
        if _hash(variant.prompt_hash):
            provenance["prompt_hash"] = _hash(variant.prompt_hash)
        if _hash(variant.ordered_storyboard_assets_hash):
            provenance["input_hash"] = _hash(variant.ordered_storyboard_assets_hash)
        subject = HumanReviewSubject(
            subject_type=query.subject_type, subject_id=str(variant.id), task_id=task.id,
            output_hash=_hash(artifact.sha256) if artifact else None,
            synthetic=_synthetic(
                mode, config, task.settings_json,
                attempt.provider if attempt else None,
                attempt.raw_response_json if attempt else None,
                artifact.source_type if artifact else None,
            ), **provenance,
        )
        ready = bool(artifact and artifact.object_key and subject.output_hash)
        return ResolvedSubject(subject, owner_id, ready)
    task = await session.scalar(
        select(CreativeTask).where(
            CreativeTask.id == query.task_id, CreativeTask.user_id == owner_id,
        )
        .execution_options(populate_existing=True)
    )
    if task is None:
        fail("HUMAN_REVIEW_SUBJECT_NOT_FOUND", 404)
    snapshot = _dict(task.snapshot_json)
    storyboard = _dict(snapshot.get("storyboard"))
    candidates = [
        candidate
        for values in (snapshot.get("candidates", []), storyboard.get("candidates", []))
        if isinstance(values, list)
        for candidate in values
        if isinstance(candidate, dict) and candidate.get("candidate_id") == query.subject_id
    ]
    if len(candidates) != 1:
        fail("HUMAN_REVIEW_SUBJECT_NOT_FOUND", 404)
    candidate = candidates[0]
    packages = [
        _dict(snapshot.get("package")),
        *[_dict(value) for value in _dict(storyboard.get("packages")).values()],
    ]
    package = next(
        (value for value in packages if value.get("package_id") == candidate.get("package_id")), {},
    )
    provenance = _provenance(candidate, package)
    if not package:
        provenance.pop("package_id", None)
        provenance.pop("package_revision", None)
    asset = _dict(snapshot.get("asset"))
    if _hash(asset.get("sha256")):
        provenance.setdefault("input_hash", _hash(asset["sha256"]))
    if isinstance(package.get("prompt"), str):
        provenance.setdefault("prompt_hash", hashlib.sha256(package["prompt"].encode()).hexdigest())
    output_hash = _hash(candidate.get("sha256"))
    ready = bool(candidate.get("object_key") and output_hash)
    synthetic = _synthetic(mode, candidate, snapshot.get("mode"), package)
    if candidate.get("output_id"):
        output, item, batch = await _image(session, owner_id, candidate["output_id"])
        if output_hash != _hash(output.sha256) or (
            candidate.get("item_id") != str(item.id) or candidate.get("batch_id") != str(batch.id)
        ):
            fail("HUMAN_REVIEW_OUTPUT_BINDING_INVALID")
        for source in (batch.request_json, item.request_json):
            if (
                _dict(source).get("creativeTaskId") != str(task.id)
                or _dict(source).get("packageId") != candidate.get("package_id")
            ):
                fail("HUMAN_REVIEW_OUTPUT_BINDING_INVALID")
        if candidate.get("object_key") != output.object_key:
            fail("HUMAN_REVIEW_OUTPUT_BINDING_INVALID")
        ready = ready and bool(output.object_key)
        synthetic = synthetic or is_offline_synthetic_output(output, item=item, batch=batch)
    subject = HumanReviewSubject(
        subject_type=query.subject_type, subject_id=query.subject_id, task_id=task.id,
        output_hash=output_hash, synthetic=synthetic, **provenance,
    )
    return ResolvedSubject(subject, owner_id, ready)


def subject_entity_id(subject: HumanReviewSubject) -> str:
    return sha256_json({
        "subjectType": subject.subject_type, "subjectId": subject.subject_id,
        "taskId": str(subject.task_id) if subject.task_id else None,
    })


def _record(envelope: HumanReviewEnvelope) -> HumanReviewRecord:
    return HumanReviewRecord.model_validate(envelope.model_dump(
        exclude={"schema_version", "owner_id"}, by_alias=True,
    ))


def _decode(event: AuditEvent, resolved: ResolvedSubject) -> HumanReviewRecord:
    try:
        refs = event.evidence_refs_json
        if (
            event.action != ACTION or event.entity_type != ENTITY_TYPE
            or not isinstance(refs, list) or len(refs) != 1 or not isinstance(refs[0], str)
            or not refs[0].startswith(PREFIX)
            or len(refs[0].encode("utf-8")) > MAX_ENVELOPE_BYTES
        ):
            raise ValueError("invalid evidence envelope")
        raw = refs[0][len(PREFIX):]
        data = json.loads(raw)
        if not isinstance(data, dict) or data.get("schemaVersion") != REVIEW_SCHEMA:
            raise ValueError("unsupported evidence schema")
        envelope = HumanReviewEnvelope.model_validate(data)
        stored_at = (
            event.created_at.replace(tzinfo=UTC) if event.created_at.tzinfo is None
            else event.created_at.astimezone(UTC)
        )
        if (
            canonical_json(envelope.model_dump(mode="json", by_alias=True)) != raw
            or envelope.owner_id != resolved.owner_id
            or envelope.id != event.id or envelope.reviewer_id != event.actor_id
            or envelope.verdict != event.to_state or envelope.note != event.reason
            or subject_entity_id(envelope.subject) != event.entity_id
            or event.entity_id != subject_entity_id(resolved.subject)
            or envelope.reviewed_at != stored_at
        ):
            raise ValueError("inconsistent evidence envelope")
        return _record(envelope)
    except (ValueError, TypeError, AttributeError, RecursionError) as exc:
        raise HumanReviewError("HUMAN_REVIEW_EVIDENCE_INVALID") from exc


async def list_reviews(
    session: AsyncSession, owner_id: uuid.UUID, query: HumanReviewQuery, *, mode: str,
) -> HumanReviewList:
    resolved = await resolve_subject(session, owner_id, query, mode=mode)
    events = await session.scalars(
        select(AuditEvent).where(
            AuditEvent.action == ACTION, AuditEvent.entity_type == ENTITY_TYPE,
            AuditEvent.entity_id == subject_entity_id(resolved.subject),
        ).order_by(AuditEvent.created_at, AuditEvent.id)
    )
    return HumanReviewList(
        subject=resolved.subject, reviews=[_decode(event, resolved) for event in events],
    )


async def export_reviews(
    session: AsyncSession, owner_id: uuid.UUID, query: HumanReviewQuery, *,
    mode: str, include_synthetic: bool = False,
) -> HumanReviewExport:
    history = await list_reviews(session, owner_id, query, mode=mode)
    excluded = [
        review for review in history.reviews
        if not include_synthetic and (review.subject.synthetic or history.subject.synthetic)
    ]
    excluded_ids = {review.id for review in excluded}
    return HumanReviewExport(
        records=[review for review in history.reviews if review.id not in excluded_ids],
        excluded_synthetic_count=len(excluded),
    )


async def create_review(
    session: AsyncSession, actor: User, payload: HumanReviewRequest, *, mode: str,
) -> HumanReviewRecord:
    # The claim helper can roll back on replay; no pending audit may precede it.
    owner_id, role = actor.id, actor.role
    try:
        if role == UserRole.AUDITOR:
            fail("PERMISSION_DENIED", 403)
        query = HumanReviewQuery.model_validate(payload.model_dump(
            include={"subject_type", "subject_id", "task_id"}, by_alias=True,
        ))
        await check_owner(session, owner_id, query)
        request_payload = payload.model_dump(mode="json", by_alias=True)
        cached = await load_idempotent_response(
            session, tenant_id=str(owner_id), operation_type=ACTION,
            key=payload.review_key, payload=request_payload,
        )
        if cached is not None:
            try:
                record = HumanReviewRecord.model_validate(cached[1])
                if (
                    record.review_key != payload.review_key or record.reviewer_id != owner_id
                    or record.subject.subject_type != payload.subject_type
                    or record.subject.subject_id != (
                        query.subject_id if query.subject_type == "DIRECTOR_CANDIDATE"
                        else str(_uuid(query.subject_id))
                    )
                    or (query.task_id is not None and record.subject.task_id != query.task_id)
                ):
                    fail("HUMAN_REVIEW_EVIDENCE_INVALID")
            except ValidationError as exc:
                raise HumanReviewError("HUMAN_REVIEW_EVIDENCE_INVALID") from exc
            await check_owner(session, owner_id, query)
            return record
        resolved = await resolve_subject(session, owner_id, query, mode=mode)
        if not resolved.ready:
            fail("HUMAN_REVIEW_OUTPUT_NOT_READY")
        if resolved.subject.output_hash != payload.expected_output_hash:
            fail("HUMAN_REVIEW_OUTPUT_HASH_MISMATCH")
        now, review_id = datetime.now(UTC), uuid.uuid4()
        envelope = HumanReviewEnvelope(
            id=review_id, review_key=payload.review_key, reviewer_id=owner_id,
            reviewed_at=now, subject=resolved.subject, owner_id=owner_id,
            verdict=payload.verdict, reason_codes=payload.reason_codes, note=payload.note,
        )
        evidence = PREFIX + canonical_json(envelope.model_dump(mode="json", by_alias=True))
        if len(evidence.encode("utf-8")) > MAX_ENVELOPE_BYTES:
            fail("HUMAN_REVIEW_EVIDENCE_TOO_LARGE", 422)
        session.add(AuditEvent(
            id=review_id, actor_id=owner_id, action=ACTION, entity_type=ENTITY_TYPE,
            entity_id=subject_entity_id(resolved.subject), from_state=None,
            to_state=payload.verdict, reason=payload.note, created_at=now,
            correlation_id=hashlib.sha256(payload.review_key.encode("utf-8")).hexdigest(),
            evidence_refs_json=[evidence],
        ))
        await session.flush()
        record = _record(envelope)
        await store_idempotent_response(
            session, tenant_id=str(owner_id), operation_type=ACTION, key=payload.review_key,
            payload=request_payload, response_status=201,
            response_body=record.model_dump(mode="json", by_alias=True),
        )
        await session.commit()
        return record
    except IdempotencyConflictError as exc:
        await session.rollback()
        raise HumanReviewError("IDEMPOTENCY_CONFLICT") from exc
    except IdempotencyInProgressError as exc:
        await session.rollback()
        raise HumanReviewError("IDEMPOTENCY_REQUEST_IN_PROGRESS") from exc
    except BaseException:
        await session.rollback()
        raise
