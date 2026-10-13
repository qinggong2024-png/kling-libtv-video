from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from libtv_agent.app import create_app
from libtv_agent.config import Settings
from libtv_agent.domain.models import Base
from sqlalchemy.ext.asyncio import create_async_engine


@pytest.fixture
async def product_client(tmp_path: Path) -> AsyncIterator[tuple[AsyncClient, Settings]]:
    database_url = f"sqlite+aiosqlite:///{(tmp_path / 'products.db').as_posix()}"
    engine = create_async_engine(database_url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    await engine.dispose()

    settings = Settings(
        app_env="test",
        database_url=database_url,
        object_store_mode="local",
        artifact_root=tmp_path / "artifacts",
        runner_root=tmp_path / "runner",
        _env_file=None,
    )
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            yield client, settings


def product_payload(sku: str = "SKU-01") -> dict[str, object]:
    return {"internalSkuId": sku}


def version_payload(*, license_status: str = "UNKNOWN") -> dict[str, object]:
    return {
        "productPageUrl": "https://example.invalid/products/sku-01",
        "pageTitle": "Example Product",
        "candidateNames": ["Example Product"],
        "truthFields": {"productType": "cardigan", "dominantColor": "black"},
        "immutableFields": {"graphicRegions": ["front"]},
        "allowedVariation": ["camera angle", "background"],
        "sourceAssetReferences": ["upload:source-01"],
        "licenseStatus": license_status,
    }


@pytest.mark.asyncio
async def test_product_and_immutable_version_lifecycle_and_license_gate(
    product_client: tuple[AsyncClient, Settings],
) -> None:
    client, settings = product_client
    headers = {"X-User-Id": settings.dev_user_id}

    created = await client.post("/api/v1/products", headers=headers, json=product_payload())
    assert created.status_code == 201, created.text
    product = created.json()
    assert product["internalSkuId"] == "SKU-01"

    version = await client.post(
        f"/api/v1/products/{product['id']}/versions",
        headers=headers,
        json=version_payload(),
    )
    assert version.status_code == 201, version.text
    version_body = version.json()
    assert version_body["versionNumber"] == 1
    assert version_body["status"] == "DRAFT"
    assert version_body["licenseStatus"] == "UNKNOWN"

    blocked_handoff = await client.post(
        f"/api/v1/products/{product['id']}/versions/{version_body['id']}/handoff",
        headers=headers,
    )
    assert blocked_handoff.status_code == 409

    confirmed = await client.post(
        f"/api/v1/products/{product['id']}/versions/{version_body['id']}/confirm",
        headers=headers,
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["status"] == "APPROVED"

    still_blocked = await client.post(
        f"/api/v1/products/{product['id']}/versions/{version_body['id']}/delivery",
        headers=headers,
    )
    assert still_blocked.status_code == 409

    # ProductVersion has no update endpoint: corrections create a new immutable version.
    replacement = await client.post(
        f"/api/v1/products/{product['id']}/versions",
        headers=headers,
        json=version_payload(license_status="VERIFIED"),
    )
    assert replacement.status_code == 201
    replacement_body = replacement.json()
    assert replacement_body["versionNumber"] == 2

    approved = await client.post(
        f"/api/v1/products/{product['id']}/versions/{replacement_body['id']}/confirm",
        headers=headers,
    )
    assert approved.status_code == 200
    delivered = await client.post(
        f"/api/v1/products/{product['id']}/versions/{replacement_body['id']}/delivery",
        headers=headers,
    )
    assert delivered.status_code == 200
    assert delivered.json()["allowed"] is True


@pytest.mark.asyncio
async def test_product_and_version_are_isolated_between_users(
    product_client: tuple[AsyncClient, Settings],
) -> None:
    client, settings = product_client
    user_headers = {"X-User-Id": settings.dev_user_id}
    admin_headers = {"X-User-Id": settings.dev_admin_id}

    created = await client.post(
        "/api/v1/products",
        headers=user_headers,
        json=product_payload("USER-ONLY"),
    )
    assert created.status_code == 201
    product_id = created.json()["id"]

    other_list = await client.get("/api/v1/products", headers=admin_headers)
    assert other_list.status_code == 200
    assert all(item["id"] != product_id for item in other_list.json())

    other_get = await client.get(f"/api/v1/products/{product_id}", headers=admin_headers)
    assert other_get.status_code == 404

    denied_version = await client.post(
        f"/api/v1/products/{product_id}/versions",
        headers=admin_headers,
        json=version_payload(),
    )
    assert denied_version.status_code == 404


@pytest.mark.asyncio
async def test_blocked_version_cannot_be_confirmed_and_reason_is_preserved(
    product_client: tuple[AsyncClient, Settings],
) -> None:
    client, settings = product_client
    headers = {"X-User-Id": settings.dev_user_id}
    product = (
        await client.post(
            "/api/v1/products",
            headers=headers,
            json=product_payload("BLOCK"),
        )
    ).json()
    version = (
        await client.post(
            f"/api/v1/products/{product['id']}/versions",
            headers=headers,
            json=version_payload(),
        )
    ).json()

    blocked = await client.post(
        f"/api/v1/products/{product['id']}/versions/{version['id']}/block",
        headers=headers,
        json={"reason": "商品身份与页面标题冲突，等待人工确认"},
    )
    assert blocked.status_code == 200
    assert blocked.json()["status"] == "BLOCKED"
    assert blocked.json()["blockedReason"].startswith("商品身份")

    confirmed = await client.post(
        f"/api/v1/products/{product['id']}/versions/{version['id']}/confirm",
        headers=headers,
    )
    assert confirmed.status_code == 409
