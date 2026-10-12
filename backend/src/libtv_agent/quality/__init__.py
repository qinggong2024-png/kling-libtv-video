"""Evidence-only quality contracts and adapters.

This package deliberately has no task-state, provider, billing, or production-gate
dependencies. Consumers may persist or display its records through existing flows.
"""

from .adapter import QualityContractAdapter
from .contracts import (
    FailureTaxonomyEntry,
    ImageQualityContract,
    QualityCheck,
    QualityReview,
    VideoQualityContract,
)
from .taxonomy import FAILURE_TAXONOMY

__all__ = [
    "FAILURE_TAXONOMY",
    "FailureTaxonomyEntry",
    "ImageQualityContract",
    "QualityCheck",
    "QualityContractAdapter",
    "QualityReview",
    "VideoQualityContract",
]
