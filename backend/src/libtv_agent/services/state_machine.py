import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Protocol

from libtv_agent.domain.enums import (
    DownloadStatus,
    GenerationStatus,
    ParentTaskPhase,
    QualityDecisionStatus,
    ValidationStatus,
)
from libtv_agent.domain.models import GenerationAttempt, ParentTask
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

CONTRACT_PATH = Path(__file__).resolve().parents[3] / "contracts" / "state-machines.json"


class VersionConflictError(RuntimeError):
    pass


class VariantDeliveryState(Protocol):
    generation_status: GenerationStatus
    download_status: DownloadStatus
    validation_status: ValidationStatus
    final_approval_status: QualityDecisionStatus


def aggregate_parent_phase(
    variants: Sequence[VariantDeliveryState],
) -> ParentTaskPhase:
    """Derive the parent phase without treating an intermediate result as task completion."""
    technically_valid = [
        item
        for item in variants
        if item.generation_status in {GenerationStatus.SUCCEEDED, GenerationStatus.PARTIAL}
        and item.download_status == DownloadStatus.READY
        and item.validation_status in {ValidationStatus.PASSED, ValidationStatus.WARNING}
    ]
    deliverable = [
        item
        for item in technically_valid
        if item.final_approval_status == QualityDecisionStatus.APPROVED
    ]
    if variants and len(deliverable) == len(variants):
        return ParentTaskPhase.DELIVERABLE

    blocked = [
        item
        for item in variants
        if (
            item.generation_status in {GenerationStatus.FAILED, GenerationStatus.UNKNOWN}
            or item.download_status == DownloadStatus.FAILED
            or item.validation_status in {ValidationStatus.FAILED, ValidationStatus.MANUAL_REVIEW}
        )
    ]
    if blocked:
        return (
            ParentTaskPhase.PARTIALLY_DELIVERABLE
            if deliverable
            else ParentTaskPhase.ACTION_REQUIRED
        )

    awaiting_approval = [
        item
        for item in technically_valid
        if item.final_approval_status == QualityDecisionStatus.PENDING
    ]
    rejected = [
        item
        for item in technically_valid
        if item.final_approval_status == QualityDecisionStatus.REJECTED
    ]
    if rejected:
        return (
            ParentTaskPhase.PARTIALLY_DELIVERABLE
            if deliverable
            else ParentTaskPhase.ACTION_REQUIRED
        )
    active = [
        item
        for item in variants
        if item.generation_status in {GenerationStatus.PENDING, GenerationStatus.RUNNING}
        or item.download_status
        in {DownloadStatus.NOT_READY, DownloadStatus.QUEUED, DownloadStatus.DOWNLOADING}
        or item.validation_status
        in {
            ValidationStatus.NOT_READY,
            ValidationStatus.TECHNICAL_CHECKING,
            ValidationStatus.AI_CHECKING,
        }
    ]
    if active:
        return ParentTaskPhase.GENERATING
    if awaiting_approval:
        return (
            ParentTaskPhase.PARTIALLY_DELIVERABLE
            if deliverable
            else ParentTaskPhase.AWAITING_FINAL_APPROVAL
        )

    # Pending generation, download, or validation work keeps the whole task active.
    return ParentTaskPhase.GENERATING


def load_state_machines() -> dict[str, Any]:
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


def assert_transition(machine: str, current: str, target: str) -> None:
    transitions = load_state_machines()[machine]["transitions"]
    if target not in transitions.get(current, []):
        raise ValueError(f"illegal {machine} transition: {current} -> {target}")


async def cas_task_phase(
    session: AsyncSession,
    task_id: object,
    expected_phase: str,
    expected_version: int,
    new_phase: str,
) -> int:
    assert_transition("parentTask", expected_phase, new_phase)
    result = await session.execute(
        update(ParentTask)
        .where(
            ParentTask.id == task_id,
            ParentTask.phase == expected_phase,
            ParentTask.state_version == expected_version,
        )
        .values(phase=new_phase, state_version=ParentTask.state_version + 1)
    )
    if result.rowcount != 1:
        raise VersionConflictError("task state changed")
    return expected_version + 1


async def cas_attempt_status(
    session: AsyncSession,
    attempt_id: object,
    expected_status: str,
    expected_version: int,
    new_status: str,
) -> int:
    assert_transition("generationAttempt", expected_status, new_status)
    result = await session.execute(
        update(GenerationAttempt)
        .where(
            GenerationAttempt.id == attempt_id,
            GenerationAttempt.status == expected_status,
            GenerationAttempt.state_version == expected_version,
        )
        .values(status=new_status, state_version=GenerationAttempt.state_version + 1)
    )
    if result.rowcount != 1:
        raise VersionConflictError("attempt state changed")
    return expected_version + 1
