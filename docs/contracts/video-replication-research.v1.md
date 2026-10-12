# Video Replication Research Preparation v1

状态：P3 / schema-interface-adapter only
执行边界：Window 7
日期：2026-10-12

## Purpose

This package describes research inputs for a future video replication workflow. It stores reference-video metadata, observable Motion DNA, and a planning-only Video Blueprint. It does not replicate a video, generate a video, call a Provider, or submit a production task.

## Ownership

- `CreativeProject` remains the project identity and planning container.
- `CreativeIntelligenceSnapshot` remains an optional read-only extension point.
- `ProductionBridge` remains the owner of future production handoff preparation.
- Research objects are standalone planning data and do not become task state, billing state, quota state, ledger state, or delivery state.

## Models

### Reference Video Metadata

`ReferenceVideoMetadata` records provenance and technical facts that are already available to the caller. The adapter does not download, inspect, transcribe, or analyze a video. `rightsNote` is required so a reference can remain visibly research-only.

### Motion DNA

`MotionDna` records observable segments: subject action/state, camera movement, framing, pacing, product focus, and evidence confidence. `forbiddenInferences` prevents unseen facts from being silently promoted into a plan.

### Video Blueprint

`VideoBlueprint` is a human-reviewable shot plan. It can describe timing, camera intent, continuity constraints, and excluded elements. It intentionally contains no Provider model, endpoint, credential, task ID, pricing, or submission parameter.

## Adapter Contract

`createOfflineSyntheticResearchAdapter()` only validates and packages caller-provided metadata:

- default retrieval time is deterministic when no retrieval time is supplied;
- URLs must be `http` or `https`;
- reference metadata requires evidence and a rights note;
- Motion DNA requires at least one positive-duration segment;
- blueprint shots must be ordered contiguously from `1`;
- returned research is always `PREFLIGHT_REQUIRED`;
- `qualificationScope` is always `OFFLINE_SYNTHETIC_ONLY`;
- `providerSubmissionAllowed` is always `false`.

The adapter is not a video parser, downloader, renderer, prompt compiler, Provider adapter, or production bridge.

## Explicit Non-Goals

- no video copying or reconstruction;
- no frame extraction, audio analysis, transcription, or visual model calls;
- no Provider invocation or real video output;
- no API contract change;
- no edit to `frontend/src/api.ts`;
- no backend API, task state, billing, quota, ledger, or production-flow change;
- no claim that selection, qualification, or blueprint completion means delivery eligibility.

## Acceptance

The research package may be stored in planning context for later human review. It must remain separate from `CreativeProject` task execution and preserve `PREFLIGHT_REQUIRED` and `OFFLINE_SYNTHETIC_ONLY` until a separately approved contract exists.
