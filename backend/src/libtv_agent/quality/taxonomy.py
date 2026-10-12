from .contracts import FailureTaxonomyEntry

FAILURE_TAXONOMY: tuple[FailureTaxonomyEntry, ...] = (
    FailureTaxonomyEntry(
        code="INPUT_UNREADABLE",
        family="INPUT",
        severity="ERROR",
        description="The source asset cannot be decoded or read.",
    ),
    FailureTaxonomyEntry(
        code="MEDIA_METADATA_MISSING",
        family="MEDIA",
        severity="ERROR",
        description="Required media metadata is missing from the observation.",
    ),
    FailureTaxonomyEntry(
        code="MEDIA_DURATION_OUT_OF_RANGE",
        family="MEDIA",
        severity="WARNING",
        description="Observed duration is outside the configured quality expectation.",
        retryable=False,
    ),
    FailureTaxonomyEntry(
        code="MEDIA_ASPECT_RATIO_INVALID",
        family="MEDIA",
        severity="WARNING",
        description="Observed dimensions do not match the expected aspect ratio.",
    ),
    FailureTaxonomyEntry(
        code="MEDIA_UNEXPECTED_AUDIO",
        family="MEDIA",
        severity="WARNING",
        description="An audio stream was observed where silent output was expected.",
    ),
    FailureTaxonomyEntry(
        code="CONTENT_PRODUCT_NOT_VISIBLE",
        family="CONTENT",
        severity="ERROR",
        description="The product is not sufficiently visible for the requested check.",
        requires_human_review=True,
    ),
    FailureTaxonomyEntry(
        code="CONSISTENCY_PRODUCT_MISMATCH",
        family="CONSISTENCY",
        severity="ERROR",
        description="Observed product details are inconsistent with the references.",
        requires_human_review=True,
    ),
    FailureTaxonomyEntry(
        code="EVIDENCE_INSUFFICIENT",
        family="EVIDENCE",
        severity="WARNING",
        description="The available evidence is insufficient for a reliable conclusion.",
        requires_human_review=True,
    ),
    FailureTaxonomyEntry(
        code="SYSTEM_OBSERVATION_UNAVAILABLE",
        family="SYSTEM",
        severity="ERROR",
        description="The quality observer could not produce an observation.",
        retryable=True,
    ),
)
