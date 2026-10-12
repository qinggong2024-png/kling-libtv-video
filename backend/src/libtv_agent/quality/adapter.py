from typing import Protocol

from .contracts import ImageQualityContract, QualityReview, VideoQualityContract


class QualityContractAdapter(Protocol):
    """Read-only boundary for quality evidence producers.

    Implementations map an existing media/check result into a contract record.
    They must not mutate task state, call a provider, write billing data, or
    decide whether production is blocked.
    """

    adapter_name: str

    def image_contract(self, value: ImageQualityContract) -> ImageQualityContract:
        """Return the normalized image evidence record."""

    def video_contract(self, value: VideoQualityContract) -> VideoQualityContract:
        """Return the normalized video evidence record."""

    def review(self, value: QualityReview) -> QualityReview:
        """Return the normalized review record."""
