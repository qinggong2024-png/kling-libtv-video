import pytest
from libtv_agent.services.auth import PasswordService


def test_argon2_password_round_trip() -> None:
    service = PasswordService()
    password_hash = service.hash("correct horse battery staple")

    assert password_hash.startswith("$argon2id$")
    assert service.verify(password_hash, "correct horse battery staple")
    assert not service.verify(password_hash, "wrong password")


def test_password_minimum_length() -> None:
    with pytest.raises(ValueError, match="12"):
        PasswordService().hash("too-short")
