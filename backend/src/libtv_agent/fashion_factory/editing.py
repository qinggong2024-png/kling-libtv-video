from __future__ import annotations

import hashlib
import json

from .contracts import MusicTrack, RenderPlan, SemanticEditSkeleton


class IneligibleMusicError(ValueError):
    pass


def micro_align_cuts(
    skeleton: SemanticEditSkeleton,
    track: MusicTrack,
    *,
    preferred_tolerance_ms: int = 250,
    hard_max_tolerance_ms: int = 400,
) -> tuple[int, ...]:
    if not track.production_eligible:
        raise IneligibleMusicError("BGM is not eligible for production use")
    if preferred_tolerance_ms > hard_max_tolerance_ms:
        raise ValueError("preferred tolerance cannot exceed the hard maximum")
    aligned: list[int] = []
    beats = tuple(sorted(set(track.beats_ms + track.downbeats_ms)))
    for shot in skeleton.shots:
        candidates = [
            beat
            for beat in beats
            if shot.minimum_cut_ms <= beat <= shot.maximum_cut_ms
            and abs(beat - shot.semantic_cut_ms) <= hard_max_tolerance_ms
        ]
        if not candidates:
            aligned.append(shot.semantic_cut_ms)
            continue
        nearest = min(candidates, key=lambda beat: (abs(beat - shot.semantic_cut_ms), beat))
        if abs(nearest - shot.semantic_cut_ms) <= preferred_tolerance_ms:
            aligned.append(nearest)
        else:
            aligned.append(shot.semantic_cut_ms)
    return tuple(aligned)


def create_render_plan(
    render_plan_id: str,
    product_snapshot_id: str,
    source_clip_ids: tuple[str, ...],
    skeleton: SemanticEditSkeleton,
    track: MusicTrack,
) -> RenderPlan:
    cuts = micro_align_cuts(skeleton, track)
    lineage = {
        "product_snapshot_id": product_snapshot_id,
        "source_clip_ids": source_clip_ids,
        "skeleton": skeleton.model_dump(mode="json"),
        "track": track.model_dump(mode="json"),
        "cuts_ms": cuts,
    }
    fingerprint = hashlib.sha256(
        json.dumps(lineage, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return RenderPlan(
        render_plan_id=render_plan_id,
        product_snapshot_id=product_snapshot_id,
        source_clip_ids=source_clip_ids,
        cuts_ms=cuts,
        track_id=track.track_id,
        deterministic_fingerprint=fingerprint,
    )

