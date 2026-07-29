import argparse
import asyncio
import json
import os
from dataclasses import asdict
from pathlib import Path

from libtv_agent.adapters.libtv import LibTVError, RealLibTVAdapter


def write_terminal_result(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=True), encoding="utf-8")
    temporary.replace(path)


async def execute(args: argparse.Namespace) -> int:
    if not args.nonce or os.environ.get("LIBTV_COMMAND_NONCE") != args.nonce:
        write_terminal_result(
            args.result_file,
            {
                "ok": False,
                "commandId": args.command_id,
                "nonce": args.nonce,
                "error": "command-host nonce mismatch",
            },
        )
        return 2
    adapter = RealLibTVAdapter(
        args.libtv_executable,
        execution_mode=os.environ.get("LIBTV_EXECUTION_MODE", "dry-run"),
        paid_generation_enabled=os.environ.get("LIBTV_PAID_GENERATION_ENABLED") == "true",
        paid_generation_confirmation=os.environ.get("LIBTV_PAID_GENERATION_CONFIRMATION", ""),
        app_env=os.environ.get("APP_ENV", "development"),
    )
    try:
        result = await adapter.run_generation(
            project_uuid=args.project_uuid,
            node=args.node,
            working_directory=args.working_directory,
        )
        write_terminal_result(
            args.result_file,
            {
                "ok": True,
                "commandId": args.command_id,
                "nonce": args.nonce,
                "result": asdict(result),
            },
        )
        return 0
    except LibTVError as exc:
        write_terminal_result(
            args.result_file,
            {
                "ok": False,
                "commandId": args.command_id,
                "nonce": args.nonce,
                "error": {
                    "code": exc.code,
                    "message": str(exc),
                    "submitted": exc.submitted,
                    "uncertain": exc.uncertain,
                },
            },
        )
        return 1
    except Exception as exc:
        write_terminal_result(
            args.result_file,
            {
                "ok": False,
                "commandId": args.command_id,
                "nonce": args.nonce,
                "error": {
                    "code": "COMMAND_HOST_ERROR",
                    "message": str(exc),
                    "submitted": True,
                    "uncertain": True,
                },
            },
        )
        return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run one durable LibTV generation command")
    parser.add_argument("--command-id", required=True)
    parser.add_argument("--nonce", required=True)
    parser.add_argument("--project-uuid", required=True)
    parser.add_argument("--node", required=True)
    parser.add_argument("--working-directory", type=Path, required=True)
    parser.add_argument("--result-file", type=Path, required=True)
    parser.add_argument("--libtv-executable", default="libtv")
    return parser


def main() -> int:
    return asyncio.run(execute(build_parser().parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
