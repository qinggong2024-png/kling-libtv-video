import logging

import pytest
from libtv_agent.services.idempotency import (
    IdempotencyConflictError,
    IdempotencyInProgressError,
    load_idempotent_response,
    store_idempotent_response,
)
from test_state_and_points import session  # noqa: F401


async def test_idempotency_outcomes_emit_no_request_identity(session, caplog, monkeypatch):  # noqa: F811
    caplog.set_level(logging.INFO, logger="libtv_agent.services.idempotency")
    args = dict(
        tenant_id="private-user",
        operation_type="CONFIRM:private-task",
        key="private-key",
        payload={"prompt": "private-prompt"},
    )
    assert await load_idempotent_response(session, **args) is None
    await session.commit()

    async def no_sleep(_delay):
        pass

    monkeypatch.setattr("libtv_agent.services.idempotency.asyncio.sleep", no_sleep)
    with pytest.raises(IdempotencyInProgressError):
        await load_idempotent_response(session, **args)
    await store_idempotent_response(
        session, **args, response_status=200, response_body={"result": "private-result"}
    )
    await session.commit()
    assert await load_idempotent_response(session, **args) == (200, {"result": "private-result"})
    with pytest.raises(IdempotencyConflictError):
        await load_idempotent_response(session, **{**args, "payload": {"prompt": "other"}})
    records = [r for r in caplog.records if r.name == "libtv_agent.services.idempotency"]
    assert [r.getMessage() for r in records] == [
        "idempotency.in_progress",
        "idempotency.replay",
        "idempotency.conflict",
    ]
    assert all(r.count == 1 for r in records)
    assert all("private" not in str(r.__dict__) for r in records)
