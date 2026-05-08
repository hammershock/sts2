from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import time
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
LOG_ROOT = Path(os.environ.get("STS2_LOG_DIR", PROJECT_ROOT / "logs"))


def should_log_cli_call(argv: list[str] | None = None) -> bool:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        return False
    return not any(arg in {"--help", "-h"} for arg in args)


def log_cli_call(
    *,
    command_path: str,
    argv: list[str],
    params: dict[str, Any],
    started_at: str,
    duration_ms: float,
    return_code: int,
    output: str,
) -> None:
    if not should_log_cli_call(argv):
        return
    _append_jsonl(
        "cli",
        {
            "time": started_at,
            "finished_at": _now_iso(),
            "duration_ms": round(duration_ms, 3),
            "command_path": command_path,
            "argv": argv,
            "params": _jsonable(params),
            "return_code": return_code,
            "output": output,
        },
    )


def log_http_request(
    *,
    method: str,
    url: str,
    request_kwargs: dict[str, Any],
    started_at: str,
    started_monotonic: float,
    response: Any = None,
    error: BaseException | None = None,
) -> None:
    request_body = _request_body_from_kwargs(request_kwargs)
    record: dict[str, Any] = {
        "time": started_at,
        "finished_at": _now_iso(),
        "duration_ms": round((time.monotonic() - started_monotonic) * 1000, 3),
        "request": {
            "method": method,
            "url": url,
            "headers": _headers(getattr(getattr(response, "request", None), "headers", {})),
            "body": request_body,
        },
    }
    if response is not None:
        record["response"] = {
            "status_code": response.status_code,
            "headers": _headers(response.headers),
            "text": response.text,
        }
    if error is not None:
        record["error"] = {
            "type": type(error).__name__,
            "message": str(error),
        }
    _append_jsonl("http", record)


def _append_jsonl(category: str, record: dict[str, Any]) -> None:
    directory = LOG_ROOT / category
    try:
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{datetime.now(timezone.utc).strftime('%Y%m%d')}.jsonl"
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    except OSError:
        return


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _request_body_from_kwargs(kwargs: dict[str, Any]) -> Any:
    if "json" in kwargs:
        return _jsonable(kwargs["json"])
    content = kwargs.get("content")
    if isinstance(content, bytes):
        return content.decode("utf-8", errors="replace")
    return _jsonable(content)


def _headers(headers: Any) -> dict[str, str]:
    try:
        return {str(key): str(value) for key, value in dict(headers).items()}
    except Exception:
        return {}


def _jsonable(value: Any) -> Any:
    try:
        json.dumps(value)
        return value
    except TypeError:
        return repr(value)
