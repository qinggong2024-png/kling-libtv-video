from __future__ import annotations

import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


HANDOFF_SCHEMA_VERSION = "creative-handoff.v1"
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class HandoffModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class HandoffOwner(HandoffModel):
    owner_id: str = Field(min_length=1, max_length=160)


class HandoffProduct(HandoffModel):
    product_id: str = Field(min_length=1, max_length=160)
    product_version: int = Field(ge=1)


class HandoffCreative(HandoffModel):
    strategy_id: str = Field(min_length=1, max_length=160)
    experiment_id: str = Field(min_length=1, max_length=160)
    variant_id: str = Field(min_length=1, max_length=160)
    storyboard_id: str = Field(min_length=1, max_length=160)
    prompt_version: str = Field(min_length=1, max_length=160)


class HandoffLicense(HandoffModel):
    status: Literal["VERIFIED"] = "VERIFIED"
    references: list[str] = Field(min_length=1, max_length=30)


class HandoffApproval(HandoffModel):
    status: Literal["APPROVED"] = "APPROVED"
    version: int = Field(ge=1)
    approved_by: str = Field(min_length=1, max_length=160)
    approved_at: datetime


class HandoffAsset(HandoffModel):
    asset_id: str = Field(min_length=1, max_length=160)
    object_key: str = Field(min_length=1, max_length=500)
    sha256: str = Field(min_length=64, max_length=64)
    kind: Literal["image", "video"]
    mime_type: str = Field(min_length=3, max_length=120)
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    duration_seconds: float | None = Field(default=None, gt=0)
    approval: HandoffApproval
    license: HandoffLicense

    @model_validator(mode="after")
    def validate_sha256(self) -> "HandoffAsset":
        if not SHA256_PATTERN.fullmatch(self.sha256):
            raise ValueError("sha256 must be 64 lowercase hexadecimal characters")
        if self.kind == "image" and self.duration_seconds is not None:
            raise ValueError("image assets cannot declare duration_seconds")
        return self


class HandoffShot(HandoffModel):
    shot_id: str = Field(min_length=1, max_length=160)
    asset_id: str = Field(min_length=1, max_length=160)
    slot_id: str = Field(min_length=1, max_length=160)
    order: int = Field(ge=1)
    tags: list[str] = Field(min_length=1, max_length=30)
    duration_seconds: float = Field(gt=0, le=120)
    product_visibility: float = Field(ge=0, le=1)
    product_centered: bool
    motion_energy: Literal["high", "medium", "low"]


class HandoffSafeArea(HandoffModel):
    top: float = Field(ge=0, le=1)
    right: float = Field(ge=0, le=1)
    bottom: float = Field(ge=0, le=1)
    left: float = Field(ge=0, le=1)


class HandoffConstraints(HandoffModel):
    aspect_ratio: str = Field(pattern=r"^\d{1,2}:\d{1,2}$")
    max_duration_seconds: float = Field(gt=0, le=120)
    safe_area: HandoffSafeArea
    audio_policy: Literal["none", "post_only", "approved_asset_audio"]


class CreativeHandoffManifest(HandoffModel):
    schema_version: Literal[HANDOFF_SCHEMA_VERSION] = HANDOFF_SCHEMA_VERSION
    handoff_id: str = Field(min_length=1, max_length=160)
    created_at: datetime
    source_system: Literal["libtv_agent"] = "libtv_agent"
    target_system: Literal["cutflow"] = "cutflow"
    owner: HandoffOwner
    product: HandoffProduct
    creative: HandoffCreative
    assets: list[HandoffAsset] = Field(min_length=1, max_length=100)
    shots: list[HandoffShot] = Field(min_length=1, max_length=100)
    constraints: HandoffConstraints

    @model_validator(mode="after")
    def validate_references(self) -> "CreativeHandoffManifest":
        asset_ids = [asset.asset_id for asset in self.assets]
        if len(asset_ids) != len(set(asset_ids)):
            raise ValueError("handoff assets must have unique asset_id values")
        shot_ids = [shot.shot_id for shot in self.shots]
        if len(shot_ids) != len(set(shot_ids)):
            raise ValueError("handoff shots must have unique shot_id values")
        if sorted(shot.order for shot in self.shots) != list(range(1, len(self.shots) + 1)):
            raise ValueError("handoff shot order must be contiguous and start at 1")
        if any(shot.asset_id not in asset_ids for shot in self.shots):
            raise ValueError("every handoff shot must reference an asset in the same manifest")
        if any(asset.approval.status != "APPROVED" for asset in self.assets):
            raise ValueError("handoff assets must be approved")
        if any(asset.license.status != "VERIFIED" for asset in self.assets):
            raise ValueError("handoff assets must have verified licenses")
        return self
