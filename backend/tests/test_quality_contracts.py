import json
from datetime import UTC, datetime
from pathlib import Path

from libtv_agent.quality import (
    FAILURE_TAXONOMY,
    ImageQualityContract,
    QualityCheck,
    QualityReview,
    VideoQualityContract,
)

ROOT = Path(__file__).parents[2]
CONTRACT_DIR = ROOT / "backend" / "contracts" / "quality"


def test_quality_contract_schemas_are_strict_and_versioned() -> None:
    expected = {
        "image-quality-contract.schema.json",
        "video-quality-contract.schema.json",
        "review.schema.json",
        "failure-taxonomy.schema.json",
    }
    assert {path.name for path in CONTRACT_DIR.glob("*.json")} == expected
    for path in CONTRACT_DIR.glob("*.json"):
        document = json.loads(path.read_text(encoding="utf-8"))
        assert document["$schema"].endswith("/draft/2020-12/schema")
        assert document["additionalProperties"] is False
        assert "1.0" in json.dumps(document)


def test_quality_models_preserve_offline_synthetic_only_semantics() -> None:
    timestamp = datetime.now(UTC)
    image = ImageQualityContract(
        asset={
            "asset_id": "synthetic-image",
            "mime_type": "image/png",
            "sha256": "a" * 64,
        },
        checks=[QualityCheck(check_id="IMAGE_READABLE", result="PASS", evidence=["replay"])],
        observed_at=timestamp,
        mode="OFFLINE_SYNTHETIC_ONLY",
    )
    video = VideoQualityContract(
        artifact={
            "artifact_id": "synthetic-video",
            "mime_type": "video/mp4",
            "sha256": "b" * 64,
            "size_bytes": 1,
        },
        checks=[QualityCheck(check_id="VIDEO_DECODABLE", result="PASS", evidence=["replay"])],
        observed_at=timestamp,
        mode="OFFLINE_SYNTHETIC_ONLY",
    )
    review = QualityReview(
        subject={"subject_type": "VIDEO", "subject_id": "synthetic-video"},
        recommendation="QUALITY_REVIEW",
        evidence_refs=["synthetic-video"],
        reviewed_at=timestamp,
        mode="OFFLINE_SYNTHETIC_ONLY",
    )
    assert image.mode == video.mode == review.mode == "OFFLINE_SYNTHETIC_ONLY"
    assert image.contract_version == video.contract_version == "1.0"
    assert review.review_version == "1.0"


def test_taxonomy_codes_are_unique_and_descriptive() -> None:
    codes = [entry.code for entry in FAILURE_TAXONOMY]
    assert len(codes) == len(set(codes))
    assert all(entry.description for entry in FAILURE_TAXONOMY)
