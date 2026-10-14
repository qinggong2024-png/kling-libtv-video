from __future__ import annotations

import hashlib
import uuid
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi import HTTPException
from libtv_agent.creative.brand_dna import project_brand_dna, validate_brand_dna
from libtv_agent.creative.director_analysis import (
    build_director_analysis,
    select_director_direction,
    validate_director_analysis,
)
from libtv_agent.creative.reality_evidence import registry_evidence_rules
from libtv_agent.creative.text_contract import (
    freeze_text_contract,
    validate_prompt_preservation,
    validate_text_contract,
)
from libtv_agent.creative.visual_plan import (
    ScriptBeat,
    VisualPlan,
    storyboard_keyframes,
)
from libtv_agent.creative.workflow import (
    REALITY,
    UNCERTAIN,
    AssetLink,
    Authorization,
    Command,
    Iteration,
    PlanRevision,
    Review,
    Selection,
    StageAttempt,
    compile_package,
    compile_storyboard_package,
    digest,
    preservation_input,
)
from libtv_agent.domain.enums import QualityDecisionStatus
from libtv_agent.domain.models import (
    CreativeCommand,
    CreativeCreation,
    CreativePromptRegistry,
    CreativeRecord,
    CreativeTask,
    ImageGenerationBatch,
    ImageGenerationItem,
    ImageGenerationOutput,
    Product,
    ProductVersion,
    StagedUpload,
)
from libtv_agent.domain.schemas import ProductVersionCreate
from libtv_agent.services.content_catalog import get_merged_site_style_profile
from libtv_agent.services.product_versions import append_version, version_content
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession


def reject(code: str, status: int = 409, *, extra: dict | None = None) -> None:
    detail = {"code": code, "message": code}
    if extra:
        detail.update(extra)
    raise HTTPException(status, detail)


async def owned(session: AsyncSession, task_id: uuid.UUID, owner_id: uuid.UUID) -> CreativeTask:
    task = await session.scalar(select(CreativeTask).join(Product).where(
        CreativeTask.id == task_id, CreativeTask.user_id == owner_id, Product.user_id == owner_id,
    ))
    if task is None:
        reject("TASK_NOT_FOUND", 404)
    return task


def record(session: AsyncSession, task_id: uuid.UUID, kind: str, key: str, payload: dict) -> None:
    session.add(CreativeRecord(
        task_id=task_id, kind=kind, record_key=key, content_hash=digest(payload),
        payload_json=deepcopy(payload),
    ))


def facts_snapshot(snapshot: dict) -> dict:
    """Add the task's canonical source hash to the immutable product facts."""
    facts = deepcopy(snapshot["product_version"])
    facts["source_hash"] = snapshot["asset"]["sha256"]
    return facts


def registry_snapshot(task_id: uuid.UUID, plan: dict, package: dict) -> dict:
    purpose = package.get("purpose", "FIRST_FRAME").lower().replace("_", "-")
    prompt_key = f"creative.fake.{purpose}:{task_id}:{package['shot_id']}"
    manifest = {
        "ruleset": package["ruleset"],
        "reality_order": list(REALITY),
        "preservation": "canonical-product-prompt-and-reality",
    }
    evidence_rules = registry_evidence_rules(package["reality"])
    if evidence_rules is not None:
        manifest["reality_evidence_rules"] = evidence_rules
    payload = {
        "schema_version": "creative-prompt.v1",
        "ruleset_version": package["ruleset"],
        "model": "fake-image",
        "input_hash": digest(plan),
        "output_hash": digest(package["prompt"]),
        "content_hash": digest(package["prompt"]),
        "activation_status": "ACTIVE",
        "package_id": package["package_id"],
        "prompt": package["prompt"],
        "manifest": manifest,
        "manifest_hash": digest(manifest),
    }
    return {
        "prompt_key": prompt_key,
        "version": package["revision"],
        "content_hash": digest(package["prompt"]),
        "payload_json": payload,
    }


def freeze_package_contract(
    session: AsyncSession,
    task_id: uuid.UUID,
    snapshot: dict,
    package: dict,
) -> dict:
    facts = deepcopy(snapshot.get("facts_snapshot") or facts_snapshot(snapshot))
    semantics = validate_prompt_preservation(
        package["prompt"], package["reality"], snapshot["plan"].get("locks", {}),
    )
    if semantics["status"] == "repair_required":
        reject("PROMPT_PRESERVATION_REPAIR_REQUIRED", extra={"prompt_preflight": semantics})
    registry = registry_snapshot(task_id, snapshot["plan"], package)
    frozen = freeze_text_contract(snapshot["plan"], package, registry, facts)
    snapshot["facts_snapshot"] = facts
    snapshot.setdefault("package_contracts", {})[package["package_id"]] = {
        "registry_snapshot": registry,
        "text_contract": frozen,
    }
    # Keep the legacy pointers for FIRST_FRAME callers and old snapshots.
    snapshot["registry_snapshot"] = registry
    snapshot["text_contract"] = frozen
    record(session, task_id, "text_contract", package["package_id"], frozen)
    session.add(CreativePromptRegistry(
        prompt_key=registry["prompt_key"],
        version=registry["version"],
        content_hash=registry["content_hash"],
        payload_json=registry["payload_json"],
    ))
    return frozen


def validate_package_contract(snapshot: dict, package: dict, command_key: str) -> dict:
    stored = snapshot.get("package_contracts", {}).get(package["package_id"], {})
    if package.get("purpose", "FIRST_FRAME") == "FIRST_FRAME":
        frozen = snapshot.get("text_contract")
        registry = snapshot.get("registry_snapshot", {})
    else:
        frozen = stored.get("text_contract")
        registry = stored.get("registry_snapshot", {})
    if not isinstance(frozen, dict):
        reject("TEXT_CONTRACT_MISSING")
    result = validate_text_contract(
        snapshot.get("plan", {}),
        package,
        frozen,
        registry,
        snapshot.get("facts_snapshot", {}),
    )
    if not result["valid"]:
        reject(
            "TEXT_CONTRACT_REJECTED",
            extra={
                "contract_status": result["status"],
                "contract_failures": result["failures"],
                "contract_unverified": result["unverified"],
            },
        )
    snapshot["text_contract_validation"] = {
        "command_key": command_key,
        "package_id": package["package_id"],
        "contract_hash": frozen["contract_hash"],
        "status": result["status"],
        "valid": result["valid"],
        "failures": result["failures"],
        "unverified": result["unverified"],
    }
    return result


def director_analysis(snapshot: dict):
    analysis = snapshot.get("director_analysis")
    if not isinstance(analysis, dict):
        reject("DIRECTOR_ANALYSIS_REQUIRED")
    try:
        validated = validate_director_analysis(
            analysis,
            selected_direction=(snapshot.get("plan") or {}).get("selected_direction"),
        )
        plan = snapshot.get("plan") or {}
        if (
            snapshot.get("director_analysis_hash") != digest(analysis)
            or validated.source_hash != snapshot["asset"]["sha256"]
            or validated.source_hash != plan.get("source_hash")
            or validated.facts_revision != snapshot["product_version"]["facts_revision"]
            or validated.facts_revision != plan.get("facts_revision")
            or validated.directions_hash != digest(plan.get("directions", []))
            or validated.direction_ids != tuple(
                direction["id"] for direction in plan.get("directions", [])
            )
            or validated.selected_direction != plan.get("selected_direction")
        ):
            reject("DIRECTOR_ANALYSIS_INVALID")
        return validated
    except (ValueError, KeyError, TypeError):
        reject("DIRECTOR_ANALYSIS_INVALID")


def storyboard_state(snapshot: dict) -> dict:
    state = snapshot.setdefault("storyboard", {
        "packages": {},
        "candidates": [],
        "selections": {},
        "shot_mappings": {},
    })
    state.setdefault("packages", {})
    state.setdefault("candidates", [])
    state.setdefault("selections", {})
    state.setdefault("shot_mappings", {})
    state.setdefault("latest_reviews", {})
    return state


def storyboard_candidates(snapshot: dict, shot_id: str | None = None) -> list[dict]:
    values = storyboard_state(snapshot)["candidates"]
    return [value for value in values if shot_id is None or value["shot_id"] == shot_id]


def storyboard_candidate(snapshot: dict, candidate_id: str | None) -> dict:
    for value in storyboard_candidates(snapshot):
        if value["candidate_id"] == candidate_id:
            return value
    reject("CANDIDATE_NOT_FOUND")


def selected_first_frame(snapshot: dict) -> dict:
    selection = snapshot.get("selection")
    if not selection or selection.get("shot_id") != "FIRST_FRAME":
        reject("FIRST_FRAME_SELECTION_REQUIRED")
    output = candidate(snapshot, selection.get("candidate_id"))
    if (
        output.get("shot_id") != "FIRST_FRAME"
        or not output.get("qualified")
        or output.get("package_id") != snapshot.get("package", {}).get("package_id")
        or not output.get("synthetic")
    ):
        reject("FIRST_FRAME_SELECTION_INVALID")
    return output


def validate_storyboard_shot(shot_id: str | None, snapshot: dict) -> str:
    if snapshot["plan"].get("script_beats") is not None:
        allowed = storyboard_keyframes(
            VisualPlan.model_validate(snapshot["package"]["visual_plan"]),
        )
    else:
        allowed = {"SHOT_01": "K01"}
    if shot_id not in allowed:
        reject("SHOT_ID_UNSUPPORTED", 422)
    return shot_id


async def script_product_references(
    session: AsyncSession, task: CreativeTask, snapshot: dict, beats: list[dict], object_store,
) -> tuple[dict[str, str], dict[str, dict[str, str]]]:
    """Resolve declared product views from registered, owner-scoped original uploads."""
    sources = snapshot["product_version"].get("truth_fields", {}).get("product_view_uploads", {})
    registered = snapshot["product_version"].get("source_asset_references", [])
    views = {
        m.garment_view for raw in beats for m in ScriptBeat.model_validate(raw).moments
    } - {"front"}
    evidence, assets = {}, {}
    for view in sorted(views):
        try:
            upload_id = uuid.UUID(sources[view])
        except (KeyError, ValueError, TypeError):
            reject("PRODUCT_VIEW_EVIDENCE_REQUIRED")
        upload = await session.scalar(select(StagedUpload).where(
            StagedUpload.id == upload_id, StagedUpload.user_id == task.user_id,
            StagedUpload.source_image_output_id.is_(None),
        ).execution_options(populate_existing=True))
        if upload is None or upload.object_key not in registered:
            reject("PRODUCT_VIEW_EVIDENCE_REQUIRED")
        with TemporaryDirectory(prefix="creative-product-view-") as directory:
            if not await object_store.exists(upload.object_key):
                reject("ASSET_MISSING")
            path = await object_store.localize(upload.object_key, Path(directory) / view)
            if hashlib.sha256(path.read_bytes()).hexdigest() != upload.sha256:
                reject("ASSET_HASH_MISMATCH")
        evidence[view] = upload.sha256
        assets[view] = {
            "upload_id": str(upload.id), "object_key": upload.object_key, "sha256": upload.sha256,
        }
    return evidence, assets


def storyboard_package(
    session: AsyncSession,
    task: CreativeTask,
    snapshot: dict,
    shot_id: str,
) -> dict:
    state = storyboard_state(snapshot)
    package = state["packages"].get(shot_id)
    if package is not None:
        if package["parent_package_id"] != snapshot["package"]["package_id"]:
            reject("STORYBOARD_PACKAGE_STALE")
        return package
    first = selected_first_frame(snapshot)
    model = compile_storyboard_package(
        task.id, snapshot["plan"], snapshot["package"], first["candidate_id"], shot_id,
    )
    package = model.model_dump(mode="json")
    state["packages"][shot_id] = package
    freeze_package_contract(session, task.id, snapshot, package)
    record(session, task.id, "package", package["package_id"], package)
    return package


async def create_task(
    session: AsyncSession, owner_id: uuid.UUID, product_id: uuid.UUID, asset: AssetLink,
    *, client_key: str | None = None, product_version_id: uuid.UUID | None = None,
    brand_profile_id: str | None = None, brand_profile_version: str | None = None,
) -> dict:
    product = await session.scalar(select(Product).where(
        Product.id == product_id, Product.user_id == owner_id,
    ))
    if product is None:
        reject("PRODUCT_NOT_FOUND", 404)
    if asset.owner_id != owner_id:
        reject("OWNER_MISMATCH")
    request_input = {
        "product_id": str(product_id), "front_sha": asset.sha256,
        "product_version_id": str(product_version_id) if product_version_id else None,
        "settings": {"mode": "OFFLINE_FAKE_ONLY", "role": asset.role, "view": asset.view},
    }
    if brand_profile_id is not None:
        request_input["brand_profile_id"] = brand_profile_id
        request_input["brand_profile_version"] = brand_profile_version
    elif brand_profile_version is not None:
        reject("BRAND_PROFILE_ID_REQUIRED", 422)
    request_hash = digest(request_input)
    if client_key:
        prior = await session.scalar(select(CreativeCreation).where(
            CreativeCreation.user_id == owner_id, CreativeCreation.client_key == client_key,
        ))
        if prior:
            if prior.request_hash != request_hash:
                reject("TASK_IDEMPOTENCY_CONFLICT")
            await owned(session, prior.task_id, owner_id)
            return prior.result_json
    brand_dna = None
    if brand_profile_id is not None:
        try:
            profile = await get_merged_site_style_profile(
                session, brand_profile_id, require_active=True,
            )
        except ValueError:
            reject("BRAND_PROFILE_UNAVAILABLE", 422)
        if profile.library_scope != "brand":
            reject("BRAND_PROFILE_REQUIRED", 422)
        if brand_profile_version is not None and profile.version != brand_profile_version:
            reject("BRAND_PROFILE_STALE")
        brand_dna = project_brand_dna(profile)
    if product_version_id:
        version = await session.scalar(select(ProductVersion).join(Product).where(
            ProductVersion.id == product_version_id, ProductVersion.product_id == product_id,
            Product.user_id == owner_id,
        ))
        if version is None:
            reject("PRODUCT_VERSION_NOT_FOUND", 404)
    else:
        version = await append_version(session, product_id, ProductVersionCreate(
            source_type="USER_UPLOAD", source_asset_references=[asset.object_key],
            product_page_url=None, client_request_key=f"creative:{asset.sha256}",
        ))
    facts = version_content(version)
    task = CreativeTask(
        id=uuid.uuid4(), user_id=owner_id, product_id=product_id,
        status="DRAFT", state_version=0,
        snapshot_json={
            "asset": asset.model_dump(mode="json"), "trace": ["G0"], "candidates": [],
            "calls": 0, "cost_micros": 0, "total_calls": 0, "total_cost_micros": 0,
            "stopped": False, "product_version": facts,
            **({"brand_dna": brand_dna} if brand_dna is not None else {}),
            "storyboard": {
                "packages": {}, "candidates": [], "selections": {}, "shot_mappings": {},
            },
        },
    )
    session.add(task)
    await session.flush()
    record(session, task.id, "asset_link", "canonical-front", asset.model_dump(mode="json"))
    result = {"id": str(task.id), "status": task.status, "state_version": 0}
    if client_key:
        session.add(CreativeCreation(
            user_id=owner_id, client_key=client_key, task_id=task.id,
            request_hash=request_hash,
            result_json=result,
        ))
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        if client_key:
            prior = await session.scalar(select(CreativeCreation).where(
                CreativeCreation.user_id == owner_id,
                CreativeCreation.client_key == client_key,
            ))
            if prior and prior.request_hash == request_hash:
                await owned(session, prior.task_id, owner_id)
                return prior.result_json
            if prior:
                reject("TASK_IDEMPOTENCY_CONFLICT")
        raise
    return result


async def validate_asset(snapshot: dict, object_store) -> None:
    asset = AssetLink.model_validate(snapshot["asset"])
    if asset.revoked:
        reject("ASSET_REVOKED")
    if not await object_store.exists(asset.object_key):
        reject("ASSET_MISSING")
    with TemporaryDirectory(prefix="cw-materialize-") as directory:
        path = await object_store.localize(asset.object_key, Path(directory) / "front")
        if hashlib.sha256(path.read_bytes()).hexdigest() != asset.sha256:
            reject("ASSET_HASH_MISMATCH")


async def validate_product_version(
    session: AsyncSession, task: CreativeTask, snapshot: dict,
) -> None:
    product_snapshot = snapshot.get("product_version")
    if not product_snapshot:
        reject("PRODUCT_VERSION_REQUIRED")
    current = await session.scalar(select(ProductVersion).where(
        ProductVersion.product_id == task.product_id,
    ).order_by(ProductVersion.version_number.desc()))
    if current is None or digest(version_content(current)) != digest(product_snapshot):
        reject("PRODUCT_VERSION_STALE")
    if current.status.value == "BLOCKED":
        reject("PRODUCT_VERSION_BLOCKED")


def candidate(snapshot: dict, candidate_id: str | None) -> dict:
    for value in snapshot["candidates"]:
        if value["candidate_id"] == candidate_id:
            return value
    reject("CANDIDATE_NOT_FOUND")


def authorization(
    snapshot: dict, now: datetime, *, scope: str = "FIRST_FRAME", shot_id: str | None = None,
) -> Authorization:
    if snapshot.get("stopped"):
        reject("USER_STOPPED")
    if not snapshot.get("authorization"):
        reject("AUTHORIZATION_REQUIRED")
    auth = Authorization.model_validate(snapshot["authorization"])
    if auth.expires_at <= now:
        reject("AUTH_EXPIRED")
    if auth.scope != scope:
        reject("AUTHORIZATION_SCOPE_INVALID")
    if scope == "VIDEO_STORYBOARD" and auth.shot_ids != [shot_id]:
        reject("SHOT_NOT_AUTHORIZED")
    package = (
        storyboard_state(snapshot)["packages"].get(shot_id)
        if scope == "VIDEO_STORYBOARD"
        else snapshot.get("package")
    )
    if not package or (scope == "VIDEO_STORYBOARD" and auth.package_id != package["package_id"]):
        reject("PACKAGE_MISMATCH")
    if auth.locks_hash != package["locks_hash"]:
        reject("LOCK_CONFLICT")
    if snapshot.get("total_cost_micros", 0) > snapshot.get("task_cap_micros", auth.max_cost_micros):
        reject("TASK_BUDGET_EXHAUSTED")
    return auth


async def execute(
    session: AsyncSession, task: CreativeTask, command: Command, object_store, owner_id: uuid.UUID,
) -> dict:
    task = await owned(session, task.id, owner_id)
    fingerprint = digest(command.model_dump(mode="json"))
    prior = await session.scalar(select(CreativeCommand).where(
        CreativeCommand.task_id == task.id, CreativeCommand.command_key == command.command_key,
    ))
    if prior:
        if prior.request_hash != fingerprint:
            reject("IDEMPOTENCY_CONFLICT")
        return prior.result_json
    if command.expected_version != task.state_version:
        reject("STALE_VERSION")
    # CAS locks the root for all scope/budget changes, including concurrent workers.
    changed = await session.execute(update(CreativeTask).where(
        CreativeTask.id == task.id, CreativeTask.state_version == command.expected_version,
    ).values(state_version=command.expected_version + 1))
    if changed.rowcount != 1:
        reject("STALE_VERSION")
    snapshot = deepcopy(task.snapshot_json)
    stage = task.status
    now = datetime.now(UTC)
    action = command.action
    if snapshot.get("execution_state") in UNCERTAIN and action not in {
        "reconcile", "stop", "revoke_asset",
    }:
        reject("EXECUTION_UNKNOWN")
    if snapshot.get("stopped") and action not in {"stop", "revoke_asset", "reconcile"}:
        reject("USER_STOPPED")
    if action not in {"stop", "revoke_asset", "reconcile"}:
        await validate_asset(snapshot, object_store)
        await validate_product_version(session, task, snapshot)
    if action in {"analyze", "retry_analysis"}:
        if stage not in {"DRAFT", "ANALYSIS_FAILED"}:
            reject("STAGE_INVALID")
        facts_revision = snapshot["product_version"]["facts_revision"]
        brand = snapshot.get("brand_dna")
        if brand is not None and not validate_brand_dna(brand):
            reject("BRAND_DNA_HASH_MISMATCH")
        environments = (brand or {}).get("sceneDNA", {}).get("preferredEnvironment", [])
        default_scenes = ["plain studio", "indoor room", "outdoor walkway"]
        scenes = [
            environments[index] if index < len(environments) else default
            for index, default in enumerate(default_scenes)
        ]
        plan = PlanRevision(
            revision=1, facts_revision=facts_revision, product_id=task.product_id,
            source_hash=snapshot["asset"]["sha256"],
            product_version_id=uuid.UUID(snapshot["product_version"]["product_version_id"]),
            facts_snapshot_hash=digest(facts_snapshot(snapshot)),
            directions=[
                {"id": "A", "scene": scenes[0], "behavior": "standing still"},
                {"id": "B", "scene": scenes[1], "behavior": "seated casually"},
                {"id": "C", "scene": scenes[2], "behavior": "walking slowly"},
            ],
            brand_dna=deepcopy(brand),
            claims=[{
                "claim_id": "front-source", "value": "front image available",
                "source_fact_keys": ["source_asset_references"],
                "facts_revision": facts_revision, "evidence_kind": "OBSERVED_REFERENCE",
                "confidence_basis": "asset_sha256_and_source_fact",
                "unknown_or_assumption": "back view not observed",
            }],
        )
        analysis = build_director_analysis(
            source_hash=snapshot["asset"]["sha256"],
            facts_revision=facts_revision,
            directions=plan.directions,
            brand_selected=brand is not None,
        )
        snapshot["plan"] = plan.model_dump(mode="json")
        snapshot["director_analysis"] = analysis.model_dump(mode="json")
        snapshot["director_analysis_hash"] = digest(snapshot["director_analysis"])
        snapshot.pop("analysis_failure", None)
        snapshot["trace"].extend(["D1", "D2"])
        stage = "AWAITING_DIRECTION"
        record(session, task.id, "plan", "1", snapshot["plan"])
        record(session, task.id, "director_analysis", "1", snapshot["director_analysis"])
    elif action == "select_direction":
        if stage != "AWAITING_DIRECTION" or command.direction_id is None:
            reject("DIRECTION_REQUIRED")
        analysis = director_analysis(snapshot)
        try:
            selected_analysis = select_director_direction(analysis, command.direction_id)
        except ValueError:
            reject("DIRECTION_REQUIRED")
        locks = {
            "product_id": str(task.product_id),
            "source_hash": snapshot["asset"]["sha256"],
            "user_locks": {
                "selected_direction": command.direction_id,
                "shot_id": "FIRST_FRAME",
            },
        }
        snapshot["plan"].update(
            selected_direction=command.direction_id,
            revision=2,
            locks=locks,
        )
        if command.script_beats is not None:
            if not 1 <= len(command.script_beats) <= 32:
                reject("SCRIPT_BEATS_INVALID", 422)
            beats = [
                ScriptBeat.model_validate(b).model_dump(mode="json") for b in command.script_beats
            ]
            views, assets = await script_product_references(
                session, task, snapshot, beats, object_store,
            )
            snapshot["plan"].update(
                script_beats=beats, product_view_evidence=views, product_reference_assets=assets,
                duration_seconds=sum(b["duration_seconds"] for b in beats),
            )
        snapshot["director_analysis"] = selected_analysis.model_dump(mode="json")
        snapshot["director_analysis_hash"] = digest(snapshot["director_analysis"])
        package = compile_package(task.id, snapshot["plan"], digest(locks), 1)
        snapshot["package"] = package.model_dump(mode="json")
        freeze_package_contract(session, task.id, snapshot, snapshot["package"])
        snapshot["trace"].extend(["D3", "D4"])
        stage = "PLAN_READY"
        record(session, task.id, "plan", "2", snapshot["plan"])
        record(session, task.id, "director_analysis", "2", snapshot["director_analysis"])
        record(session, task.id, "package", package.package_id, snapshot["package"])
    elif action == "authorize":
        if (
            stage not in {"PLAN_READY", "IMAGE_REVIEW", "STORYBOARD_REVIEW"}
            or command.authorization is None
        ):
            reject("AUTHORIZATION_REQUIRED")
        if snapshot.get("stopped"):
            reject("USER_STOPPED")
        director_analysis(snapshot)
        auth = command.authorization
        if stage == "STORYBOARD_REVIEW" and auth.scope == "FIRST_FRAME":
            reject("AUTHORIZATION_SCOPE_INVALID")
        if auth.expires_at <= now:
            reject("AUTHORIZATION_SCOPE_INVALID")
        package = snapshot["package"]
        if auth.scope == "FIRST_FRAME":
            if (
                auth.package_id != package["package_id"]
                or auth.locks_hash != package["locks_hash"]
                or auth.shot_ids != ["FIRST_FRAME"]
            ):
                reject("AUTHORIZATION_SCOPE_INVALID")
        else:
            shot_id = validate_storyboard_shot(auth.shot_ids[0], snapshot)
            selected_first_frame(snapshot)
            if auth.locks_hash != package["locks_hash"]:
                reject("AUTHORIZATION_SCOPE_INVALID")
            if auth.package_id not in {
                package["package_id"],
                f"{task.id}:storyboard:{shot_id}:1",
            }:
                reject("AUTHORIZATION_SCOPE_INVALID")
            package = storyboard_package(session, task, snapshot, shot_id)
            auth = auth.model_copy(update={"package_id": package["package_id"]})
        if snapshot.get("execution_state") in UNCERTAIN:
            reject("EXECUTION_UNKNOWN")
        if auth.parent_authorization_id and auth.parent_authorization_id == auth.authorization_id:
            reject("AUTHORIZATION_CHAIN_INVALID")
        prior_auth = snapshot.get("authorization")
        if prior_auth and auth.parent_authorization_id != prior_auth["authorization_id"]:
            reject("AUTHORIZATION_CHAIN_INVALID")
        prior_revision = snapshot.get("authorized_revision")
        if prior_auth and prior_revision != package["revision"] and (
            auth.parent_authorization_id != prior_auth["authorization_id"]
        ):
            reject("AUTHORIZATION_CHAIN_REQUIRED")
        prior_cap = snapshot.get("task_cap_micros")
        new_cap = (
            auth.total_task_cap_micros
            if auth.total_task_cap_micros is not None
            else auth.max_cost_micros
        )
        if prior_cap is not None and new_cap < prior_cap:
            reject("TASK_BUDGET_CANNOT_SHRINK")
        snapshot.update(
            authorization=auth.model_dump(mode="json"),
            calls=0, cost_micros=0,
            stopped=False, authorized_revision=package["revision"],
        )
        snapshot["task_cap_micros"] = max(prior_cap if prior_cap is not None else 0, new_cap)
        snapshot["trace"].append("H1")
        record(session, task.id, "authorization", auth.authorization_id, snapshot["authorization"])
    elif action in {"generate", "revise"}:
        director_analysis(snapshot)
        storyboard_mode = snapshot.get("authorization", {}).get("scope") == "VIDEO_STORYBOARD"
        if storyboard_mode and action == "revise":
            reject("STORYBOARD_REVISION_NOT_SUPPORTED")
        if storyboard_mode and stage not in {"IMAGE_REVIEW", "STORYBOARD_REVIEW"}:
            reject("STAGE_INVALID")
        if not storyboard_mode and stage not in {"PLAN_READY", "IMAGE_REVIEW"}:
            reject("STAGE_INVALID")
        shot_id = snapshot["authorization"]["shot_ids"][0] if storyboard_mode else "FIRST_FRAME"
        if storyboard_mode and command.shot_id not in {None, shot_id}:
            reject("SHOT_ID_MISMATCH")
        package = (
            storyboard_state(snapshot)["packages"].get(shot_id)
            if storyboard_mode else snapshot["package"]
        )
        if package is None:
            reject("STORYBOARD_PACKAGE_REQUIRED")
        if command.package_id != package["package_id"]:
            reject("PACKAGE_MISMATCH")
        validate_package_contract(snapshot, package, command.command_key)
        auth_scope = "VIDEO_STORYBOARD" if storyboard_mode else "FIRST_FRAME"
        auth = authorization(snapshot, now, scope=auth_scope, shot_id=shot_id)
        # D4 already froze these exact decisions. Reconstructing defaults here
        # discards camera intent and breaks historical/new rule compatibility.
        decisions = tuple(item["decision"] for item in package["reality"])
        expected_preservation = preservation_input(
            snapshot["plan"], package["locks_hash"], package["prompt"], decisions,
        )
        if storyboard_mode:
            expected_preservation.update({
                "first_frame_candidate_id": selected_first_frame(snapshot)["candidate_id"],
                "shot_id": shot_id,
            })
        if package["preservation_hash"] != digest(expected_preservation):
            reject("PROMPT_PRESERVATION_FAILED")
        parent = None
        index = 0
        if action == "revise":
            parent = candidate(snapshot, command.candidate_id)
            if (parent.get("qualified")
                    or parent["candidate_id"] != snapshot["candidates"][-1]["candidate_id"]):
                reject("REVISION_PARENT_INVALID")
            index = parent["revision_index"] + 1
            if not auth.loop_enabled:
                reject("LOOP_NOT_AUTHORIZED")
            if index > auth.max_revisions:
                reject("LIMIT_REACHED")
            if index >= 2 and parent.get("fix") == command.fix:
                reject("NO_PROGRESS")
            if (not command.fix or not command.failure_region or not command.changed_modules
                    or not set(command.changed_modules) <= set(auth.allowed_modules)):
                reject("REVISION_EVIDENCE_OR_MODULE_INVALID")
        elif any(
            value["authorization_id"] == auth.authorization_id
            for value in (
                storyboard_candidates(snapshot, shot_id)
                if storyboard_mode else snapshot["candidates"]
            )
        ):
            reject("EXISTING_CANDIDATE_RECOVERY")
        # Synthetic cost 1 for media plus 1 for Fake critic. Real price/ledger are untouched.
        cost = 2
        if snapshot["calls"] + 2 > auth.max_calls:
            reject("CALL_LIMIT")
        if snapshot["cost_micros"] + cost > auth.max_cost_micros:
            reject("BUDGET_EXHAUSTED")
        task_cap = (
            auth.total_task_cap_micros
            if auth.total_task_cap_micros is not None
            else auth.max_cost_micros
        )
        if snapshot["total_cost_micros"] + cost > task_cap:
            reject("TASK_BUDGET_EXHAUSTED")
        if action == "revise":
            package_model = compile_package(
                task.id, snapshot["plan"], package["locks_hash"], package["revision"] + 1,
                package["package_id"], command.fix,
                inherited_reality=package["reality"],
            )
            snapshot["package"] = package_model.model_dump(mode="json")
            package = snapshot["package"]
            freeze_package_contract(session, task.id, snapshot, package)
            validate_package_contract(snapshot, package, command.command_key)
            record(session, task.id, "package", package["package_id"], package)
            snapshot["trace"].extend(["D3", "D4"])
        snapshot["calls"] += 2
        snapshot["cost_micros"] += cost
        snapshot["total_calls"] += 2
        snapshot["total_cost_micros"] += cost
        snapshot["trace"].extend(
            ["STORYBOARD_E1", "STORYBOARD_E2"] if storyboard_mode else ["E1", "E2"]
        )
        candidate_id = f"fake:{task.id}:{command.command_key}"
        attempt = StageAttempt(
            attempt_id=candidate_id,
            scope=auth_scope,
            shot_id=shot_id,
            package_id=package["package_id"],
            authorization_id=auth.authorization_id, input_hash=digest(package),
            status=command.fake_outcome, reserved_cost_micros=cost,
            actual_cost_micros=cost if command.fake_outcome == "SUCCEEDED" else None,
            output_hash=(
                snapshot["asset"]["sha256"] if command.fake_outcome == "SUCCEEDED" else None
            ),
        )
        snapshot["execution_state"] = command.fake_outcome
        record(session, task.id, "attempt", candidate_id, attempt.model_dump(mode="json"))
        if command.fake_outcome in UNCERTAIN:
            snapshot["uncertain_attempt"] = attempt.model_dump(mode="json")
            snapshot["uncertain_scope"] = auth_scope
            snapshot["uncertain_shot_id"] = shot_id
            snapshot["stop_reason"] = "EXECUTION_UNKNOWN"
            stage = "ACTION_REQUIRED"
        else:
            source_hash = snapshot["asset"]["sha256"]
            product_version_id = snapshot["product_version"]["product_version_id"]
            package_revision = package["revision"]
            provenance = {
                "creativeTaskId": str(task.id),
                "packageId": package["package_id"],
                "packageRevision": package_revision,
                "productVersionId": product_version_id,
                "sourceHash": source_hash,
                "purpose": auth_scope,
                "shotId": shot_id,
                "synthetic": True,
                "qualificationScope": "OFFLINE_SYNTHETIC_ONLY",
            }
            batch = ImageGenerationBatch(
                user_id=owner_id, client_batch_id=candidate_id + ":batch",
                idempotency_key=candidate_id, request_hash=digest(package),
                name="creative-offline-fake", provider="fake",
                status="COMPLETED", expected_generation_count=1,
                paid_submission_consent_at=now,
                request_json=provenance,
            )
            item = ImageGenerationItem(
                order_no=1, client_task_id=candidate_id + ":item",
                outfit_id=str(task.product_id), outfit_name="creative product",
                sku="", kind=(
                    "CREATIVE_STORYBOARD" if storyboard_mode else "CREATIVE_FIRST_FRAME"
                ), view="front", label=shot_id,
                prompt=package["prompt"], model_id="fake-image", status="COMPLETED",
                provider_task_id=candidate_id, request_json=provenance,
            )
            item.outputs.append(ImageGenerationOutput(
                order_no=1, remote_url=f"fake://{candidate_id}",
                object_key=snapshot["asset"]["object_key"],
                content_type="image/png", sha256=source_hash,
                qualification_status=QualityDecisionStatus.PENDING,
                quality_gates_json={
                    "synthetic": True,
                    "qualification": "OFFLINE_SYNTHETIC_ONLY",
                    "qualificationScope": "OFFLINE_SYNTHETIC_ONLY",
                    "qualified": False,
                    "deliverableEligible": False,
                    "packageRevision": package_revision,
                    "productVersionId": product_version_id,
                    "sourceHash": source_hash,
                },
            ))
            batch.items.append(item)
            session.add(batch)
            await session.flush()
            output = {
                "candidate_id": candidate_id, "package_id": package["package_id"],
                "authorization_id": auth.authorization_id, "purpose": auth_scope,
                "shot_id": shot_id,
                "batch_id": candidate_id + ":batch", "item_id": candidate_id + ":item",
                "output_id": candidate_id + ":output", "synthetic": True,
                "revision_index": index, "qualified": False,
                "parent_candidate_id": parent["candidate_id"] if parent else None,
                "fix": command.fix, "failure_region": command.failure_region,
                "sha256": snapshot["asset"]["sha256"],
                "object_key": snapshot["asset"]["object_key"],
                "media_evidence": "CANONICAL_COPY_PLACEHOLDER_NOT_GENERATED",
            }
            if storyboard_mode:
                state = storyboard_state(snapshot)
                state["candidates"].append(output)
                state["shot_mappings"][shot_id] = {
                    key: output[key]
                    for key in ("candidate_id", "package_id", "batch_id", "item_id", "output_id")
                }
            else:
                snapshot["candidates"].append(output)
            output["batch_id"] = str(batch.id)
            output["item_id"] = str(item.id)
            output["output_id"] = str(item.outputs[0].id)
            if storyboard_mode:
                state["shot_mappings"][shot_id].update({
                    "batch_id": output["batch_id"],
                    "item_id": output["item_id"],
                    "output_id": output["output_id"],
                })
            snapshot["stop_reason"] = "UNVERIFIED_PIXELS"
            review = Review(
                candidate_id=candidate_id, scope=auth_scope, shot_id=shot_id,
                reviewer_kind="FAKE_CRITIC", decision="UNVERIFIED",
                axes={axis: "unverified" for axis in (
                    "product_fidelity", "human_capture", "spatial_light_integration",
                    "ad_goal_visibility",
                )},
            )
            snapshot["trace"].append("E3")
            record(
                session, task.id, "review", candidate_id + ":fake", review.model_dump(mode="json"),
            )
            iteration = Iteration(
                loop_id=auth.authorization_id, index=index, candidate_id=candidate_id,
                parent_candidate_id=output["parent_candidate_id"], package_id=package["package_id"],
                changed_modules=command.changed_modules, stop_reason="UNVERIFIED_PIXELS",
            )
            record(session, task.id, "iteration", candidate_id, iteration.model_dump(mode="json"))
            stage = "STORYBOARD_REVIEW" if storyboard_mode else "IMAGE_REVIEW"
    elif action == "review":
        story = storyboard_state(snapshot)
        output = (
            storyboard_candidate(snapshot, command.candidate_id)
            if command.candidate_id in {
                value["candidate_id"] for value in story["candidates"]
            } else candidate(snapshot, command.candidate_id)
        )
        is_storyboard = output.get("purpose") == "VIDEO_STORYBOARD"
        if command.shot_id is not None and command.shot_id != output["shot_id"]:
            reject("SHOT_ID_MISMATCH")
        expected_stage = "STORYBOARD_REVIEW" if is_storyboard else "IMAGE_REVIEW"
        if stage != expected_stage or command.decision is None:
            reject("REVIEW_STAGE_INVALID")
        output["qualified"] = command.decision == "QUALIFIED"
        review = Review(
            candidate_id=output["candidate_id"], reviewer_kind="HUMAN",
            scope=output.get("purpose", "FIRST_FRAME"),
            shot_id=output["shot_id"],
            reviewer_id=owner_id, decision=command.decision, reason=command.reason,
        )
        review_payload = review.model_dump(mode="json")
        record(session, task.id, "review", command.command_key, review_payload)
        if is_storyboard:
            story["latest_reviews"][output["shot_id"]] = review_payload
            if story["selections"].get(output["shot_id"], {}).get(
                "candidate_id"
            ) == output["candidate_id"]:
                story["selections"].pop(output["shot_id"], None)
        else:
            snapshot["latest_review"] = review_payload
            if snapshot.get("selection", {}).get("candidate_id") == output["candidate_id"]:
                snapshot.pop("selection", None)
    elif action == "select":
        story = storyboard_state(snapshot)
        output = (
            storyboard_candidate(snapshot, command.candidate_id)
            if command.candidate_id in {
                value["candidate_id"] for value in story["candidates"]
            } else candidate(snapshot, command.candidate_id)
        )
        is_storyboard = output.get("purpose") == "VIDEO_STORYBOARD"
        if command.shot_id is not None and command.shot_id != output["shot_id"]:
            reject("SHOT_ID_MISMATCH")
        expected_stage = "STORYBOARD_REVIEW" if is_storyboard else "IMAGE_REVIEW"
        if stage != expected_stage:
            reject("STAGE_INVALID")
        if not output["qualified"]:
            reject("HUMAN_REVIEW_REQUIRED")
        expected_package = (
            story["packages"].get(output["shot_id"])
            if is_storyboard else snapshot["package"]
        )
        if not expected_package or output["package_id"] != expected_package["package_id"]:
            reject("STALE_CANDIDATE_PACKAGE")
        selection = Selection(
            purpose=output.get("purpose", "FIRST_FRAME"),
            shot_id=output["shot_id"],
            candidate_id=output["candidate_id"], package_id=output["package_id"],
            batch_id=output["batch_id"], item_id=output["item_id"],
            output_id=output["output_id"], selected_by=owner_id,
        )
        selection_payload = selection.model_dump(mode="json")
        if is_storyboard:
            story["selections"][output["shot_id"]] = selection_payload
            story["shot_mappings"][output["shot_id"]] = selection_payload
        else:
            snapshot["selection"] = selection_payload
        record(session, task.id, "selection", command.command_key, selection_payload)
    elif action == "revoke_asset":
        if not command.reason or not command.impact_scope:
            reject("REVOCATION_EVIDENCE_REQUIRED", 422)
        snapshot["asset"]["revoked"] = True
        event = {
            "asset": snapshot["asset"], "operator_id": str(owner_id),
            "server_time": now.isoformat(), "reason": command.reason,
            "impact_scope": command.impact_scope, "state_version": command.expected_version + 1,
        }
        record(session, task.id, "asset_revocation", str(uuid.uuid4()), event)
        snapshot["asset_revocation"] = event
        snapshot.pop("selection", None)
        stage = "BLOCKED"
    elif action == "stop":
        snapshot["stopped"] = True
        snapshot["stop_reason"] = "USER_STOPPED"
        stop_event = {
            "operator_id": str(owner_id),
            "server_time": now.isoformat(),
            "reason": command.reason or "USER_STOPPED",
            "impact_scope": command.impact_scope or "new-execution",
            "command_key": command.command_key,
            "state_version": command.expected_version + 1,
        }
        snapshot["stop_event"] = stop_event
        record(session, task.id, "stop", command.command_key, stop_event)
    elif action == "reconcile":
        if snapshot.get("execution_state") not in UNCERTAIN:
            reject("NOT_UNCERTAIN")
        if not command.reconcile_not_submitted:
            reject("RECONCILIATION_REQUIRED")
        # Test-only declared reconciliation cannot be used as real provider evidence.
        old = snapshot.pop("uncertain_attempt")
        snapshot["cost_micros"] -= old["reserved_cost_micros"]
        snapshot["total_cost_micros"] -= old["reserved_cost_micros"]
        snapshot["execution_state"] = "RECONCILED_NOT_SUBMITTED"
        if not snapshot.get("stopped") and not snapshot["asset"].get("revoked"):
            snapshot["stop_reason"] = None
        old["status"] = "RECONCILED_NOT_SUBMITTED"
        record(session, task.id, "attempt", command.command_key + ":reconciliation", old)
        stage = "BLOCKED" if snapshot["asset"].get("revoked") else (
            "IMAGE_REVIEW" if snapshot["candidates"] else "PLAN_READY"
        )
    result = {
        "id": str(task.id), "status": stage, "state_version": command.expected_version + 1,
        "snapshot": snapshot, "mode": "OFFLINE_FAKE_ONLY",
    }
    await session.execute(update(CreativeTask).where(CreativeTask.id == task.id).values(
        status=stage, snapshot_json=snapshot,
    ))
    session.add(CreativeCommand(
        task_id=task.id, command_key=command.command_key,
        request_hash=fingerprint, result_json=result,
    ))
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        reject("COMMAND_CONFLICT")
    return result


async def persist_analysis_failure(
    session: AsyncSession, task_id: uuid.UUID, owner_id: uuid.UUID, expected_version: int,
    command_key: str,
) -> None:
    task = await owned(session, task_id, owner_id)
    if task.status not in {"DRAFT", "ANALYSIS_FAILED"}:
        return
    snapshot = deepcopy(task.snapshot_json)
    snapshot["analysis_failure"] = {
        "reason_code": "DIRECTOR_ANALYSIS_FAILED", "retryable": True,
        "command_key": command_key,
    }
    changed = await session.execute(
        update(CreativeTask).where(
            CreativeTask.id == task_id, CreativeTask.user_id == owner_id,
            CreativeTask.state_version == expected_version,
        ).values(
            status="ANALYSIS_FAILED", snapshot_json=snapshot,
            state_version=expected_version + 1,
        )
    )
    if changed.rowcount == 1:
        record(session, task_id, "analysis_failure", str(expected_version + 1),
               snapshot["analysis_failure"])
    await session.commit()
