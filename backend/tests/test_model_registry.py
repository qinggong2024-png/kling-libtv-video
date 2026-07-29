from datetime import UTC, datetime

from libtv_agent.services.model_registry import (
    as_utc,
    compatibility_fingerprint,
    map_generation_params,
    normalize_live_schema,
    validate_model_compatibility,
)


def live_payload() -> dict:
    return {
        "modelKey": "kling-v3-omni",
        "modelName": "Kling O3",
        "modality": "video",
        "schema": {
            "properties": {
                "prompt": {"maxLength": 2000, "originalField": "prompt"},
                "ratio": {"enum": ["16:9", "9:16"], "originalField": "ratio"},
                "duration": {"min": 3, "max": 15, "originalField": "duration"},
                "quality_4k": {
                    "enum": [{"value": "low"}, {"value": "high"}],
                    "originalField": "quality",
                },
                "enableSound": {
                    "enum": [{"value": "on"}, {"value": "off"}],
                    "originalField": "enableSound",
                },
                "smartStoryboard": {"originalField": "multi_shot"},
                "modeType": {
                    "originalField": "modeType",
                    "items": {"singleImage2video": [1, 1], "mixed2video": [1, 7]},
                },
            },
            "config": {
                "settings": {
                    "singleImage2video": ["ratio", "duration", "quality_4k"],
                    "mixed2video": ["ratio", "duration", "quality_4k"],
                }
            },
        },
    }


def test_as_utc_handles_sqlite_naive_and_aware_datetimes() -> None:
    naive = datetime(2026, 7, 27, 12, 0, 0)
    aware = datetime(2026, 7, 27, 12, 0, 0, tzinfo=UTC)

    assert as_utc(naive) == aware
    assert as_utc(aware) == aware
    assert as_utc(None) is None


def test_live_schema_is_compatible_and_maps_original_fields() -> None:
    normalized = normalize_live_schema(live_payload())

    assert validate_model_compatibility(normalized).compatible
    assert len(compatibility_fingerprint(normalized)) == 64
    assert map_generation_params(
        {
            "preset": "DEFAULT_10S_9X16",
            "model": "Kling O3",
            "modelKey": "kling-v3-omni",
            "modeType": "mixed2video",
            "aspectRatio": "9:16",
            "duration": 10,
            "quality": "high",
            "sound": "off",
            "smartStoryboard": False,
            "count": 1,
        },
        normalized,
    ) == {
        "model": "Kling O3",
        "modeType": "mixed2video",
        "ratio": "9:16",
        "duration": 10,
        "quality": "high",
        "enableSound": "off",
        "multi_shot": False,
        "count": 1,
    }
