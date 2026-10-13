import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, status
from libtv_agent.api.dependencies import Actor, Session
from libtv_agent.domain.enums import ProductLicenseStatus, ProductVersionStatus
from libtv_agent.domain.models import Product, ProductVersion
from libtv_agent.domain.schemas import (
    ProductCreate,
    ProductRead,
    ProductVersionCreate,
    ProductVersionDecision,
    ProductVersionRead,
)
from libtv_agent.services.product_versions import append_version
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, OperationalError

router = APIRouter(prefix="/products", tags=["products"])


def _version_read(value: ProductVersion) -> ProductVersionRead:
    return ProductVersionRead.model_validate(value, from_attributes=True)


async def _owned_product(product_id: uuid.UUID, actor: Actor, session: Session) -> Product:
    value = await session.scalar(
        select(Product).where(Product.id == product_id, Product.user_id == actor.id)
    )
    if value is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "product was not found")
    return value


async def _owned_version(
    product_id: uuid.UUID,
    version_id: uuid.UUID,
    actor: Actor,
    session: Session,
) -> ProductVersion:
    value = await session.scalar(
        select(ProductVersion)
        .join(Product, Product.id == ProductVersion.product_id)
        .where(
            ProductVersion.id == version_id,
            ProductVersion.product_id == product_id,
            Product.user_id == actor.id,
        )
    )
    if value is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "product version was not found")
    return value


async def _product_read(value: Product, session: Session) -> ProductRead:
    current = await session.scalar(
        select(ProductVersion)
        .where(ProductVersion.product_id == value.id)
        .order_by(ProductVersion.version_number.desc())
        .limit(1)
    )
    return ProductRead(
        id=value.id,
        user_id=value.user_id,
        internal_sku_id=value.internal_sku_id,
        current_version_id=current.id if current else None,
        created_at=value.created_at,
        updated_at=value.updated_at,
    )


@router.post("", response_model=ProductRead, status_code=status.HTTP_201_CREATED)
async def create_product(
    payload: ProductCreate,
    actor: Actor,
    session: Session,
) -> ProductRead:
    value = Product(user_id=actor.id, internal_sku_id=payload.internal_sku_id)
    session.add(value)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "a product with this internal SKU already exists",
        ) from exc
    await session.refresh(value)
    return await _product_read(value, session)


@router.get("", response_model=list[ProductRead])
async def list_products(actor: Actor, session: Session) -> list[ProductRead]:
    values = list(
        await session.scalars(
            select(Product)
            .where(Product.user_id == actor.id)
            .order_by(Product.updated_at.desc(), Product.id)
        )
    )
    return [await _product_read(value, session) for value in values]


@router.get("/{product_id}", response_model=ProductRead)
async def get_product(
    product_id: uuid.UUID,
    actor: Actor,
    session: Session,
) -> ProductRead:
    return await _product_read(await _owned_product(product_id, actor, session), session)


@router.post(
    "/{product_id}/versions",
    response_model=ProductVersionRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_product_version(
    product_id: uuid.UUID,
    payload: ProductVersionCreate,
    actor: Actor,
    session: Session,
) -> ProductVersionRead:
    await _owned_product(product_id, actor, session)
    if payload.product_id is not None and payload.product_id != product_id:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "product id does not match path")
    try:
        value = await append_version(session, product_id, payload)
        await session.commit()
    except (IntegrityError, OperationalError) as exc:
        await session.rollback()
        raise HTTPException(409, {"code": "RETRYABLE_PRODUCT_VERSION_CONFLICT"}) from exc
    await session.refresh(value)
    return _version_read(value)


@router.get("/{product_id}/versions", response_model=list[ProductVersionRead])
async def list_product_versions(
    product_id: uuid.UUID,
    actor: Actor,
    session: Session,
) -> list[ProductVersionRead]:
    await _owned_product(product_id, actor, session)
    values = list(
        await session.scalars(
            select(ProductVersion)
            .where(ProductVersion.product_id == product_id)
            .order_by(ProductVersion.version_number.desc())
        )
    )
    return [_version_read(value) for value in values]


@router.get("/{product_id}/versions/{version_id}", response_model=ProductVersionRead)
async def get_product_version(
    product_id: uuid.UUID,
    version_id: uuid.UUID,
    actor: Actor,
    session: Session,
) -> ProductVersionRead:
    return _version_read(await _owned_version(product_id, version_id, actor, session))


@router.post("/{product_id}/versions/{version_id}/confirm", response_model=ProductVersionRead)
async def confirm_product_version(
    product_id: uuid.UUID,
    version_id: uuid.UUID,
    actor: Actor,
    session: Session,
) -> ProductVersionRead:
    value = await _owned_version(product_id, version_id, actor, session)
    if value.status is ProductVersionStatus.BLOCKED:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "blocked product version must be unblocked by a new version",
        )
    value.status = ProductVersionStatus.APPROVED
    value.blocked_reason = None
    value.confirmed_at = datetime.now(UTC)
    await session.commit()
    await session.refresh(value)
    return _version_read(value)


@router.post("/{product_id}/versions/{version_id}/block", response_model=ProductVersionRead)
async def block_product_version(
    product_id: uuid.UUID,
    version_id: uuid.UUID,
    payload: ProductVersionDecision,
    actor: Actor,
    session: Session,
) -> ProductVersionRead:
    value = await _owned_version(product_id, version_id, actor, session)
    value.status = ProductVersionStatus.BLOCKED
    value.blocked_reason = payload.reason or "blocked by user"
    value.confirmed_at = None
    await session.commit()
    await session.refresh(value)
    return _version_read(value)


async def _assert_production_eligible(value: ProductVersion) -> None:
    if value.status is not ProductVersionStatus.APPROVED:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "product version must be approved before production",
        )
    if value.license_status is not ProductLicenseStatus.VERIFIED:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "product version license must be VERIFIED before handoff or delivery",
        )


@router.post("/{product_id}/versions/{version_id}/handoff")
async def handoff_product_version(
    product_id: uuid.UUID,
    version_id: uuid.UUID,
    actor: Actor,
    session: Session,
) -> dict[str, object]:
    value = await _owned_version(product_id, version_id, actor, session)
    await _assert_production_eligible(value)
    return {"allowed": True, "productId": str(product_id), "versionId": str(version_id)}


@router.post("/{product_id}/versions/{version_id}/delivery")
async def deliver_product_version(
    product_id: uuid.UUID,
    version_id: uuid.UUID,
    actor: Actor,
    session: Session,
) -> dict[str, object]:
    value = await _owned_version(product_id, version_id, actor, session)
    await _assert_production_eligible(value)
    return {"allowed": True, "productId": str(product_id), "versionId": str(version_id)}
