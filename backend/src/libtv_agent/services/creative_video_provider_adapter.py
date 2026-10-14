"""Bind a validated local input lease to the existing video adapter; never submit."""
from __future__ import annotations

import hashlib
from collections.abc import Sequence

from libtv_agent.adapters.video_provider import VideoGenerationRequest
from libtv_agent.creative.workflow import digest
from libtv_agent.services.creative_provider_preflight import MaterializedProviderInput
from libtv_agent.services.creative_provider_requests import (
    CreativeProviderRequestRejected,
    CreativeVideoProviderRequest,
)


def bind_creative_video_adapter_request(
    request: CreativeVideoProviderRequest,
    inputs: Sequence[MaterializedProviderInput],
) -> VideoGenerationRequest:
    """Preserve wire order and verify bytes without granting Provider authorization."""
    if request.request_hash != digest(request.model_dump(mode="json", exclude={"request_hash"})):
        raise CreativeProviderRequestRejected("PROVIDER_REQUEST_STALE")
    if len(inputs) != len(request.references):
        raise CreativeProviderRequestRejected("REFERENCE_BINDINGS_INVALID")
    for ref, entry in zip(request.references, inputs, strict=True):
        if (
            (ref.role, ref.order, ref.adapter_field, ref.object_key, ref.sha256)
            != (entry.role, entry.order, entry.adapter_field, entry.object_key, entry.sha256)
            or not entry.path.is_file() or entry.path.is_symlink()
        ):
            raise CreativeProviderRequestRejected("REFERENCE_BINDINGS_INVALID")
        if hashlib.sha256(entry.path.read_bytes()).hexdigest() != ref.sha256:
            raise CreativeProviderRequestRejected("REFERENCE_HASH_MISMATCH")
    first = tuple(e.path for e in inputs if e.adapter_field == "first_frame_path")
    storyboards = tuple(e.path for e in inputs if e.adapter_field == "refer_image_paths")
    products = tuple(e.path for e in inputs if e.adapter_field == "product_reference_paths")
    if (
        len(first) != 1 or not products
        or len(first) + len(storyboards) + len(products) != len(inputs)
    ):
        raise CreativeProviderRequestRejected("REFERENCE_BINDINGS_INVALID")
    if tuple(e.path for e in inputs) != (*first, *storyboards, *products):
        raise CreativeProviderRequestRejected("REFERENCE_BINDINGS_INVALID")
    return VideoGenerationRequest(
        **request.adapter_parameters.model_dump(),
        first_frame_path=first[0], refer_image_paths=storyboards,
        product_reference_paths=products,
    )
