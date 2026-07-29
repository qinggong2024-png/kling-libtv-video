from typing import Any

from libtv_agent.domain.enums import ConsistencyLevel

BLOCKING_FLAGS = {"SCHEMA_INCOMPATIBLE", "REMOTE_IDENTITY_CONFLICT", "INPUT_INVALID"}
REVIEW_FLAGS = {
    "STORYBOARD_GARMENT_CONFLICT",
    "STORYBOARD_IDENTITY_CONFLICT",
    "TEXT_OR_LOGO_KEY_SELLING_POINT",
}
WARNING_FLAGS = {
    "GARMENT_PARTIALLY_OCCLUDED",
    "LOW_DETAIL_REFERENCE",
    "LARGE_POSE_CHANGE",
    "SCENE_DISCONTINUITY",
    "MULTIPLE_PEOPLE",
    "BACK_VIEW_REQUIRED",
}


def decide_consistency(
    analysis: dict[str, Any], *, schema_compatible: bool = True
) -> ConsistencyLevel:
    flags = set(analysis.get("riskFlags", []))
    observations = analysis.get("consistencyObservations", {})
    if not schema_compatible or flags & BLOCKING_FLAGS:
        return ConsistencyLevel.SYSTEM_BLOCK
    if flags & REVIEW_FLAGS or observations.get("unknownFields"):
        return ConsistencyLevel.QUALITY_REVIEW
    if flags & WARNING_FLAGS:
        return ConsistencyLevel.WARNING
    return ConsistencyLevel.PASS
