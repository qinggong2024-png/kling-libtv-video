import json

import pytest
from libtv_agent.api.image_generations import _public_error


@pytest.mark.parametrize("code", ["WAVESPEED_REQUEST_FAILED", "token=private-code"])
def test_public_error_never_exposes_provider_text_or_arbitrary_details(code):
    result = _public_error(
        {
            "code": code,
            "message": "token=private-key https://cdn.test/a?sig=private-signature",
            "retryable": False,
            "details": {
                "submitted": True,
                "prompt": "private-prompt",
                "reference": "data:image/png;base64,private-image",
            },
        }
    )
    assert "private" not in json.dumps(result)
    assert result["retryable"] is False
    assert result["details"] == {"submitted": True}
    assert result["code"] == (code if code.startswith("WAVESPEED") else "IMAGE_GENERATION_FAILED")


def test_no_error_stays_absent():
    assert _public_error(None) is None
