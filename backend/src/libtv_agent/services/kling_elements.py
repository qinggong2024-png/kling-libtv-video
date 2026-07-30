from __future__ import annotations

import inspect
from typing import Any

from libtv_agent.adapters.kling_official_api import KlingElementCreateRequest


class KlingElementError(RuntimeError):
    def __init__(self, code: str, message: str, *, status_code: int = 409) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code


async def _invoke(adapter: Any, method_name: str, *args: Any, **kwargs: Any) -> Any:
    method = getattr(adapter, method_name, None)
    if not callable(method):
        raise KlingElementError(
            "KLING_ELEMENT_UNSUPPORTED",
            f"Kling provider does not support {method_name}",
            status_code=501,
        )
    try:
        result = method(*args, **kwargs)
        return await result if inspect.isawaitable(result) else result
    except KlingElementError:
        raise
    except Exception as exc:
        code = str(getattr(exc, "code", "KLING_ELEMENT_REQUEST_FAILED"))
        status_code = 503 if bool(getattr(exc, "retryable", False)) else 409
        raise KlingElementError(code, str(exc), status_code=status_code) from exc


def normalize_element(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise KlingElementError(
            "KLING_ELEMENT_RESPONSE_INVALID",
            "Kling element response must be an object",
            status_code=502,
        )
    data = value.get("data", value)
    if not isinstance(data, dict):
        raise KlingElementError(
            "KLING_ELEMENT_RESPONSE_INVALID",
            "Kling element response data must be an object",
            status_code=502,
        )
    element_id = (
        data.get("id")
        or data.get("element_id")
        or data.get("elementId")
        or data.get("task_id")
        or data.get("taskId")
    )
    if not isinstance(element_id, str) or not element_id:
        raise KlingElementError(
            "KLING_ELEMENT_RESPONSE_INVALID",
            "Kling element response is missing id",
            status_code=502,
        )
    return {
        "id": element_id,
        "name": data.get("name"),
        "description": data.get("description"),
        "status": str(data.get("status") or "unknown"),
        "imageUrls": list(data.get("image_urls") or data.get("imageUrls") or []),
        "videoUrl": data.get("video_url") or data.get("videoUrl"),
        "voiceId": data.get("voice_id") or data.get("voiceId"),
        "createdAt": data.get("created_at") or data.get("createdAt"),
        "updatedAt": data.get("updated_at") or data.get("updatedAt"),
        "raw": data,
    }


async def create_element(adapter: Any, payload: dict[str, Any]) -> dict[str, Any]:
    image_references = tuple(payload.get("imageReferences") or ())
    video_references = tuple(payload.get("videoReferences") or ())
    if bool(image_references) == bool(video_references):
        raise KlingElementError(
            "KLING_INVALID_INPUT",
            "exactly one of imageReferences or videoReferences is required",
            status_code=422,
        )
    request = KlingElementCreateRequest(
        element_name=str(payload["name"]),
        element_description=str(payload["description"]),
        reference_type="image_refer" if image_references else "video_refer",
        frontal_image=image_references[0] if image_references else None,
        refer_images=image_references[1:] if image_references else (),
        refer_videos=video_references,
        element_voice_id=payload.get("voiceId"),
        tag_ids=tuple(payload.get("tagIds") or ()),
        callback_url=payload.get("callbackUrl"),
        external_task_id=payload.get("externalId"),
    )
    return normalize_element(await _invoke(adapter, "create_element", request))


async def get_element(adapter: Any, element_id: str) -> dict[str, Any]:
    return normalize_element(await _invoke(adapter, "query_element", task_id=element_id))


async def list_elements(
    adapter: Any,
    *,
    page_num: int,
    page_size: int,
    official: bool,
) -> dict[str, Any]:
    result = await _invoke(
        adapter,
        "list_elements",
        page_num=page_num,
        page_size=page_size,
        official=official,
    )
    if isinstance(result, list):
        items_value, total = result, len(result)
    elif isinstance(result, dict):
        data = result.get("data", result)
        if isinstance(data, list):
            items_value, total = data, len(data)
        elif isinstance(data, dict):
            items_value = data.get("items") or data.get("elements") or []
            total = data.get("total") or data.get("count") or len(items_value)
        else:
            raise KlingElementError(
                "KLING_ELEMENT_RESPONSE_INVALID",
                "Kling element list response data must be an object or array",
                status_code=502,
            )
    else:
        raise KlingElementError(
            "KLING_ELEMENT_RESPONSE_INVALID",
            "Kling element list response must be an object or array",
            status_code=502,
        )
    if not isinstance(items_value, list):
        raise KlingElementError(
            "KLING_ELEMENT_RESPONSE_INVALID",
            "Kling element list items must be an array",
            status_code=502,
        )
    return {
        "items": [normalize_element(item) for item in items_value],
        "pageNum": page_num,
        "pageSize": page_size,
        "total": int(total),
        "official": official,
    }


async def delete_element(adapter: Any, element_id: str) -> None:
    await _invoke(adapter, "delete_element", element_id)
