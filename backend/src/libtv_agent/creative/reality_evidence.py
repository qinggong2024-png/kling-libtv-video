"""Versioned knowledge for the existing six Reality dimensions.

These are authoring and review instructions, never observed product facts or
pixel verdicts. Freeze the returned snapshot with a new package's Registry.
"""
from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from typing import Any

from libtv_agent.creative.text_contract import canonical_hash

RULES_VERSION = "reality-evidence.v1"
COMPILER_VERSION = "compact-photo.v1.13.14"
REALITY_ORDER = (
    "Camera", "Lighting", "Composition", "Human Behavior", "Environment", "Imperfection",
)


@dataclass(frozen=True)
class EvidenceRule:
    dimension: str
    rule_id: str
    context_fields: tuple[str, ...]
    generation_constraint: str
    judgment_standard: str
    review_axis: str
    revision_module: str
    causal_variable: str
    optional_patterns: tuple[str, ...] = ()


RULES = (
    EvidenceRule(
        "Camera", "camera.operator-intent",
        ("operator", "capture_reason", "distance", "subject_camera_awareness"),
        "Specify who takes the image, why, distance and whether the subject notices the camera "
        "when known; keep missing values unresolved. For casual capture, let framing follow "
        "the operator's activity. A phone model name alone does not establish capture intent.",
        "Compare framing, distance, gaze and camera awareness with the intended photographer "
        "and capture reason. Looking at the camera can be valid; do not demand candid capture "
        "when the chosen direction is posed, selfie or studio.",
        "human_capture", "Reality", "operator_intent",
        ("Casual phone capture, if selected: a friend takes a photo while walking nearby.",),
    ),
    EvidenceRule(
        "Lighting", "lighting.shared-causality",
        ("source", "direction", "contact_shadows", "exposure"),
        "Use a physically coherent source and direction across person, garment and objects; "
        "retain contact shadows and readable product detail. Do not replace the chosen "
        "lighting with a generic cinematic or phone-photo treatment.",
        "Compare highlights, cast/contact shadows and exposure across the subject and scene. "
        "Check the promised product evidence remains visible; no added grain can repair "
        "contradictory illumination.",
        "spatial_light_integration", "Reality", "light_integration",
    ),
    EvidenceRule(
        "Composition", "composition.subject-environment",
        ("subject_object_distance", "hand_object_contact", "foot_support",
         "fabric_gravity", "occlusion"),
        "Describe subject-to-environment relationships using existing spatial anchors: "
        "subject/table distance, hand proximity or actual contact, supported feet when visible, "
        "gravity and tension in fabric, and consistent foreground/background occlusion. "
        "Do not invent a second Spatial model or force hidden feet into frame.",
        "Inspect visible contacts, scale, support, fabric drape and occlusion against the "
        "specified relationships. A subject pasted onto a plausible background fails "
        "integration; off-frame contact is unverified, not automatically failed.",
        "spatial_light_integration", "Composition", "subject_environment_relationship",
    ),
    EvidenceRule(
        "Human Behavior", "human.motivated-action",
        ("identity", "current_action", "previous_moment", "reason", "attention", "body_state"),
        "Preserve the approved identity separately from action. Connect current action to "
        "the previous moment, reason for being here, attention and a natural bodily response "
        "when specified. Keep unknown context unresolved or explicitly proposed for confirmation; "
        "do not invent biographical facts, a new face or a different selected action.",
        "Inspect whether gaze, hand activity, weight shift, posture and expression support "
        "the stated action and attention. Identity descriptors alone do not explain behavior. "
        "A static pose is valid when deliberately selected.",
        "human_capture", "Reality", "motivated_action",
        ("Flea market, only if compatible: her friend stopped at an old book; she leans "
         "slightly to read its cover, attention on the book, unaware of the camera.",),
    ),
    EvidenceRule(
        "Environment", "environment.usage-evidence",
        ("objects", "messiness", "usage_history", "human_traces"),
        "Use concrete objects, arrangement, usage history and human traces compatible with "
        "the selected location. Mark additions as proposed, never observed evidence. "
        "Clean studios and deliberate order are valid; do not add clutter indiscriminately.",
        "Check whether object placement and use traces support the location and activity "
        "without contradictions or repeated decorative props. The adjective authentic "
        "alone is not evidence; missing source pixels remain unverified.",
        "spatial_light_integration", "Scene", "usage_traces",
        ("Flea market, optional: uneven book stacks, old price stickers on books, "
         "cardboard boxes and objects partly occluding one another.",),
    ),
    EvidenceRule(
        "Imperfection", "imperfection.causal-and-safe",
        ("camera_imperfection", "human_imperfection", "material_imperfection",
         "scene_imperfection"),
        "Imperfection may be none. If explicitly compatible with the direction and locks, "
        "use small causal variation in capture, human posture, material drape or scene "
        "arrangement. Do not add blur or grain as a realism filter. Preserve identity, "
        "garment color, print, text, silhouette and condition; never add stains, wear or "
        "faded print to the canonical garment without source evidence and permission.",
        "Assess camera, human, material and scene variation separately and explain its "
        "physical cause. Reject filter-only realism and any product/identity lock damage. "
        "No imperfection is required; fine product detail must stay readable.",
        "human_capture", "Reality", "causal_imperfection",
        (
            "Camera, conditional: minor autofocus inconsistency, exposure variation or "
            "motion softness away from required product detail.",
            "Human, conditional: uneven expression, posture asymmetry or loose hair; "
            "preserve approved identity.",
            "Material, conditional: action-driven fabric wrinkles or observed texture "
            "variation. Faded print is evidence-only, never a generic realism instruction.",
            "Scene, conditional: compatible clutter, incidental objects or uneven arrangement.",
        ),
    ),
)


def evidence_rules_snapshot() -> dict[str, Any]:
    """Return detached JSON values suitable for immutable Registry storage."""
    payload = {
        "schema_version": RULES_VERSION,
        "source": {
            "kind": "USER_REPORTED_EXPERIMENT",
            "label": "Nano Banana realism observations supplied on 2026-10-13",
            "validation": "HEURISTIC_NOT_INDEPENDENTLY_PIXEL_VERIFIED",
        },
        "boundary": "GENERATION_GUIDANCE_AND_REVIEW_CRITERIA_NOT_QUALITY_APPROVAL",
        "rules": [
            {**asdict(rule), "context_fields": list(rule.context_fields),
             "optional_patterns": list(rule.optional_patterns)}
            for rule in RULES
        ],
    }
    return {**payload, "content_hash": canonical_hash(payload)}


def compile_reality_decisions(direction: Mapping[str, str]) -> list[dict[str, str]]:
    """Enrich existing string-valued Reality entries without changing their schema."""
    snapshot = evidence_rules_snapshot()
    decisions = (
        direction.get("camera") or "eye-level medium frame",
        "single soft side light", "garment fully readable",
        direction.get("behavior", ""), direction.get("scene", ""), "none",
    )
    return [
        {
            "dimension": rule.dimension,
            "decision": decision,
            "evidence": "PROPOSED_FAKE",
            "rule_id": rule.rule_id,
            "rules_version": RULES_VERSION,
            "rules_hash": snapshot["content_hash"],
            "required_context": ", ".join(rule.context_fields),
            "generation_constraint": rule.generation_constraint,
            "judgment_standard": rule.judgment_standard,
            "review_axis": rule.review_axis,
            "revision_module": rule.revision_module,
            "causal_variable": rule.causal_variable,
        }
        for rule, decision in zip(RULES, decisions, strict=True)
    ]


def render_reality_constraints(reality: Sequence[Mapping[str, str]]) -> str:
    """Only render rules already carried by this package, never today's catalog."""
    lines = [
        f"{item['dimension']}: {item['generation_constraint']}"
        for item in reality
        if item.get("generation_constraint")
        and item.get("decision", "").strip().upper() not in {"N/A", "NA"}
    ]
    return "\n".join(lines)


def compile_photographic_cues(
    reality: Sequence[Mapping[str, str]], direction: Mapping[str, str],
) -> list[dict[str, str]]:
    """Compile proposed physical relationships, preserving inherited frozen cues."""
    result = [dict(item) for item in reality]
    camera = next(item for item in result if item["dimension"] == "Camera")
    if camera.get("compiler_version"):
        return result
    human = next(item for item in result if item["dimension"] == "Human Behavior")
    light = next(item for item in result if item["dimension"] == "Lighting")
    camera_text = camera["decision"].lower()
    mode = direction.get("photo_intent") or (
        "mirror_self_capture" if "mirror" in camera_text and "self" in camera_text
        else "self_capture_front" if "front" in camera_text and "self" in camera_text
        else "casual_portrait"
    )
    if mode not in {
        "candid", "casual_portrait", "identity_snapshot", "mirror_self_capture",
        "self_capture_front", "product_only",
    }:
        raise ValueError("unsupported photographic intent")
    camera.update(compiler_version=COMPILER_VERSION, capture_mode=mode)
    if mode == "product_only" or human["decision"].strip().upper() in {"N/A", "NA"}:
        camera["capture_mode"] = "product_only"
        human.update(
            decision="N/A", reason="Product-only direction: no human subject is requested.",
        )
    else:
        action = human["decision"]
        missing = []
        if mode == "candid":
            context = ("operator", "capture_reason", "attention", "body_state")
            missing = [key for key in context if not direction.get(key, "").strip()]
            intent = "; ".join(direction[key] for key in context if direction.get(key))
        elif mode == "mirror_self_capture":
            intent = "the subject records the outfit in the mirror"
        elif mode == "self_capture_front":
            intent = "the subject records the outfit with the front-facing camera"
        else:
            intent = "the subject knows the outfit is being photographed"
        if re.search(r"\b(walk|walking|step|stride)\b", action.lower()):
            relation = "weight transfers onto the supporting leg"
            visible = "the hem and sleeves fold with that stride"
        elif re.search(r"\b(seat|seated|sit|sitting)\b", action.lower()):
            relation = "the torso bends at the seated waist"
            visible = "garment folds collect at the bend rather than lying flat"
        else:
            relation = "gravity pulls the garment from its shoulder support"
            visible = "fabric hangs below the shoulders and folds at the selected posture"
        if mode == "candid" and direction.get("body_state"):
            relation = direction["body_state"]
        if mode == "mirror_self_capture":
            relation = "the holding hand supports the phone in front of the mirror"
            visible = "the phone and holding hand share the same reflection"
        elif mode == "self_capture_front":
            relation = "the holding arm establishes the front-camera viewpoint"
            visible = "the holding phone stays outside its own image"
        trigger = f"During {action}, {intent}"
        cue = f"{trigger}; {relation}, so {visible}."
        camera.update(
            causal_trigger=trigger, physical_relation=relation, visible_result=visible,
            compiled_cue=cue, unresolved_context=", ".join(missing),
        )
    if light["decision"].strip().upper() not in {"N/A", "NA"}:
        trigger = f"Under {light['decision']}"
        relation = "garment folds interrupt the incoming light"
        visible = "crease shadows follow fold depth on the same fabric"
        light.update(
            causal_trigger=trigger, physical_relation=relation, visible_result=visible,
            compiled_cue=f"{trigger}, {relation}, so {visible}.",
        )
    return result


def render_photographic_cues(reality: Sequence[Mapping[str, str]]) -> str:
    camera = next(item for item in reality if item["dimension"] == "Camera")
    if camera.get("compiler_version") != COMPILER_VERSION:
        return render_reality_constraints(reality)
    cues = [item["compiled_cue"] for item in reality if item.get("compiled_cue")]
    return f"Capture mode: {camera['capture_mode']}.\n" + "\n".join(cues[:2])


def registry_evidence_rules(reality: Sequence[Mapping[str, str]]) -> dict[str, Any] | None:
    """Bind new packages to a complete matching knowledge snapshot."""
    tagged = [item for item in reality if item.get("rules_version")]
    if not tagged:
        return None
    snapshot = evidence_rules_snapshot()
    if len(tagged) != 6 or any(
        item.get("rules_version") != snapshot["schema_version"]
        or item.get("rules_hash") != snapshot["content_hash"]
        for item in tagged
    ):
        raise ValueError("Reality rules do not match the authored knowledge version")
    return snapshot
