"""Shared append-only facts creation; serialize version allocation on the Product row."""
from __future__ import annotations

import uuid

from fastapi import HTTPException
from libtv_agent.creative.workflow import digest
from libtv_agent.domain.models import Product, ProductVersion
from libtv_agent.domain.schemas import ProductVersionCreate
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession


def version_content(value: ProductVersion) -> dict:
    return {
        "product_id": str(value.product_id), "product_version_id": str(value.id),
        "facts_revision": value.version_number, "source_type": value.source_type,
        "product_page_url": value.product_page_url, "page_title": value.page_title,
        "candidate_names": value.candidate_names, "truth_fields": value.truth_fields,
        "immutable_fields": value.immutable_fields, "allowed_variation": value.allowed_variation,
        "source_asset_references": value.source_asset_references,
    }


async def append_version(
    session: AsyncSession, product_id: uuid.UUID, payload: ProductVersionCreate,
) -> ProductVersion:
    await session.execute(update(Product).where(Product.id == product_id).values(
        updated_at=Product.updated_at,
    ))
    values = payload.model_dump(
        exclude={"product_id", "client_request_key"}, mode="json", by_alias=False,
    )
    fingerprint = digest(values)
    if payload.client_request_key:
        prior = await session.scalar(select(ProductVersion).where(
            ProductVersion.product_id == product_id,
            ProductVersion.request_key == payload.client_request_key,
        ))
        if prior:
            if prior.request_hash != fingerprint:
                raise HTTPException(409, {"code": "PRODUCT_VERSION_IDEMPOTENCY_CONFLICT"})
            return prior
    number = await session.scalar(select(func.coalesce(func.max(
        ProductVersion.version_number,
    ), 0)).where(ProductVersion.product_id == product_id))
    value = ProductVersion(
        id=uuid.uuid4(), product_id=product_id, version_number=number + 1,
        request_key=payload.client_request_key, request_hash=fingerprint, **values,
    )
    session.add(value)
    await session.flush()
    return value
