from __future__ import annotations

from enum import StrEnum


class FactoryState(StrEnum):
    CREATED = "CREATED"
    PRODUCT_TRUTH_READY = "PRODUCT_TRUTH_READY"
    CREATIVE_PLANNED = "CREATIVE_PLANNED"
    IMAGE_GENERATING = "IMAGE_GENERATING"
    IMAGE_READY = "IMAGE_READY"
    IMAGE_QA_RUNNING = "IMAGE_QA_RUNNING"
    VIDEO_GENERATING = "VIDEO_GENERATING"
    VIDEO_READY = "VIDEO_READY"
    TEMPORAL_QA_RUNNING = "TEMPORAL_QA_RUNNING"
    SALVAGING = "SALVAGING"
    SEGMENT_READY = "SEGMENT_READY"
    EDIT_SKELETON_READY = "EDIT_SKELETON_READY"
    MUSIC_READY = "MUSIC_READY"
    EDITING = "EDITING"
    FINAL_QA = "FINAL_QA"
    DELIVERED = "DELIVERED"
    RETRYABLE_FAILED = "RETRYABLE_FAILED"
    TERMINAL_FAILED = "TERMINAL_FAILED"
    HUMAN_REVIEW = "HUMAN_REVIEW"
    CANCELLED = "CANCELLED"


_MAINLINE = (
    FactoryState.CREATED,
    FactoryState.PRODUCT_TRUTH_READY,
    FactoryState.CREATIVE_PLANNED,
    FactoryState.IMAGE_GENERATING,
    FactoryState.IMAGE_READY,
    FactoryState.IMAGE_QA_RUNNING,
    FactoryState.VIDEO_GENERATING,
    FactoryState.VIDEO_READY,
    FactoryState.TEMPORAL_QA_RUNNING,
    FactoryState.SALVAGING,
    FactoryState.SEGMENT_READY,
    FactoryState.EDIT_SKELETON_READY,
    FactoryState.MUSIC_READY,
    FactoryState.EDITING,
    FactoryState.FINAL_QA,
    FactoryState.DELIVERED,
)
TRANSITIONS = {state: {target} for state, target in zip(_MAINLINE, _MAINLINE[1:])}
for state in _MAINLINE[:-1]:
    TRANSITIONS[state].update(
        {FactoryState.RETRYABLE_FAILED, FactoryState.TERMINAL_FAILED, FactoryState.HUMAN_REVIEW,
         FactoryState.CANCELLED}
    )
TRANSITIONS[FactoryState.RETRYABLE_FAILED] = set(_MAINLINE[1:-1]) | {
    FactoryState.HUMAN_REVIEW,
    FactoryState.TERMINAL_FAILED,
    FactoryState.CANCELLED,
}


def assert_factory_transition(current: FactoryState, target: FactoryState) -> None:
    if target not in TRANSITIONS.get(current, set()):
        raise ValueError(f"illegal factory transition: {current} -> {target}")


def resume_state(persisted_state: str) -> FactoryState:
    """Restore the last persisted state; never silently restart from CREATED."""
    return FactoryState(persisted_state)
