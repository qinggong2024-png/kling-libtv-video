from __future__ import annotations

import argparse
import asyncio
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend" / "src"))

from libtv_agent.adapters.wavespeed import (  # noqa: E402
    WAVESPEED_TERMINAL_STATUSES,
    WaveSpeedAdapter,
    WaveSpeedError,
    build_generation_payload,
)
from libtv_agent.config import Settings  # noqa: E402
from libtv_agent.services.wavespeed_config import load_wavespeed_admin_config  # noqa: E402

PAID_CONFIRMATION = "I_ACCEPT_WAVESPEED_CHARGES"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run one paid WaveSpeed image prediction")
    parser.add_argument("--model", choices=("gpt-image-2", "nano-banana-2"), required=True)
    parser.add_argument("--mode", choices=("edit", "text-to-image"), required=True)
    parser.add_argument("--prompt-file", type=Path, required=True)
    parser.add_argument("--image", type=Path, action="append", default=[])
    parser.add_argument("--aspect-ratio", default="9:16")
    parser.add_argument("--resolution", choices=("1k", "2k", "4k"), default="2k")
    parser.add_argument("--quality", choices=("low", "medium", "high"), default="medium")
    parser.add_argument("--output-format", choices=("png", "jpeg"), default="png")
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/wavespeed"))
    parser.add_argument("--timeout-seconds", type=float, default=1800.0)
    parser.add_argument("--execute-paid", action="store_true")
    parser.add_argument("--confirm", default="")
    return parser.parse_args()


def require_paid_confirmation(args: argparse.Namespace) -> None:
    if args.execute_paid and args.confirm == PAID_CONFIRMATION:
        return
    raise SystemExit(
        "Paid WaveSpeed submission blocked. Pass --execute-paid "
        f"--confirm {PAID_CONFIRMATION} to continue."
    )


def safe_filename(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-.")
    return normalized[:100] or "prediction"


def download_output(url: str, destination: Path) -> None:
    request = Request(url, headers={"User-Agent": "libtv-agent-wavespeed-test/1"})
    with urlopen(request, timeout=300) as response:  # noqa: S310 - provider URL is validated upstream
        content_type = response.headers.get_content_type()
        if content_type not in {"image/jpeg", "image/png", "image/webp"}:
            raise RuntimeError(f"unexpected WaveSpeed output content type: {content_type}")
        content = response.read()
    if not content:
        raise RuntimeError("WaveSpeed output download was empty")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(content)


def output_suffix(url: str, output_format: str) -> str:
    suffix = Path(urlsplit(url).path).suffix.lower()
    if suffix in {".jpg", ".jpeg", ".png", ".webp"}:
        return suffix
    return ".jpg" if output_format == "jpeg" else ".png"


async def run(args: argparse.Namespace) -> None:
    require_paid_confirmation(args)
    if not args.prompt_file.is_file():
        raise SystemExit(f"Prompt file was not found: {args.prompt_file}")
    if args.mode == "edit" and not args.image:
        raise SystemExit("Edit mode requires at least one --image")
    if args.mode == "text-to-image" and args.image:
        raise SystemExit("Text-to-image mode does not accept --image")

    settings = Settings()
    load_wavespeed_admin_config(settings)
    if not settings.wavespeed_enabled:
        raise SystemExit("WaveSpeed is disabled; enable it in the administrator provider page")
    if not settings.effective_wavespeed_api_key:
        raise SystemExit("WaveSpeed API Key is not configured")

    adapter = WaveSpeedAdapter(settings)
    prompt = args.prompt_file.read_text(encoding="utf-8").strip()
    image_urls: list[str] = []
    for index, image_path in enumerate(args.image, 1):
        print(f"Uploading reference image {index}/{len(args.image)}: {image_path.name}")
        image_urls.append(await adapter.upload_media(image_path))

    model_id, payload = build_generation_payload(
        provider=args.model,
        mode=args.mode,
        prompt=prompt,
        images=image_urls,
        aspect_ratio=args.aspect_ratio,
        resolution=args.resolution,
        quality=args.quality,
        output_format=args.output_format,
    )
    submission = await adapter.submit_prediction(model_id, payload)
    print(f"Submitted taskId={submission.task_id} modelId={submission.model_id}")

    loop = asyncio.get_running_loop()
    deadline = loop.time() + args.timeout_seconds
    interval = 2.0
    while True:
        if loop.time() >= deadline:
            raise TimeoutError(f"Client wait timed out for task {submission.task_id}")
        prediction = await adapter.get_prediction(submission.task_id)
        print(f"status={prediction.status}")
        if prediction.status in WAVESPEED_TERMINAL_STATUSES:
            break
        await asyncio.sleep(interval)
        interval = min(30.0, interval * 1.5)

    if prediction.status != "completed":
        raise WaveSpeedError(
            "WAVESPEED_TASK_FAILED",
            prediction.error or f"WaveSpeed task ended with {prediction.status}",
            task_id=prediction.task_id,
            model_id=prediction.model_id or model_id,
        )

    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    task_token = safe_filename(prediction.task_id)
    model_token = safe_filename(args.model)
    for index, url in enumerate(prediction.outputs, 1):
        suffix = output_suffix(url, args.output_format)
        filename = f"{model_token}-{timestamp}-{task_token}-{index}{suffix}"
        destination = args.output_dir / filename
        await asyncio.to_thread(download_output, url, destination)
        print(f"output[{index}]={url}")
        print(f"saved[{index}]={destination.resolve()}")


def main() -> None:
    args = parse_args()
    try:
        asyncio.run(run(args))
    except (WaveSpeedError, OSError, TimeoutError, ValueError) as exc:
        raise SystemExit(f"WaveSpeed test failed: {exc}") from exc


if __name__ == "__main__":
    main()
