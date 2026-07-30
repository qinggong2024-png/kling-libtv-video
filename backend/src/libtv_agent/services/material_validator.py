from __future__ import annotations

from dataclasses import dataclass

from libtv_agent.templates.video_templates import (
    ActionIntensity,
    CameraTempo,
    CutMode,
    VideoTemplate,
)

SUPPORTED_IMAGE_MIME_TYPES = frozenset({"image/jpeg", "image/png", "image/webp"})


@dataclass(frozen=True)
class MaterialDescriptor:
    id: str
    order: int
    original_name: str
    mime_type: str
    size_bytes: int
    sha256: str
    width: int | None = None
    height: int | None = None


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    message: str
    material_id: str | None = None
    field: str | None = None


@dataclass(frozen=True)
class MaterialValidationResult:
    valid: bool
    errors: tuple[ValidationIssue, ...]
    warnings: tuple[ValidationIssue, ...]
    vision_check_required: bool = False


def validate_materials(
    materials: list[MaterialDescriptor],
    *,
    template: VideoTemplate | None,
    variant_count: int,
    action_intensity: ActionIntensity,
    camera_tempo: CameraTempo,
    cut_mode: CutMode,
    max_file_bytes: int = 20 * 1024 * 1024,
) -> MaterialValidationResult:
    errors: list[ValidationIssue] = []
    warnings: list[ValidationIssue] = []
    count = len(materials)

    if not 1 <= count <= 7:
        errors.append(
            ValidationIssue(
                "STORYBOARD_COUNT_INVALID",
                "storyboard image count must be between 1 and 7",
                field="storyboards",
            )
        )
    orders = [material.order for material in materials]
    if sorted(orders) != list(range(1, count + 1)):
        errors.append(
            ValidationIssue(
                "STORYBOARD_ORDER_INVALID",
                "storyboard order must be contiguous and start at 1",
                field="storyboards",
            )
        )
    if template is None:
        errors.append(
            ValidationIssue(
                "VIDEO_TEMPLATE_REQUIRED",
                "a known video template is required",
                field="templateId",
            )
        )
    elif not template.min_images <= count <= template.max_images:
        errors.append(
            ValidationIssue(
                "VIDEO_TEMPLATE_IMAGE_COUNT_INCOMPATIBLE",
                (
                    f"template {template.id} accepts between "
                    f"{template.min_images} and {template.max_images} images"
                ),
                field="templateId",
            )
        )
    if not 1 <= variant_count <= 4:
        errors.append(
            ValidationIssue(
                "VARIANT_COUNT_INVALID",
                "variant count must be between 1 and 4",
                field="variantCount",
            )
        )
    if action_intensity not in {"low", "standard", "high"}:
        errors.append(
            ValidationIssue(
                "ACTION_INTENSITY_INVALID",
                "action intensity is invalid",
                field="actionIntensity",
            )
        )
    if camera_tempo not in {"slow", "standard", "fast"}:
        errors.append(
            ValidationIssue(
                "CAMERA_TEMPO_INVALID",
                "camera tempo is invalid",
                field="cameraTempo",
            )
        )
    if cut_mode not in {"explicit_cuts", "continuous_when_possible"}:
        errors.append(ValidationIssue("CUT_MODE_INVALID", "cut mode is invalid", field="cutMode"))

    seen_hashes: dict[str, str] = {}
    for material in materials:
        if material.size_bytes <= 0:
            errors.append(
                ValidationIssue(
                    "IMAGE_EMPTY",
                    "image file is empty",
                    material_id=material.id,
                    field="storyboards",
                )
            )
        elif material.size_bytes > max_file_bytes:
            errors.append(
                ValidationIssue(
                    "IMAGE_TOO_LARGE",
                    f"image exceeds the {max_file_bytes}-byte size limit",
                    material_id=material.id,
                    field="storyboards",
                )
            )
        if material.mime_type not in SUPPORTED_IMAGE_MIME_TYPES:
            errors.append(
                ValidationIssue(
                    "IMAGE_MIME_UNSUPPORTED",
                    f"unsupported image MIME type: {material.mime_type}",
                    material_id=material.id,
                    field="storyboards",
                )
            )
        if not material.sha256:
            errors.append(
                ValidationIssue(
                    "IMAGE_SHA256_MISSING",
                    "image SHA-256 is missing",
                    material_id=material.id,
                    field="storyboards",
                )
            )
        elif first_id := seen_hashes.get(material.sha256):
            errors.append(
                ValidationIssue(
                    "DUPLICATE_STORYBOARD",
                    f"image duplicates storyboard material {first_id}",
                    material_id=material.id,
                    field="storyboards",
                )
            )
        else:
            seen_hashes[material.sha256] = material.id
        if material.width is not None and not 128 <= material.width <= 8192:
            errors.append(
                ValidationIssue(
                    "IMAGE_DIMENSIONS_INVALID",
                    "image width must be between 128 and 8192 pixels",
                    material_id=material.id,
                    field="storyboards",
                )
            )
        if material.height is not None and not 128 <= material.height <= 8192:
            errors.append(
                ValidationIssue(
                    "IMAGE_DIMENSIONS_INVALID",
                    "image height must be between 128 and 8192 pixels",
                    material_id=material.id,
                    field="storyboards",
                )
            )
        if material.width is None or material.height is None:
            warnings.append(
                ValidationIssue(
                    "IMAGE_DIMENSIONS_UNKNOWN",
                    "image dimensions are not available for deterministic validation",
                    material_id=material.id,
                    field="storyboards",
                )
            )

    return MaterialValidationResult(
        valid=not errors,
        errors=tuple(errors),
        warnings=tuple(warnings),
        vision_check_required=False,
    )
