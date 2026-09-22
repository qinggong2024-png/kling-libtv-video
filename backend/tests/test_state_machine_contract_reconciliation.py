"""Keep backend/contracts/state-machines.json honest against aggregate_parent_phase.

The contract drifted once already. Version 4.3.2-phase1 declared twelve real edges
illegal, among them the two most common ones the system actually walks
(GENERATING -> DELIVERABLE and GENERATING -> AWAITING_FINAL_APPROVAL), because the
table described a DOWNLOADING -> VALIDATING -> AWAITING_FINAL_APPROVAL pipeline that
aggregate_parent_phase never produces. That is why assert_transition was never wired
into the write path: wiring it would have rejected normal traffic.

These tests enumerate every observable outcome of the aggregate and every
single-step transition it can produce, then require the contract to cover them.
If the aggregate changes without the contract being updated, this fails loudly
instead of silently re-opening the same drift.

Enumeration cost: 840 single-variant worlds plus 100 two-variant worlds, each
mutated one axis at a time.
"""

import itertools

import pytest
from libtv_agent.domain.enums import (
    DownloadStatus,
    GenerationStatus,
    ParentTaskPhase,
    QualityDecisionStatus,
    ValidationStatus,
)
from libtv_agent.services.state_machine import aggregate_parent_phase, load_state_machines

AXIS_ORDER = (
    "generation_status",
    "download_status",
    "validation_status",
    "final_approval_status",
)
AXIS_VALUES: tuple[tuple[object, ...], ...] = (
    tuple(GenerationStatus),
    tuple(DownloadStatus),
    tuple(ValidationStatus),
    tuple(QualityDecisionStatus),
)

# One representative tuple per behavioural category, used to build two-variant
# worlds. Two-variant worlds are what make PARTIALLY_DELIVERABLE reachable.
CATEGORY_SAMPLES = (
    (
        GenerationStatus.PENDING,
        DownloadStatus.NOT_READY,
        ValidationStatus.NOT_READY,
        QualityDecisionStatus.PENDING,
    ),
    (
        GenerationStatus.RUNNING,
        DownloadStatus.DOWNLOADING,
        ValidationStatus.TECHNICAL_CHECKING,
        QualityDecisionStatus.PENDING,
    ),
    (
        GenerationStatus.SUCCEEDED,
        DownloadStatus.READY,
        ValidationStatus.PASSED,
        QualityDecisionStatus.PENDING,
    ),
    (
        GenerationStatus.SUCCEEDED,
        DownloadStatus.READY,
        ValidationStatus.PASSED,
        QualityDecisionStatus.APPROVED,
    ),
    (
        GenerationStatus.SUCCEEDED,
        DownloadStatus.READY,
        ValidationStatus.PASSED,
        QualityDecisionStatus.REJECTED,
    ),
    (
        GenerationStatus.SUCCEEDED,
        DownloadStatus.READY,
        ValidationStatus.WARNING,
        QualityDecisionStatus.PENDING,
    ),
    (
        GenerationStatus.PARTIAL,
        DownloadStatus.READY,
        ValidationStatus.PASSED,
        QualityDecisionStatus.PENDING,
    ),
    (
        GenerationStatus.FAILED,
        DownloadStatus.FAILED,
        ValidationStatus.FAILED,
        QualityDecisionStatus.PENDING,
    ),
    (
        GenerationStatus.UNKNOWN,
        DownloadStatus.FAILED,
        ValidationStatus.MANUAL_REVIEW,
        QualityDecisionStatus.PENDING,
    ),
    (
        GenerationStatus.SUCCEEDED,
        DownloadStatus.FAILED,
        ValidationStatus.FAILED,
        QualityDecisionStatus.PENDING,
    ),
)


class _Variant:
    """Duck-typed stand-in for GenerationVariant (only the four aggregate axes matter)."""

    __slots__ = AXIS_ORDER

    def __init__(self, values: tuple[object, ...]) -> None:
        for name, value in zip(AXIS_ORDER, values, strict=True):
            setattr(self, name, value)


def _worlds() -> list[tuple[tuple[object, ...], ...]]:
    singles = [(item,) for item in itertools.product(*AXIS_VALUES)]
    pairs = [pair for pair in itertools.product(CATEGORY_SAMPLES, repeat=2)]
    return singles + pairs


def _phase_of(world: tuple[tuple[object, ...], ...]) -> str:
    return aggregate_parent_phase([_Variant(item) for item in world]).value


def _observed_outputs() -> set[str]:
    return {_phase_of(world) for world in _worlds()}


def _observed_transitions() -> set[tuple[str, str]]:
    edges: set[tuple[str, str]] = set()
    for world in _worlds():
        origin = _phase_of(world)
        for position, variant in enumerate(world):
            for axis_index, values in enumerate(AXIS_VALUES):
                for replacement in values:
                    if replacement == variant[axis_index]:
                        continue
                    moved_variant = list(variant)
                    moved_variant[axis_index] = replacement
                    moved_world = list(world)
                    moved_world[position] = tuple(moved_variant)
                    target = _phase_of(tuple(moved_world))
                    if target != origin:
                        edges.add((origin, target))
    return edges


def test_empty_variant_set_still_aggregates_to_generating() -> None:
    assert aggregate_parent_phase([]) is ParentTaskPhase.GENERATING


def test_contract_declares_every_phase_the_aggregate_can_return() -> None:
    declared = set(load_state_machines()["reconciliation"]["aggregateOutputs"])
    assert _observed_outputs() <= declared, (
        "aggregate_parent_phase returns a phase the contract does not declare"
    )


def test_contract_declares_every_aggregate_transition() -> None:
    transitions = load_state_machines()["parentTask"]["transitions"]
    missing = sorted(
        (origin, target)
        for origin, target in _observed_transitions()
        if target not in transitions.get(origin, [])
    )
    assert not missing, (
        f"state-machines.json is missing {len(missing)} transition(s) the aggregate "
        f"actually produces: {missing}"
    )


def test_reserved_phases_are_declared_but_never_produced() -> None:
    reconciliation = load_state_machines()["reconciliation"]
    reserved = set(reconciliation["reservedPhases"])
    assert reserved, "reservedPhases must document the design-only phases"
    assert not (reserved & _observed_outputs()), (
        "a phase is listed as reserved but the aggregate now returns it; "
        "update reservedPhases and give it real transitions"
    )


def test_reserved_phases_still_have_a_transition_key() -> None:
    # test_machine_contract_matches_enums requires one key per enum value, so the
    # reserved phases must keep their key even though nothing enters them.
    transitions = set(load_state_machines()["parentTask"]["transitions"])
    assert set(load_state_machines()["reconciliation"]["reservedPhases"]) <= transitions


def test_cancelled_is_the_only_terminal_phase() -> None:
    contract = load_state_machines()["parentTask"]
    assert contract["terminal"] == [ParentTaskPhase.CANCELLED.value]
    assert contract["transitions"][ParentTaskPhase.CANCELLED.value] == []
    for resting in contract["restingStates"]:
        assert contract["transitions"][resting], (
            f"{resting} is listed as a resting state but has no outgoing transition; "
            "aggregate_parent_phase can leave it"
        )


def test_every_transition_target_is_a_declared_phase() -> None:
    phases = {value.value for value in ParentTaskPhase}
    for origin, targets in load_state_machines()["parentTask"]["transitions"].items():
        for target in targets:
            assert target in phases, f"{origin} -> {target} targets an unknown phase"
        assert origin not in targets, f"{origin} declares a self transition"


@pytest.mark.parametrize("phase", [value.value for value in ParentTaskPhase])
def test_no_real_transition_is_rejected(phase: str) -> None:
    """Every aggregate-produced edge must survive assert_transition.

    This is the guard that was missing: the old contract would have raised here.
    """
    from libtv_agent.services.state_machine import assert_transition

    transitions = load_state_machines()["parentTask"]["transitions"]
    for target in transitions[phase]:
        assert_transition("parentTask", phase, target)
