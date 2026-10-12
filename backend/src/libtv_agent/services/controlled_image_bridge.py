"""Controlled bridge admission using existing Creative and production validators."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, Literal

from libtv_agent.config import Settings
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    from libtv_agent.services.creative_provider_preflight import ProviderCapabilityDeclaration
    from libtv_agent.services.creative_provider_requests import ImageProviderOptions


class ControlledImageBridgeRejected(ValueError):
    def __init__(self, code: str, status_code: int = 409) -> None:
        self.code = code
        self.status_code = status_code
        super().__init__(code)


@dataclass(frozen=True)
class ControlledImageBridgeBinding:
    options: ImageProviderOptions
    capability: ProviderCapabilityDeclaration
    approval_manifest_path: Path


@dataclass(frozen=True)
class ControlledImageBridgePolicy:
    """Trusted server configuration, never populated from an HTTP request."""

    enabled: bool = False
    bindings: Mapping[uuid.UUID, ControlledImageBridgeBinding] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "bindings", MappingProxyType(dict(self.bindings)))


class ControlledImageBridgePreflight(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["controlled-image-bridge-preflight.v1"] = (
        "controlled-image-bridge-preflight.v1"
    )
    status: Literal["READY_FOR_HUMAN_SUBMIT"] = "READY_FOR_HUMAN_SUBMIT"
    execution_mode: Literal["PREFLIGHT_ONLY"] = "PREFLIGHT_ONLY"
    creative_task_id: uuid.UUID
    state_version: int
    package_revision_id: str
    shot_id: Literal["FIRST_FRAME"] = "FIRST_FRAME"
    provider: str
    model: str
    request_hash: str
    evidence_hash: str
    preflight_hash: str
    reference_count: int
    expires_at: datetime
    actual_submitted: Literal[False] = False
    provider_submission_allowed: Literal[False] = False
    provider_capabilities_verified: Literal[False] = False
    qualification_scope: Literal["OFFLINE_SYNTHETIC_ONLY"] = "OFFLINE_SYNTHETIC_ONLY"
    deliverable_eligible: Literal[False] = False


async def preflight_controlled_image_bridge(
    session: AsyncSession,
    *,
    task_id: uuid.UUID,
    owner_id: uuid.UUID,
    expected_version: int,
    policy: ControlledImageBridgePolicy | None,
    object_store,
    settings: Settings,
) -> ControlledImageBridgePreflight:
    if not isinstance(policy, ControlledImageBridgePolicy) or policy.enabled is not True:
        raise ControlledImageBridgeRejected("CONTROLLED_BRIDGE_DISABLED", 403)
    # Preparation packages may be supplied independently. A disabled bridge
    # must not import them or prevent the existing application from starting.
    try:
        from libtv_agent.domain.models import CreativeTask
        from libtv_agent.services.creative_provider_preflight import (
            CreativeProviderPreflightRejected,
            preflight_creative_provider_request,
        )
        from libtv_agent.services.creative_provider_requests import (
            CreativeProviderRequestRejected,
            compile_creative_image_request,
        )
    except ImportError as exc:
        raise ControlledImageBridgeRejected(
            "CONTROLLED_BRIDGE_DEPENDENCIES_UNAVAILABLE", 503,
        ) from exc
    task = await session.scalar(
        select(CreativeTask).where(
            CreativeTask.id == task_id,
            CreativeTask.user_id == owner_id,
        ).execution_options(populate_existing=True)
    )
    if task is None:
        raise ControlledImageBridgeRejected("CREATIVE_TASK_NOT_FOUND", 404)
    if task.state_version != expected_version:
        raise ControlledImageBridgeRejected("STALE_VERSION")
    binding = policy.bindings.get(task_id)
    if not isinstance(binding, ControlledImageBridgeBinding):
        raise ControlledImageBridgeRejected("CONTROLLED_BRIDGE_BINDING_REQUIRED", 403)
    try:
        request = await compile_creative_image_request(
            session,
            task,
            owner_id=owner_id,
            object_store=object_store,
            options=binding.options,
        )
        # The existing validator rechecks ownership, source/package hashes,
        # approval, license, quote and quota; media must not outlive this call.
        async with await preflight_creative_provider_request(
            session,
            task,
            request,
            owner_id=owner_id,
            object_store=object_store,
            settings=settings,
            capability=binding.capability,
            approval_manifest_path=binding.approval_manifest_path,
        ) as lease:
            result = lease.result
            return ControlledImageBridgePreflight(
                creative_task_id=task.id,
                state_version=request.state_version,
                package_revision_id=result.package_revision_id,
                provider=result.provider,
                model=result.model,
                request_hash=result.request_hash,
                evidence_hash=result.evidence_hash,
                preflight_hash=result.preflight_hash,
                reference_count=len(result.materialized_inputs),
                expires_at=result.expires_at,
            )
    except (CreativeProviderRequestRejected, CreativeProviderPreflightRejected) as exc:
        raise ControlledImageBridgeRejected(exc.code) from exc
