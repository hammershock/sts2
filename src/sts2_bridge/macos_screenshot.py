from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sts2_bridge.models import BridgeError


DEFAULT_OWNER = "Slay the Spire 2"
REPO_ROOT = Path(__file__).resolve().parents[2]
SCK_SOURCE = REPO_ROOT / "scripts" / "sck_capture_window.swift"
SCK_BINARY = REPO_ROOT / ".cache" / "sts2" / "sck_capture_window"


@dataclass(frozen=True)
class WindowInfo:
    window_id: int
    owner: str
    name: str | None
    x: int
    y: int
    width: int
    height: int
    layer: int

    @property
    def area(self) -> int:
        return self.width * self.height

    def to_dict(self) -> dict[str, Any]:
        return {
            "window_id": self.window_id,
            "owner": self.owner,
            "name": self.name,
            "bounds": {
                "x": self.x,
                "y": self.y,
                "width": self.width,
                "height": self.height,
            },
            "layer": self.layer,
        }


def list_windows(owner: str = DEFAULT_OWNER) -> list[WindowInfo]:
    try:
        import Quartz  # type: ignore[import-not-found]
    except ImportError as exc:
        raise BridgeError(
            "missing_quartz",
            "pyobjc-framework-Quartz is required for macOS window discovery.",
            retryable=False,
        ) from exc

    raw_windows = Quartz.CGWindowListCopyWindowInfo(Quartz.kCGWindowListOptionAll, Quartz.kCGNullWindowID)
    windows: list[WindowInfo] = []
    for raw in raw_windows:
        raw_owner = raw.get("kCGWindowOwnerName")
        if raw_owner != owner:
            continue
        bounds = raw.get("kCGWindowBounds") or {}
        windows.append(
            WindowInfo(
                window_id=int(raw.get("kCGWindowNumber")),
                owner=str(raw_owner),
                name=raw.get("kCGWindowName"),
                x=int(bounds.get("X", 0)),
                y=int(bounds.get("Y", 0)),
                width=int(bounds.get("Width", 0)),
                height=int(bounds.get("Height", 0)),
                layer=int(raw.get("kCGWindowLayer", 0)),
            )
        )
    return windows


def window_status(owner: str = DEFAULT_OWNER) -> dict[str, Any]:
    windows = list_windows(owner)
    selected: WindowInfo | None = None
    try:
        selected = select_game_window(windows)
    except BridgeError:
        selected = None
    frontmost = _frontmost_app()
    return {
        "owner": owner,
        "process_running": bool(windows),
        "frontmost_app": frontmost,
        "is_frontmost": frontmost == owner,
        "selected_window": selected.to_dict() if selected else None,
        "window_count": len(windows),
    }


def select_game_window(windows: list[WindowInfo]) -> WindowInfo:
    candidates = [
        window
        for window in windows
        if window.layer == 0 and window.width >= 320 and window.height >= 240 and window.x > -10000
    ]
    if not candidates:
        raise BridgeError(
            "window_not_found",
            "Cannot find a visible Slay the Spire 2 game window.",
            details={"windows": [window.to_dict() for window in windows]},
            retryable=True,
        )
    return max(candidates, key=lambda window: window.area)


def capture_window(
    output: Path | None = None,
    *,
    owner: str = DEFAULT_OWNER,
    window_id: int | None = None,
    include_shadow: bool = False,
    allow_rect_fallback: bool = True,
    activate_fallback: bool = False,
) -> dict[str, Any]:
    windows = list_windows(owner)
    window = _find_window(windows, window_id) if window_id is not None else select_game_window(windows)
    output_path = output or default_output_path()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    status = window_status(owner)
    if status["is_frontmost"]:
        sck_result = _capture_with_sck(output_path, owner)
        if sck_result["ok"]:
            return {
                "path": str(output_path),
                "bytes": output_path.stat().st_size,
                "method": "screencapturekit",
                "activate_fallback": False,
                "active_app_before": status["frontmost_app"],
                "window": window.to_dict(),
                "screencapturekit": sck_result["data"],
            }

    attempts: list[dict[str, Any]] = []
    command = ["/usr/sbin/screencapture", "-x", f"-l{window.window_id}"]
    if not include_shadow:
        command.append("-o")
    command.append(str(output_path))

    result = subprocess.run(command, text=True, capture_output=True, check=False)
    attempts.append(_attempt_result("window", command, result))
    method = "window"

    active_app_before: str | None = None
    can_use_rect_fallback = allow_rect_fallback and (activate_fallback or status["is_frontmost"])
    if result.returncode != 0 and allow_rect_fallback and not can_use_rect_fallback:
        attempts.append(
            {
                "method": "rect",
                "skipped": True,
                "reason": "rect fallback would capture the frontmost screen region while the game is not frontmost",
            }
        )

    if result.returncode != 0 and can_use_rect_fallback:
        if activate_fallback:
            active_app_before = _frontmost_app()
            _activate_app(owner)
            time.sleep(0.5)
        rect = f"{window.x},{window.y},{window.width},{window.height}"
        command = ["/usr/sbin/screencapture", "-x", f"-R{rect}", str(output_path)]
        try:
            result = subprocess.run(command, text=True, capture_output=True, check=False)
        finally:
            if activate_fallback and active_app_before and active_app_before != owner:
                _activate_app(active_app_before)
        attempts.append(_attempt_result("rect", command, result))
        method = "rect"

    if result.returncode != 0:
        raise BridgeError(
            "screenshot_failed",
            "macOS failed to capture the STS2 window. Check Screen Recording permission for the terminal app.",
            details={
                "attempts": attempts,
                "frontmost": status,
                "window": window.to_dict(),
            },
            retryable=True,
        )
    if not output_path.exists() or output_path.stat().st_size == 0:
        raise BridgeError(
            "screenshot_empty",
            "Screenshot command completed but produced no image.",
            details={"path": str(output_path), "window": window.to_dict()},
            retryable=True,
        )
    return {
        "path": str(output_path),
        "bytes": output_path.stat().st_size,
        "method": method,
        "activate_fallback": activate_fallback,
        "active_app_before": active_app_before,
        "window": window.to_dict(),
    }


def click_window(
    x: float,
    y: float,
    *,
    owner: str = DEFAULT_OWNER,
    window_id: int | None = None,
    normalized: bool = False,
    activate: bool = True,
    restore: bool = True,
    dry_run: bool = False,
) -> dict[str, Any]:
    windows = list_windows(owner)
    window = _find_window(windows, window_id) if window_id is not None else select_game_window(windows)
    screen_x, screen_y = window_click_coordinates(window, x, y, normalized=normalized)

    active_app_before = _frontmost_app()
    should_activate = activate and not dry_run
    if should_activate:
        _activate_app(owner)
        time.sleep(0.2)

    if not dry_run:
        _post_left_click(screen_x, screen_y)

    if should_activate and restore and active_app_before and active_app_before != owner:
        time.sleep(0.1)
        _activate_app(active_app_before)

    return {
        "clicked": not dry_run,
        "dry_run": dry_run,
        "owner": owner,
        "window": window.to_dict(),
        "input": {"x": x, "y": y, "normalized": normalized},
        "screen_point": {"x": screen_x, "y": screen_y},
        "activate": activate,
        "activated": should_activate,
        "restore": restore,
        "active_app_before": active_app_before,
    }


def window_click_coordinates(
    window: WindowInfo,
    x: float,
    y: float,
    *,
    normalized: bool = False,
) -> tuple[int, int]:
    if normalized:
        if not (0 <= x <= 1 and 0 <= y <= 1):
            raise BridgeError(
                "invalid_click_coordinates",
                "Normalized click coordinates must be between 0 and 1.",
                details={"x": x, "y": y},
                retryable=False,
            )
        relative_x = round(x * window.width)
        relative_y = round(y * window.height)
    else:
        relative_x = round(x)
        relative_y = round(y)

    if relative_x < 0 or relative_y < 0 or relative_x > window.width or relative_y > window.height:
        raise BridgeError(
            "invalid_click_coordinates",
            "Click coordinates are outside the selected window bounds.",
            details={
                "x": x,
                "y": y,
                "normalized": normalized,
                "window": window.to_dict(),
            },
            retryable=False,
        )
    return window.x + relative_x, window.y + relative_y


def default_output_path() -> Path:
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    return Path("debug") / "screenshots" / f"sts2-{timestamp}.png"


def _find_window(windows: list[WindowInfo], window_id: int) -> WindowInfo:
    for window in windows:
        if window.window_id == window_id:
            return window
    raise BridgeError(
        "window_not_found",
        "The requested STS2 window id was not found.",
        details={"window_id": window_id, "windows": [window.to_dict() for window in windows]},
        retryable=True,
    )


def _attempt_result(method: str, command: list[str], result: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    return {
        "method": method,
        "command": command,
        "returncode": result.returncode,
        "stderr": result.stderr.strip(),
    }


def _capture_with_sck(output_path: Path, owner: str) -> dict[str, Any]:
    try:
        _ensure_sck_binary()
    except BridgeError as exc:
        return {"ok": False, "error": exc.to_dict()["error"]}
    result = subprocess.run(
        [str(SCK_BINARY), str(output_path), owner],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        return {
            "ok": False,
            "error": {
                "code": "screencapturekit_failed",
                "message": "ScreenCaptureKit window capture failed.",
                "details": {"stderr": result.stderr.strip(), "stdout": result.stdout.strip()},
                "retryable": True,
            },
        }
    try:
        import json

        data = json.loads(result.stdout.strip() or "{}")
    except ValueError:
        data = {"stdout": result.stdout.strip()}
    return {"ok": True, "data": data}


def _ensure_sck_binary() -> None:
    if not SCK_SOURCE.exists():
        raise BridgeError(
            "screencapturekit_source_missing",
            "ScreenCaptureKit helper source is missing.",
            details={"path": str(SCK_SOURCE)},
            retryable=False,
        )
    if SCK_BINARY.exists() and SCK_BINARY.stat().st_mtime >= SCK_SOURCE.stat().st_mtime:
        return
    SCK_BINARY.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        ["/usr/bin/swiftc", "-parse-as-library", str(SCK_SOURCE), "-o", str(SCK_BINARY)],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise BridgeError(
            "screencapturekit_build_failed",
            "Failed to build the ScreenCaptureKit helper.",
            details={"stderr": result.stderr.strip(), "stdout": result.stdout.strip()},
            retryable=False,
        )


def _frontmost_app() -> str | None:
    script = 'tell application "System Events" to get name of first application process whose frontmost is true'
    result = subprocess.run(["/usr/bin/osascript", "-e", script], text=True, capture_output=True, check=False)
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def _activate_app(app_name: str) -> None:
    subprocess.run(
        ["/usr/bin/osascript", "-e", f'tell application "{app_name}" to activate'],
        text=True,
        capture_output=True,
        check=False,
    )


def _post_left_click(x: int, y: int) -> None:
    try:
        import Quartz  # type: ignore[import-not-found]
    except ImportError as exc:
        raise BridgeError(
            "missing_quartz",
            "pyobjc-framework-Quartz is required for macOS click fallback.",
            retryable=False,
        ) from exc

    point = Quartz.CGPointMake(x, y)
    move = Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventMouseMoved, point, Quartz.kCGMouseButtonLeft)
    down = Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventLeftMouseDown, point, Quartz.kCGMouseButtonLeft)
    up = Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventLeftMouseUp, point, Quartz.kCGMouseButtonLeft)
    if move is None or down is None or up is None:
        raise BridgeError(
            "click_failed",
            "macOS failed to create a mouse click event. Check Accessibility permission for the terminal app.",
            retryable=True,
        )
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, move)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, down)
    time.sleep(0.05)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, up)
