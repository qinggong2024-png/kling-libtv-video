# Real Sample Test Protocol

Date: 2026-10-13

## Purpose

Validate one real product from intake through a reviewable advertising result. This is an evaluation protocol only. It does not change application code, prompts, adapters, providers, API contracts, or runtime configuration.

The test must keep these questions separate:

1. Did the system execute the requested step correctly?
2. Did the prompt and creative package express the intended direction correctly?
3. Did the image or video model produce an acceptable result from valid inputs?

## Test Unit

Run exactly one product in the first pass.

```yaml
product_count: 1
source_images: 1 primary front image, optional supporting images only if needed
brand_mode: generic or verified brand
creative_direction: one approved direction
image_outputs: one controlled first-frame candidate
video_outputs: one short final candidate
provider_calls: one image request and one video request at most
paid_submission: requires an explicit human decision at the final submit control
```

Do not compare multiple products in the first pass. The purpose is to establish a clean causal record.

## Required Inputs

Prepare these before opening the workflow:

```yaml
product_image:
  file: one clear product-front image
  format: PNG, JPG, or WEBP
  truth: product identity, visible colors, material, silhouette, and notable construction details

brand:
  mode: generic or verified brand
  name: required only for verified brand mode
  facts: only claims supported by the supplied product or brand material

creative_brief:
  audience: one sentence
  channel: one target placement
  goal: one advertising goal
  tone: three to five concrete adjectives
  forbidden_changes: product facts that must not change

acceptance:
  product_fidelity: must preserve the listed product facts
  brand_fidelity: must not invent brand claims
  visual_quality: no visible defects that prevent use
  continuity: product, subject, wardrobe, and shot intent remain consistent
  delivery: output can be reviewed and downloaded through the existing workflow
```

Record the input filename, file hash, product facts, and acceptance criteria before the first upload.

## Runtime Preflight

Run these checks immediately before the sample:

```yaml
frontend: http://127.0.0.1:5173/
backend_live: http://127.0.0.1:8000/api/v1/health/live
backend_ready: http://127.0.0.1:8000/api/v1/health/ready
expected_health: 200
expected_schema: e5f6a7b8c901
```

Record:

- branch and commit
- frontend and backend ports
- database revision
- source image hash
- current runtime mode and provider status
- whether paid generation is authorized

Stop before the sample if any health check fails, the schema is not at head, or the selected runtime profile is unclear.

## Execution Steps

### 1. Product Intake

In Director Studio:

1. Open the product intake stage.
2. Upload the single primary product image.
3. Select generic style or the verified brand mode.
4. Confirm the visible product facts shown by the system.
5. Record upload response, task identifier, status transitions, and any error.

Observe:

- The browser remains responsive.
- The upload request reaches the backend.
- The product image is associated with the intended task.
- The system does not invent a brand or product fact.
- Refreshing the page does not lose the saved intake state.

Stop if the upload fails, the state is lost, or the displayed facts contradict the supplied product.

### 2. Creative Direction

After product intake is accepted:

1. Generate one creative direction.
2. Review the audience, setting, action, camera intent, and tone.
3. Compare every product claim against the recorded truth.
4. Accept or reject the direction as a human reviewer.

Record:

- direction identifier and revision
- request and response status
- generated direction text
- factual conflicts
- reviewer decision and reason

Do not continue to production planning if the direction changes a forbidden product fact.

### 3. Creative Package

After accepting the direction:

1. Generate the production package.
2. Inspect the image prompt, video prompt, shot list, negative constraints, and continuity notes.
3. Confirm that the package references the locked product and the accepted direction.
4. Confirm that image and video tasks use the same product identity and package revision.

The package is acceptable only when a human can explain how each requested visual requirement maps to a package field or prompt instruction.

### 4. Image Candidate

Before the provider call:

1. Capture the compiled request and package revision.
2. Confirm the provider, model, execution mode, and estimated cost shown by the system.
3. Stop at the final submission control and record the evidence.
4. Continue only when the real sample has been explicitly authorized for this product.

After the image returns, inspect:

- product silhouette, color, material, logos, labels, and construction
- composition and camera framing
- subject interaction with the product
- lighting and obvious rendering defects
- whether the result matches the accepted direction

Keep one candidate for the first pass. Do not hide weak results by generating multiple variants.

### 5. Video Candidate

Proceed only after the image candidate passes the product-fidelity gate:

1. Confirm that the video request references the accepted image/package revision.
2. Confirm shot duration, aspect ratio, camera movement, and continuity constraints.
3. Submit one video request only.
4. Review the returned video for product continuity, motion defects, temporal stability, and advertising usefulness.

Do not start retries until the failure is classified and documented.

### 6. Final Review

Score the single result against the recorded acceptance criteria:

```yaml
product_fidelity: pass/fail
brand_fidelity: pass/fail/not_applicable
creative_match: pass/fail
visual_quality: pass/fail
temporal_quality: pass/fail/not_applicable
workflow_delivery: pass/fail
overall_decision: accept/reject/retest
```

The first sample passes only when the workflow delivered a reviewable result and the result meets the agreed product-fidelity and visual-quality gates.

## Evidence Record

Create one evidence record for every step:

```yaml
step:
timestamp:
input_hash:
task_id:
package_revision:
request_id:
endpoint:
http_status:
ui_state:
expected:
actual:
artifact_path:
error_text:
classification:
confidence:
```

Capture screenshots for visible defects and preserve response bodies or server log excerpts for transport and persistence failures. Do not record secrets or full credential values.

## Defect Classification

### Code or Runtime

Classify as code/runtime when the system fails to execute a valid request or preserve its contract:

- page crash, blank screen, or JavaScript exception
- wrong route, 404, 5xx, timeout, or broken API proxy
- request never reaches the backend
- valid response is not persisted or cannot be reloaded
- schema, state, task, package, or revision identifiers are inconsistent
- UI shows a state different from the backend response
- upload, review, download, or status transition is impossible despite valid inputs
- provider request is malformed because the application compiled it incorrectly

Required evidence: endpoint, status code, request identifier, response or log excerpt, and the expected contract.

### Prompt or Creative Package

Classify as prompt/package when the workflow is healthy and the provider receives a coherent request, but the request does not express the approved creative intent:

- required product facts are missing from the prompt
- forbidden changes are not stated
- shot action, framing, tone, or continuity instruction is absent or contradictory
- image and video prompts reference different product/package revisions
- negative constraints do not cover a known acceptance requirement
- the direction is internally inconsistent before provider execution

Required evidence: accepted direction, compiled package, exact prompt revision, and the missing or conflicting instruction.

### Model Capability

Classify as model capability when the request, product facts, package, provider response, and workflow state are all correct, but the generated media still fails visually:

- product details drift despite explicit correct instructions
- anatomy, hands, text, logos, reflections, or fine materials render incorrectly
- motion causes temporal instability or object deformation
- composition is valid but visual quality is below the agreed threshold
- repeated execution with the same valid request shows provider/model limitations

Required evidence: exact request and input artifacts, model/provider identity, returned media, and confirmation that the application compiled the request correctly.

### Unknown

Use `unknown` when evidence does not distinguish the three categories. Do not label a defect as a prompt or model problem until the request and workflow logs have been checked.

## Stop and Escalation Rules

Stop the sample immediately when:

- health readiness is not `200`
- product identity or brand attribution is wrong
- a required human review gate is bypassed
- a request would incur a paid action without explicit confirmation
- the provider returns an error that could cause a duplicate paid submission
- the result violates a forbidden product fact
- the same defect repeats twice without a new hypothesis

After stopping, classify the issue, preserve evidence, and return to the appropriate owner: runtime/code, prompt/package, or provider/model.

## First Sample Decision Gate

The first real sample may begin only when all of the following are recorded:

```yaml
runtime_ready: true
schema_aligned: true
product_input_selected: true
truth_facts_recorded: true
acceptance_criteria_recorded: true
provider_and_model_recorded: true
paid_boundary_reviewed: true
human_reviewer_available: true
```

This protocol does not authorize paid generation by itself. The final image and video submission controls remain the human decision point.

## Current Baseline

As of 2026-10-13:

```yaml
runtime_health: passed
database_schema: e5f6a7b8c901
frontend: 5173
backend: 8000
director_studio: reachable
real_sample_execution: not_started
```
