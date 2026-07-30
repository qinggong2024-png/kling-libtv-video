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


def _first_value(data: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = data.get(key)
        if value is not None:
            return value
    return None


def _media_urls(value: Any, *url_keys: str) -> list[str]:
    if isinstance(value, str):
        return [value] if value else []
    if isinstance(value, dict):
        url = _first_value(value, *url_keys)
        return [str(url)] if url else []
    if isinstance(value, list):
        urls: list[str] = []
        for item in value:
            urls.extend(_media_urls(item, *url_keys))
        return urls
    return []


def _video_url(value: Any) -> str | None:
    urls = _media_urls(value, "video_url", "videoUrl", "url")
    return urls[0] if urls else None


def normalize_element(
    value: Any,
    *,
    task: dict[str, Any] | None = None,
) -> dict[str, Any]:
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
    task_data = task or {}
    task_result = data.get("task_result") or data.get("taskResult")
    if isinstance(task_result, dict):
        elements = task_result.get("elements")
        if isinstance(elements, list) and elements and isinstance(elements[0], dict):
            return normalize_element(elements[0], task=data)

    element_id = _first_value(data, "element_id", "elementId", "id")
    if element_id is None:
        element_id = _first_value(data, "task_id", "taskId")
    if element_id is None:
        element_id = _first_value(task_data, "task_id", "taskId", "id")
    if not isinstance(element_id, (str, int)) or not str(element_id):
        raise KlingElementError(
            "KLING_ELEMENT_RESPONSE_INVALID",
            "Kling element response is missing id",
            status_code=502,
        )
    image_value = _first_value(
        data,
        "image_urls",
        "imageUrls",
        "element_image_urls",
        "elementImageUrls",
        "images",
        "image",
        "image_url",
        "imageUrl",
        "element_image_url",
        "elementImageUrl",
    )
    video_value = _first_value(
        data,
        "video_url",
        "videoUrl",
        "element_video_url",
        "elementVideoUrl",
        "video",
    )
    return {
        "id": str(element_id),
        "name": _first_value(data, "name", "element_name", "elementName"),
        "description": _first_value(
            data,
            "description",
            "element_description",
            "elementDescription",
        ),
        "status": str(
            _first_value(
                data,
                "status",
                "element_status",
                "elementStatus",
                "task_status",
                "taskStatus",
            )
            or _first_value(task_data, "task_status", "taskStatus", "status")
            or "unknown"
        ),
        "imageUrls": _media_urls(image_value, "image_url", "imageUrl", "url"),
        "videoUrl": _video_url(video_value),
        "voiceId": _first_value(
            data,
            "voice_id",
            "voiceId",
            "element_voice_id",
            "elementVoiceId",
        ),
        "createdAt": _first_value(data, "created_at", "createdAt")
        or _first_value(task_data, "created_at", "createdAt"),
        "updatedAt": _first_value(data, "updated_at", "updatedAt")
        or _first_value(task_data, "updated_at", "updatedAt"),
        "raw": data,
    }


def _normalize_list_items(items: list[Any]) -> tuple[list[dict[str, Any]], int]:
    normalized: list[dict[str, Any]] = []
    expanded_count = 0
    for item in items:
        if not isinstance(item, dict):
            normalized.append(normalize_element(item))
            continue
        task_result = item.get("task_result") or item.get("taskResult")
        elements = task_result.get("elements") if isinstance(task_result, dict) else None
        if isinstance(elements, list) and elements:
            normalized.extend(normalize_element(element, task=item) for element in elements)
            expanded_count += len(elements) - 1
        else:
            normalized.append(normalize_element(item))
    return normalized, expanded_count


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
    response_total: Any = None
    if isinstance(result, list):
        items_value = result
    elif isinstance(result, dict):
        data = result.get("data", result)
        if isinstance(data, list):
            items_value = data
            response_total = _first_value(result, "total", "count")
        elif isinstance(data, dict):
            items_value = data.get("items") or data.get("elements") or []
            response_total = data.get("total")
            if response_total is None:
                response_total = data.get("count")
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
    items, expanded_count = _normalize_list_items(items_value)
    total = (
        int(response_total) + expanded_count
        if response_total is not None
        else len(items)
    )
    return {
        "items": items,
        "pageNum": page_num,
        "pageSize": page_size,
        "total": total,
        "official": official,
    }


async def delete_element(adapter: Any, element_id: str) -> None:
    await _invoke(adapter, "delete_element", element_id)
