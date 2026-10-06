import pytest
from fastapi import HTTPException
from libtv_agent.api.dependencies import can_review_across_owners, require_review_write
from libtv_agent.domain.enums import UserRole
from libtv_agent.domain.models import User
from libtv_agent.domain.schemas import FinalApprovalRequest


def test_auditors_are_read_only_for_quality_review_writes() -> None:
    actor = User(role=UserRole.AUDITOR)

    with pytest.raises(HTTPException) as captured:
        require_review_write(actor)

    assert captured.value.status_code == 403
    assert captured.value.detail["code"] == "PERMISSION_DENIED"


@pytest.mark.parametrize(
    ("role", "expected"),
    [
        (UserRole.USER, False),
        (UserRole.OPERATOR, True),
        (UserRole.ADMIN, True),
        (UserRole.AUDITOR, False),
    ],
)
def test_only_operations_roles_can_review_across_owners(
    role: UserRole, expected: bool
) -> None:
    assert can_review_across_owners(User(role=role)) is expected


def test_rejected_video_review_requires_a_reason() -> None:
    with pytest.raises(ValueError, match="REJECTED requires a review reason"):
        FinalApprovalRequest(
            decision="REJECTED",
            product_fidelity_pass=False,
            editing_assembly_pass=False,
            human_critical_pass=False,
            human_review_seconds=5,
            expected_state_version=3,
        )
