import asyncio
import base64
from pathlib import Path

import pytest
from libtv_agent.adapters.object_store import LocalObjectStore
from libtv_agent.adapters.openai_analysis import (
    AnalysisImageInput,
    AnalysisTimeoutError,
    OpenAIAnalysisAdapter,
    fake_analysis,
)
from libtv_agent.config import Settings
from libtv_agent.services.analysis import (
    ANALYSIS_PROMPT_VERSION,
    _analysis_image_url,
    render_analysis_prompt,
)


class FakeResponses:
    def __init__(self) -> None:
        self.request: dict[str, object] | None = None

    async def parse(self, **kwargs: object) -> object:
        self.request = kwargs
        result = fake_analysis(["asset-1", "asset-2"])
        return type("ParsedResponse", (), {"output_parsed": result})()


class FakeOpenAIClient:
    def __init__(self) -> None:
        self.responses = FakeResponses()


class CapturingOpenAIClient(FakeOpenAIClient):
    kwargs: dict[str, object] | None = None

    def __init__(self, **kwargs: object) -> None:
        super().__init__()
        CapturingOpenAIClient.kwargs = kwargs


class SlowResponses:
    async def parse(self, **kwargs: object) -> object:
        del kwargs
        await asyncio.sleep(0.2)
        return type("ParsedResponse", (), {"output_parsed": fake_analysis(["asset-1"])})()


class SlowOpenAIClient:
    def __init__(self) -> None:
        self.responses = SlowResponses()


@pytest.mark.asyncio
async def test_openai_contract_binds_each_asset_and_order_without_network() -> None:
    client = FakeOpenAIClient()
    settings = Settings(openai_api_key=None, _env_file=None)
    adapter = OpenAIAnalysisAdapter(settings, client=client)
    prompt = render_analysis_prompt(["asset-1", "asset-2"], "Keep the logo readable")
    images = [
        AnalysisImageInput("asset-1", 1, "data:image/jpeg;base64,YQ=="),
        AnalysisImageInput("asset-2", 2, "https://objects.example.invalid/signed?ttl=300"),
    ]

    result = await adapter.analyze(prompt, images)

    assert result.model_version == "fake-2.1"
    assert client.responses.request is not None
    assert client.responses.request["model"] == "gpt-5.6-terra"
    assert client.responses.request["reasoning"] == {"effort": "low"}
    request_input = client.responses.request["input"]
    content = request_input[0]["content"]  # type: ignore[index]
    assert content[0]["text"].startswith("ANALYSIS_PROMPT_VERSION: analysis-v2.4.0")
    assert content[1] == {"type": "input_text", "text": "STORYBOARD assetId=asset-1 order=1"}
    assert content[2]["image_url"] == images[0].image_url
    assert content[3] == {"type": "input_text", "text": "STORYBOARD assetId=asset-2 order=2"}
    assert content[4]["image_url"] == images[1].image_url
    assert client.responses.request["text_format"].__name__ == "AnalysisResult"


@pytest.mark.asyncio
async def test_openai_analysis_has_a_hard_timeout() -> None:
    settings = Settings(
        openai_analysis_timeout_seconds=0.01,
        openai_api_key=None,
        _env_file=None,
    )
    adapter = OpenAIAnalysisAdapter(settings, client=SlowOpenAIClient())

    with pytest.raises(AnalysisTimeoutError, match="0.01 seconds"):
        await adapter.analyze(
            render_analysis_prompt(["asset-1"], ""),
            [AnalysisImageInput("asset-1", 1, "data:image/jpeg;base64,YQ==")],
        )


@pytest.mark.asyncio
async def test_openai_client_uses_configured_compatible_base_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("openai.AsyncOpenAI", CapturingOpenAIClient)
    settings = Settings(
        openai_api_key="model-test-secret-key",
        openai_base_url="https://gateway.example.test/v1",
        _env_file=None,
    )
    adapter = OpenAIAnalysisAdapter(settings)

    await adapter.analyze(
        render_analysis_prompt(["asset-1", "asset-2"], ""),
        [
            AnalysisImageInput("asset-1", 1, "data:image/jpeg;base64,YQ=="),
            AnalysisImageInput("asset-2", 2, "data:image/jpeg;base64,Yg=="),
        ],
    )

    assert CapturingOpenAIClient.kwargs == {
        "api_key": "model-test-secret-key",
        "base_url": "https://gateway.example.test/v1",
        "timeout": 180.0,
    }


def test_analysis_prompt_is_complete_and_versioned() -> None:
    prompt = render_analysis_prompt(["asset-a", "asset-b"], "  user requirement  ")
    normalized_prompt = " ".join(prompt.split())

    assert ANALYSIS_PROMPT_VERSION in prompt
    assert "assetId=asset-a; order=1" in prompt
    assert "assetId=asset-b; order=2" in prompt
    assert "All human-readable string values" in prompt
    assert "Simplified Chinese" in prompt
    assert "unknownFields" in prompt
    assert "Dynamic must not mean faster" in normalized_prompt
    assert "Mirror selfie or mirror recording" in prompt
    assert "Dress or skirt" in prompt
    assert "surface-locked textures" in prompt
    assert "continuous walking" in prompt
    assert "user requirement" in prompt
    assert "{{" not in prompt


@pytest.mark.asyncio
async def test_local_object_uses_controlled_data_url(tmp_path: Path) -> None:
    source = tmp_path / "objects" / "asset.jpg"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"jpeg-contract")
    store = LocalObjectStore(tmp_path / "objects")

    url = await _analysis_image_url(store, "asset.jpg", "asset-id", tmp_path / "cache")

    prefix, encoded = url.split(",", 1)
    assert prefix == "data:image/jpeg;base64"
    assert base64.b64decode(encoded) == b"jpeg-contract"
