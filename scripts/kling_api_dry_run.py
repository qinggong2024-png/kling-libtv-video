from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend" / "src"))

from libtv_agent.adapters.kling_official_api import KlingOfficialApiAdapter  # noqa: E402
from libtv_agent.adapters.video_provider import VideoGenerationRequest  # noqa: E402
from libtv_agent.config import Settings  # noqa: E402

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png"}


def _images(directory: Path | None) -> tuple[Path, ...]:
    if directory is None:
        return ()
    if not directory.is_dir():
        raise ValueError(f"image directory does not exist: {directory}")
    return tuple(
        sorted(
            (
                path.resolve()
                for path in directory.iterdir()
                if path.suffix.lower() in IMAGE_SUFFIXES
            ),
            key=lambda path: path.name.casefold(),
        )
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate and render a redacted Kling API 2.0 request without network access."
    )
    parser.add_argument("--storyboard-dir", type=Path, required=True)
    parser.add_argument("--product-dir", type=Path)
    prompt = parser.add_mutually_exclusive_group(required=True)
    prompt.add_argument("--prompt")
    prompt.add_argument("--prompt-file", type=Path)
    parser.add_argument("--duration", type=int, default=10)
    parser.add_argument("--aspect-ratio", default="9:16")
    parser.add_argument("--resolution", choices=("720p", "1080p", "4k"), default="1080p")
    parser.add_argument("--audio", choices=("native", "off"), default="off")
    parser.add_argument("--single-shot", action="store_true")
    return parser.parse_args()


async def _run(args: argparse.Namespace) -> None:
    prompt = (
        args.prompt_file.read_text(encoding="utf-8")
        if args.prompt_file is not None
        else str(args.prompt)
    )
    storyboards = _images(args.storyboard_dir)
    products = _images(args.product_dir)
    external_id = hashlib.sha256(
        json.dumps(
            {
                "prompt": prompt,
                "storyboards": [path.name for path in storyboards],
                "products": [path.name for path in products],
            },
            ensure_ascii=False,
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    settings = Settings(
        app_env="development",
        kling_provider_backend="api",
        kling_api_enabled=False,
        kling_api_key=None,
        _env_file=None,
    )
    adapter = KlingOfficialApiAdapter(settings)
    request = VideoGenerationRequest(
        prompt=prompt,
        model=settings.kling_api_model,
        image_paths=storyboards,
        product_reference_paths=products,
        duration=args.duration,
        aspect_ratio=args.aspect_ratio,
        resolution=args.resolution,
        audio=args.audio,
        multi_shot=not args.single_shot,
        external_task_id=external_id,
    )
    payload = await adapter.build_request_payload(request)
    summary = await adapter.request_summary(request)
    summary["requestShape"] = {
        "contentTypes": [item["type"] for item in payload["contents"]],
        "contentIds": [item.get("id") for item in payload["contents"] if item.get("id")],
        "settings": payload["settings"],
        "options": payload["options"],
    }
    summary["networkCalled"] = False
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def main() -> None:
    try:
        asyncio.run(_run(_parse_args()))
    except (OSError, ValueError) as exc:
        raise SystemExit(f"dry-run failed: {exc}") from exc


if __name__ == "__main__":
    main()
