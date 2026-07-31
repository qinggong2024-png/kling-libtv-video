import pytest
from httpx import ASGITransport, AsyncClient
from libtv_agent.app import create_app
from libtv_agent.config import Settings
from libtv_agent.domain.models import Base


@pytest.mark.asyncio
async def test_prompt_preset_crud_is_user_owned() -> None:
    settings = Settings(
        app_env="test",
        database_url="sqlite+aiosqlite:///:memory:",
        _env_file=None,
    )
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        async with app.state.database.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            user_headers = {"X-User-Id": settings.dev_user_id}
            admin_headers = {"X-User-Id": settings.dev_admin_id}
            created = await client.post(
                "/api/v1/prompt-presets",
                headers=user_headers,
                json={
                    "scope": "image_storyboard",
                    "name": "自然走动",
                    "content": "人物自然向前走动。",
                    "sortOrder": 2,
                },
            )
            assert created.status_code == 201, created.text
            assert created.json()["scope"] == "image_storyboard"
            preset_id = created.json()["id"]

            listed = await client.get(
                "/api/v1/prompt-presets?scope=image_storyboard", headers=user_headers
            )
            assert listed.status_code == 200
            assert [item["name"] for item in listed.json()] == ["默认 1", "自然走动"]
            default_storyboard_id = listed.json()[0]["id"]
            assert "图一的人物和环境" in listed.json()[0]["content"]

            updated_default = await client.put(
                f"/api/v1/prompt-presets/{default_storyboard_id}",
                headers=user_headers,
                json={
                    "scope": "image_storyboard",
                    "name": "默认 1",
                    "content": "用户修改后的默认分镜提示词。",
                    "sortOrder": 0,
                },
            )
            assert updated_default.status_code == 200
            assert updated_default.json()["content"] == "用户修改后的默认分镜提示词。"

            video_preset = await client.post(
                "/api/v1/prompt-presets",
                headers=user_headers,
                json={"scope": "video", "name": "自然走动", "content": "视频提示词。"},
            )
            assert video_preset.status_code == 201, video_preset.text
            video_list = await client.get(
                "/api/v1/prompt-presets?scope=video", headers=user_headers
            )
            assert {item["name"] for item in video_list.json()} == {"默认 1", "自然走动"}
            default_video = next(item for item in video_list.json() if item["name"] == "默认 1")
            assert "iPhone17" in default_video["content"]

            fusion_list = await client.get(
                "/api/v1/prompt-presets?scope=image_fusion", headers=user_headers
            )
            assert fusion_list.status_code == 200
            assert "完整保留图一原始背景" in fusion_list.json()[0]["content"]

            other_user_list = await client.get(
                "/api/v1/prompt-presets?scope=image_storyboard", headers=admin_headers
            )
            assert other_user_list.status_code == 200
            assert [item["name"] for item in other_user_list.json()] == ["默认 1"]
            forbidden_update = await client.put(
                f"/api/v1/prompt-presets/{preset_id}",
                headers=admin_headers,
                json={
                    "scope": "image_storyboard",
                    "name": "越权修改",
                    "content": "不可见",
                    "sortOrder": 0,
                },
            )
            assert forbidden_update.status_code == 404

            updated = await client.put(
                f"/api/v1/prompt-presets/{preset_id}",
                headers=user_headers,
                json={
                    "scope": "image_storyboard",
                    "name": "背面展示",
                    "content": "人物转身展示背面。",
                    "sortOrder": 1,
                },
            )
            assert updated.status_code == 200
            assert updated.json()["name"] == "背面展示"

            deleted = await client.delete(
                f"/api/v1/prompt-presets/{preset_id}",
                headers=user_headers,
            )
            assert deleted.status_code == 204
            remaining = await client.get(
                "/api/v1/prompt-presets?scope=image_storyboard", headers=user_headers
            )
            assert [item["id"] for item in remaining.json()] == [default_storyboard_id]

            deleted_default = await client.delete(
                f"/api/v1/prompt-presets/{default_storyboard_id}",
                headers=user_headers,
            )
            assert deleted_default.status_code == 204
            empty = await client.get(
                "/api/v1/prompt-presets?scope=image_storyboard", headers=user_headers
            )
            assert empty.json() == []
            still_empty = await client.get(
                "/api/v1/prompt-presets?scope=image_storyboard", headers=user_headers
            )
            assert still_empty.json() == []
