from __future__ import annotations

import json
import os
import shutil
import sys
import time
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import urlparse

import click
import typer
import yaml
from pydantic import BaseModel

from sts2_bridge.action_args import parse_action_args, resolve_action
from sts2_bridge.action_view import render_action_response, route_action_response
from sts2_bridge.agent_view import (
    build_state_view,
)
from sts2_bridge.client import DEFAULT_BASE_URL, Sts2Client
from sts2_bridge.models import BridgeError, GameState
from sts2_bridge.rendering import render_state_view
from sts2_bridge.state_view import render_state_response, route_state_response
from sts2_bridge.state_view.model import response_data
from sts2_bridge.state_actions import effective_available_actions, effective_visible_action_entries, has_recovery_options
from sts2_bridge.trace import log_cli_call, should_log_cli_call, _now_iso

app = typer.Typer(
    invoke_without_command=True,
    no_args_is_help=False,
    help="Layered CLI bridge for Slay the Spire 2 agent control.",
)
debug_app = typer.Typer(no_args_is_help=True, help="Debug commands for API and macOS window inspection.")
app.add_typer(debug_app, name="debug")


BaseUrlOption = Annotated[
    str | None,
    typer.Option("--base-url", help="STS2 Mod API base URL. Defaults to STS2_API_BASE_URL or localhost:8080."),
]
TimeoutOption = Annotated[float, typer.Option("--api-timeout", help="HTTP request timeout in seconds.")]
REST_RECOVERY_TARGETS = {
    "relic": (0.03, 0.333),
    "top-bar-relic": (0.03, 0.333),
    "rest-card": (0.41, 0.43),
    "smith-card": (0.59, 0.43),
}


@app.callback()
def main(
    ctx: typer.Context,
    base_url: BaseUrlOption = None,
    api_timeout: TimeoutOption = 10.0,
) -> None:
    """Run interactive mode when no subcommand is provided."""
    if ctx.invoked_subcommand is not None:
        return
    if not _is_interactive_terminal():
        typer.echo(ctx.get_help())
        raise typer.Exit()
    _interactive(_client(base_url, api_timeout))
    raise typer.Exit()


@debug_app.command()
def health(
    base_url: BaseUrlOption = None,
    api_timeout: TimeoutOption = 10.0,
) -> None:
    """Check whether the STS2 Mod API is reachable."""
    client = _client(base_url, api_timeout)
    _run_text(lambda: _render_health(client.health()))


@debug_app.command("route-render-samples")
def debug_route_render_samples(
    logs_dir: Annotated[Path, typer.Option("--logs-dir", help="Directory containing HTTP JSONL logs.")] = Path("logs/http"),
    output_dir: Annotated[
        Path,
        typer.Option("--output-dir", help="Directory to rebuild with rendered route sample files."),
    ] = Path("debug/route_render_samples"),
) -> None:
    """Regenerate debug/route_render_samples from HTTP logs."""

    def command() -> str:
        resolved_logs_dir = _resolve_logs_dir(logs_dir)
        resolved_output_dir = _resolve_repo_path(output_dir)
        result = _rebuild_route_render_samples(resolved_logs_dir, resolved_output_dir)
        return _format_route_render_sample_result(result)

    _run_text(command)


@app.command()
def state(
    base_url: BaseUrlOption = None,
    api_timeout: TimeoutOption = 10.0,
    raw: Annotated[bool, typer.Option("--raw", help="Return the raw parsed /state HTTP JSON response.")] = False,
) -> None:
    """Read the current game state."""
    client = _client(base_url, api_timeout)

    def command() -> str:
        response = client.state_response()
        if raw:
            return _to_yaml(response)
        return render_state_response(response)

    _run_text(command)


@app.command(context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
def act(
    ctx: typer.Context,
    action: Annotated[str, typer.Argument(help="Action name, alias, or index from Legal actions.")],
    base_url: BaseUrlOption = None,
    api_timeout: TimeoutOption = 10.0,
    raw_result: Annotated[
        bool,
        typer.Option("--raw-result", help="Return the raw parsed /action HTTP JSON response."),
    ] = False,
) -> None:
    """Execute one game action. Extra tokens after ACTION are parsed as action args."""
    client = _client(base_url, api_timeout)

    def command() -> str:
        before = _try_state(client)
        if before is None:
            raise BridgeError(
                "state_unavailable",
                "Cannot resolve action name or index because current state is unavailable.",
                retryable=True,
            )
        raw_tokens = list(ctx.args)
        resolved_action, args, completion_tokens = _parse_action_request(action, raw_tokens, before)
        args = _complete_action_args_from_state(resolved_action, args, completion_tokens, before)
        _validate_action_against_state(resolved_action, before)
        try:
            response = client.action_response(resolved_action, args)
        except BridgeError as exc:
            if exc.code in {"connection_failed", "timeout", "http_error"}:
                output = render_action_response(
                    None,
                    request_action=resolved_action,
                    request_args=args,
                    transport_error=exc.to_dict()["error"],
                )
                raise RenderedCliError(output, code=1) from exc
            raise
        if raw_result:
            return _to_yaml(response)
        output = render_action_response(response, request_action=resolved_action, request_args=args)
        if response.get("ok") is False:
            raise RenderedCliError(output, code=1)
        return output

    _run_text(command)


@app.command()
def wait(
    base_url: BaseUrlOption = None,
    api_timeout: TimeoutOption = 10.0,
    timeout: Annotated[float, typer.Option("--timeout", help="Maximum time to wait in seconds.")] = 30.0,
    interval: Annotated[float, typer.Option("--interval", help="Polling interval in seconds.")] = 0.5,
) -> None:
    """Wait until the game state is readable and has at least one available action."""
    client = _client(base_url, api_timeout)

    def command() -> str:
        deadline = time.monotonic() + timeout
        last_error: dict[str, Any] | None = None
        while time.monotonic() <= deadline:
            try:
                response = client.state_response()
            except BridgeError as exc:
                last_error = exc.to_dict()["error"]
                if not exc.retryable:
                    raise
                time.sleep(interval)
                continue
            data = response_data(response)
            actions = data.get("available_actions") if isinstance(data, dict) else []
            if actions:
                return render_state_response(response)
            time.sleep(interval)
        raise BridgeError(
            "wait_timeout",
            "Timed out waiting for an actionable STS2 state.",
            details={"timeout": timeout, "last_error": last_error},
            retryable=True,
        )

    _run_text(command)


@debug_app.command()
def windows(
    owner: Annotated[str, typer.Option("--owner", help="macOS window owner name to search for.")] = "Slay the Spire 2",
) -> None:
    """List candidate STS2 windows for screenshot fallback debugging."""

    def command() -> str:
        _require_macos()
        from sts2_bridge.macos_screenshot import list_windows, select_game_window

        windows_data = list_windows(owner)
        selected = None
        try:
            selected = select_game_window(windows_data).to_dict()
        except BridgeError:
            selected = None
        return _to_yaml({"selected": selected, "windows": [window.to_dict() for window in windows_data]})

    _run_text(command)


@debug_app.command("window-status")
def window_status_command(
    owner: Annotated[str, typer.Option("--owner", help="macOS window owner name to search for.")] = "Slay the Spire 2",
) -> None:
    """Report whether the STS2 window exists and is the frontmost app."""

    def command() -> str:
        _require_macos()
        from sts2_bridge.macos_screenshot import window_status

        return _to_yaml(window_status(owner))

    _run_text(command)


@debug_app.command("click-window")
def click_window_command(
    x: Annotated[float, typer.Argument(help="X coordinate relative to the selected game window.")],
    y: Annotated[float, typer.Argument(help="Y coordinate relative to the selected game window.")],
    owner: Annotated[str, typer.Option("--owner", help="macOS window owner name to search for.")] = "Slay the Spire 2",
    window_id: Annotated[int | None, typer.Option("--window-id", help="Click a specific macOS window id.")] = None,
    normalized: Annotated[
        bool,
        typer.Option("--normalized", help="Treat X and Y as 0..1 fractions of the selected window size."),
    ] = False,
    activate: Annotated[
        bool,
        typer.Option("--activate/--no-activate", help="Bring the game to the foreground before clicking."),
    ] = True,
    restore: Annotated[
        bool,
        typer.Option("--restore/--no-restore", help="Restore the previous foreground app after clicking."),
    ] = True,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Only report the resolved screen point.")] = False,
) -> None:
    """Click a point inside the STS2 window as a last-resort UI fallback."""

    def command() -> str:
        _require_macos()
        from sts2_bridge.macos_screenshot import click_window

        return _to_yaml(
            click_window(
                x,
                y,
                owner=owner,
                window_id=window_id,
                normalized=normalized,
                activate=activate,
                restore=restore,
                dry_run=dry_run,
            )
        )

    _run_text(command)


@debug_app.command("recover-rest")
def recover_rest_command(
    base_url: BaseUrlOption = None,
    api_timeout: TimeoutOption = 10.0,
    owner: Annotated[str, typer.Option("--owner", help="macOS window owner name to search for.")] = "Slay the Spire 2",
    window_id: Annotated[int | None, typer.Option("--window-id", help="Click a specific macOS window id.")] = None,
    target: Annotated[
        str,
        typer.Option("--target", help="Recovery target: relic, top-bar-relic, rest-card, smith-card."),
    ] = "relic",
    x: Annotated[
        float | None,
        typer.Option("--x", help="Override normalized X coordinate for the recovery click."),
    ] = None,
    y: Annotated[
        float | None,
        typer.Option("--y", help="Override normalized Y coordinate for the recovery click."),
    ] = None,
    double_click: Annotated[bool, typer.Option("--double-click", help="Send two clicks to the selected target.")] = False,
    escape: Annotated[
        bool,
        typer.Option("--escape/--no-escape", help="Press Escape after the click to close a relic detail modal."),
    ] = True,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Only report the resolved click and state check.")] = False,
    force: Annotated[bool, typer.Option("--force", help="Allow recovery outside REST/no-action states.")] = False,
) -> None:
    """Recover a REST UI/API desync by clicking the top-left relic area."""
    client = _client(base_url, api_timeout)

    def command() -> str:
        _require_macos()
        from sts2_bridge.macos_screenshot import click_window, press_key

        before = client.state()
        actions = effective_available_actions(before)
        recovery = has_recovery_options(before)
        if not force and before.screen != "REST":
            raise BridgeError(
                "invalid_recovery_state",
                "REST recovery can only run on REST screens unless --force is passed.",
                details=_recovery_state_summary(before),
                retryable=False,
            )
        if not force and not recovery:
            raise BridgeError(
                "invalid_recovery_state",
                "Current REST state does not expose recovery options.",
                details=_recovery_state_summary(before),
                retryable=False,
            )

        click_x, click_y = _rest_recovery_point(target, x, y)
        clicks = [
            click_window(click_x, click_y, owner=owner, window_id=window_id, normalized=True, dry_run=dry_run)
        ]
        if double_click and not dry_run:
            time.sleep(0.15)
            clicks.append(
                click_window(click_x, click_y, owner=owner, window_id=window_id, normalized=True, dry_run=False)
            )
        escape_result: dict[str, Any] | None = None
        if escape:
            if not dry_run:
                time.sleep(0.2)
            escape_result = press_key("escape", dry_run=dry_run)
        after: dict[str, Any] | None = None
        status = "dry_run"
        suggestions: list[str] = []
        if not dry_run:
            time.sleep(0.5)
            after_state = client.state()
            after = _recovery_state_summary(after_state)
            if _rest_recovery_resolved(after_state):
                status = "recovered"
            else:
                status = "unchanged"
                suggestions = _rest_recovery_suggestions(target)

        return _to_yaml(
            {
                "recovery": "rest_relic_refresh_click",
                "status": status,
                "dry_run": dry_run,
                "target": target,
                "point": {"x": click_x, "y": click_y, "normalized": True},
                "before": _recovery_state_summary(before),
                "click": clicks[0],
                "clicks": clicks,
                "escape": escape_result,
                "after": after,
                "suggestions": suggestions,
            }
        )

    _run_text(command)


@app.command()
def screenshot(
    output: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="PNG output path. Defaults to debug/screenshots/sts2-<timestamp>.png."),
    ] = None,
    owner: Annotated[str, typer.Option("--owner", help="macOS window owner name to search for.")] = "Slay the Spire 2",
    window_id: Annotated[int | None, typer.Option("--window-id", help="Capture a specific macOS window id.")] = None,
    include_shadow: Annotated[bool, typer.Option("--include-shadow", help="Include macOS window shadow.")] = False,
    no_rect_fallback: Annotated[
        bool,
        typer.Option("--no-rect-fallback", help="Do not fall back to screen-rectangle capture if window capture fails."),
    ] = False,
    activate_fallback: Annotated[
        bool,
        typer.Option(
            "--activate-fallback",
            help="If window capture fails, briefly activate the game before rectangle capture, then restore focus.",
        ),
    ] = False,
) -> None:
    """Capture the STS2 game window without bringing it to the foreground."""

    def command() -> str:
        _require_macos()
        from sts2_bridge.macos_screenshot import capture_window

        return _to_yaml(
            capture_window(
                output,
                owner=owner,
                window_id=window_id,
                include_shadow=include_shadow,
                allow_rect_fallback=not no_rect_fallback,
                activate_fallback=activate_fallback,
            )
        )

    _run_text(command)


def _client(base_url: str | None, timeout: float) -> Sts2Client:
    return Sts2Client(base_url or os.environ.get("STS2_API_BASE_URL", DEFAULT_BASE_URL), timeout=timeout)


def _rebuild_route_render_samples(logs_dir: Path, output_dir: Path) -> dict[str, Any]:
    if not logs_dir.exists() or not logs_dir.is_dir():
        raise BridgeError(
            "invalid_logs_dir",
            "HTTP log directory does not exist.",
            details={"logs_dir": str(logs_dir)},
            retryable=False,
        )
    if output_dir.exists() and not output_dir.is_dir():
        raise BridgeError(
            "invalid_output_dir",
            "Route render sample output path exists but is not a directory.",
            details={"output_dir": str(output_dir)},
            retryable=False,
        )

    log_files = sorted(logs_dir.glob("*.jsonl"))
    if not log_files:
        raise BridgeError(
            "empty_logs_dir",
            "HTTP log directory does not contain any JSONL files.",
            details={"logs_dir": str(logs_dir)},
            retryable=False,
        )

    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    counts: dict[str, int] = {}
    files: list[dict[str, Any]] = []
    errors: list[str] = []
    total_lines = _count_file_lines(log_files)
    with click.progressbar(length=total_lines, label="Rendering route samples") as progress:
        for log_file in log_files:
            with log_file.open("r", encoding="utf-8") as handle:
                for line_no, line in enumerate(handle, 1):
                    progress.update(1)
                    if not line.strip():
                        continue
                    try:
                        sample = _route_log_line(log_file, line_no, line)
                    except Exception as exc:
                        errors.append(f"{log_file}:{line_no}: {type(exc).__name__}: {exc}")
                        continue
                    if sample is None:
                        continue
                    route = sample["route"]
                    counts[route] = counts.get(route, 0) + 1
                    route_dir = output_dir / route
                    route_dir.mkdir(parents=True, exist_ok=True)
                    path = route_dir / _route_sample_filename(log_file, line_no, sample)
                    path.write_text(sample["rendered"].rstrip() + "\n", encoding="utf-8")
                    files.append(
                        {
                            "route": route,
                            "path": path,
                            "source": sample["source"],
                            "line": line_no,
                        }
                    )

    if errors:
        error_path = output_dir / "_generation_errors.txt"
        error_path.write_text("\n".join(errors) + "\n", encoding="utf-8")
        raise BridgeError(
            "route_render_sample_generation_failed",
            "Some HTTP log records could not be routed or rendered.",
            details={"errors": len(errors), "error_file": str(error_path)},
            retryable=False,
        )
    if not files:
        raise BridgeError(
            "route_render_samples_empty",
            "No routeable /state or /action HTTP records were found.",
            details={"logs_dir": str(logs_dir)},
            retryable=False,
        )

    index_path = output_dir / "index.txt"
    index_path.write_text(_format_route_render_sample_index(logs_dir, output_dir, counts, files), encoding="utf-8")
    return {
        "logs_dir": logs_dir,
        "output_dir": output_dir,
        "routes": len(counts),
        "samples": len(files),
        "index": index_path,
    }


def _count_file_lines(paths: list[Path]) -> int:
    total = 0
    for path in paths:
        with path.open("r", encoding="utf-8") as handle:
            total += sum(1 for _ in handle)
    return total


def _resolve_logs_dir(logs_dir: Path) -> Path:
    if logs_dir.exists() or logs_dir.is_absolute():
        return logs_dir
    repo_relative = _repo_root() / logs_dir
    if repo_relative.exists():
        return repo_relative
    return logs_dir


def _resolve_repo_path(path: Path) -> Path:
    if path.is_absolute():
        return path
    return _repo_root() / path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _route_log_line(log_file: Path, line_no: int, line: str) -> dict[str, Any] | None:
    record = json.loads(line)
    request = record.get("request") if isinstance(record, dict) else None
    if not isinstance(request, dict):
        return None
    method = request.get("method")
    path = urlparse(request.get("url") or "").path
    if method == "GET" and path == "/state":
        return _route_state_log_record(log_file, line_no, record)
    if method == "POST" and path == "/action":
        return _route_action_log_record(log_file, line_no, record)
    return None


def _route_state_log_record(log_file: Path, line_no: int, record: dict[str, Any]) -> dict[str, Any] | None:
    raw = _log_response_json(record)
    if not isinstance(raw, dict):
        return None
    route = route_state_response(raw)
    return {
        "kind": "state",
        "route": route.category,
        "source": str(log_file),
        "line": line_no,
        "method": "GET",
        "path": "/state",
        "http_status": _log_status(record),
        "rendered": render_state_response(raw),
    }


def _route_action_log_record(log_file: Path, line_no: int, record: dict[str, Any]) -> dict[str, Any] | None:
    request_body = (record.get("request") or {}).get("body")
    request_action = request_body.get("action") if isinstance(request_body, dict) else None
    request_args = {key: value for key, value in request_body.items() if key != "action"} if isinstance(request_body, dict) else {}
    raw = _log_response_json(record)
    status = _log_status(record)
    route = route_action_response(raw if isinstance(raw, dict) else None, request_action=request_action, http_status=status)
    return {
        "kind": "action",
        "route": route.category,
        "source": str(log_file),
        "line": line_no,
        "method": "POST",
        "path": "/action",
        "request_action": request_action,
        "request_args": request_args,
        "http_status": status,
        "rendered": render_action_response(
            raw if isinstance(raw, dict) else None,
            request_action=request_action,
            request_args=request_args,
            http_status=status,
        ),
    }


def _log_response_json(record: dict[str, Any]) -> Any:
    response = record.get("response")
    if not isinstance(response, dict):
        return None
    text = response.get("text")
    if not isinstance(text, str) or not text:
        return None
    return json.loads(text)


def _log_status(record: dict[str, Any]) -> int | None:
    response = record.get("response")
    if not isinstance(response, dict):
        return None
    status = response.get("status_code")
    return status if isinstance(status, int) else None


def _route_sample_filename(log_file: Path, line_no: int, sample: dict[str, Any]) -> str:
    label = sample.get("request_action") or sample.get("method") or "sample"
    return f"{log_file.stem}_l{line_no:05d}_{_safe_filename_part(label)}.txt"


def _safe_filename_part(value: object) -> str:
    text = str(value or "").strip().lower()
    chars = [char if char.isalnum() or char in "._-" else "_" for char in text]
    return "_".join("".join(chars).split("_")).strip("_") or "sample"


def _format_route_render_sample_result(result: dict[str, Any]) -> str:
    lines = [
        "Route render samples regenerated.",
        f"Logs: {result['logs_dir']}",
        f"Output: {result['output_dir']}",
        f"Routes: {result['routes']}",
        f"Samples: {result['samples']}",
        f"Index: {result['index']}",
    ]
    return "\n".join(lines).rstrip() + "\n"


def _format_route_render_sample_index(
    logs_dir: Path,
    output_dir: Path,
    counts: dict[str, int],
    files: list[dict[str, Any]],
) -> str:
    lines = [
        "Route render samples",
        f"Logs: {logs_dir}",
        f"Output: {output_dir}",
        "",
        f"Routes: {len(counts)}",
        f"Samples: {len(files)}",
        "",
        "Counts:",
    ]
    for route in sorted(counts):
        lines.append(f"{counts[route]:5d}  {route}")
    lines.append("")
    lines.append("Files:")
    for item in files:
        path = item["path"]
        relative = path.relative_to(output_dir)
        lines.append(f"{item['route']}\t{relative}\t{item['source']}:{item['line']}")
    return "\n".join(lines).rstrip() + "\n"


def _is_interactive_terminal() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()


def _interactive(client: Sts2Client) -> None:
    typer.echo(_interactive_help().rstrip())
    while True:
        try:
            state = client.state()
            view = build_state_view(state, "brief")
            typer.echo("")
            typer.echo(render_state_view(view), nl=False)
            raw_command = typer.prompt("sts2", default="", show_default=False)
            command = raw_command.strip()
            if command.lower() in {"q", "quit", "exit"}:
                return
            if command in {"?", "h", "help"}:
                typer.echo(_interactive_help().rstrip())
                continue
            request = _interactive_action_from_input(command, state, view)
            if request is None:
                continue
            action, args = request
            result = client.act(action, args)
            status = result.status or "completed"
            suffix = f" {_inline_mapping(args)}" if args else ""
            typer.echo(f"done: {action}{suffix} ({status})")
        except BridgeError as exc:
            typer.echo(_render_error(exc))
        except (EOFError, KeyboardInterrupt):
            typer.echo("")
            return


def _interactive_help() -> str:
    return "\n".join(
        [
            "Interactive keys:",
            "- Enter: refresh, or take the only non-card action when it is unambiguous",
            "- 0-9: play that hand card in combat; choose that map/reward option on map/reward screens",
            "- e: end turn",
            "- c: collect rewards and proceed",
            "- r: resolve rewards",
            "- action args: run an explicit action, e.g. play_card 0 0",
            "- ?: help",
            "- q: quit",
        ]
    ) + "\n"


def _interactive_action_from_input(
    command: str,
    state: GameState,
    view: dict[str, Any],
) -> tuple[str, dict[str, Any]] | None:
    if command == "":
        return _default_interactive_action(state)

    lowered = command.lower()
    if lowered == "e":
        return _action_if_available(state, "end_turn", {})
    if lowered == "c":
        return _action_if_available(state, "collect_rewards_and_proceed", {})
    if lowered == "r":
        return _action_if_available(state, "resolve_rewards", {})
    if command.isdigit():
        return _numeric_interactive_action(int(command), state, view)

    tokens = command.split()
    action = resolve_action(tokens[0], effective_available_actions(state))
    args = parse_action_args(action, tokens[1:])
    return action, _complete_action_args_from_state(action, args, tokens[1:], state)


def _default_interactive_action(state: GameState) -> tuple[str, dict[str, Any]] | None:
    actions = effective_available_actions(state)
    non_card_actions = [action for action in actions if action != "play_card"]
    if len(actions) == 1 and actions[0] != "play_card":
        action = actions[0]
        return action, _complete_action_args_from_state(action, parse_action_args(action, []), [], state)
    if len(non_card_actions) == 1 and not _has_playable_cards(state):
        action = non_card_actions[0]
        return action, _complete_action_args_from_state(action, parse_action_args(action, []), [], state)
    return None


def _numeric_interactive_action(
    index: int,
    state: GameState,
    view: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    actions = effective_available_actions(state)
    if state.screen == "MAP" and "choose_map_node" in actions:
        return "choose_map_node", {"option_index": index}
    if state.screen in {"REWARD", "CARD_REWARD"} and "claim_reward" in actions:
        return "claim_reward", {"option_index": index}
    if state.screen == "CARD_SELECTION" and "select_deck_card" in actions:
        return "select_deck_card", {"option_index": index}
    if state.screen == "REST" and "choose_rest_option" in actions:
        return "choose_rest_option", {"option_index": index}
    if state.screen == "COMBAT" and "play_card" in actions:
        card_args = _card_args_from_view(index, view)
        if card_args is not None:
            return "play_card", card_args

    action = resolve_action(str(index), actions)
    return action, _complete_action_args_from_state(action, parse_action_args(action, []), [], state)


def _card_args_from_view(card_index: int, view: dict[str, Any]) -> dict[str, Any] | None:
    combat = view.get("combat") or {}
    cards = combat.get("playable") or combat.get("playable_cards") or []
    for card in cards:
        if card.get("card_index") != card_index:
            continue
        args = {"card_index": card_index}
        targets = card.get("valid_targets") or []
        if card.get("requires_target") and targets:
            target_index = targets[0].get("target_index")
            if target_index is not None:
                args["target_index"] = target_index
        return args
    return None


def _action_if_available(state: GameState, action: str, args: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    available_actions = effective_available_actions(state)
    if action not in available_actions:
        raise BridgeError(
            "invalid_action",
            f"{action} is not available in the current state.",
            details={"available_actions": available_actions},
            retryable=False,
        )
    return action, args


def _parse_action_request(
    action_ref: str,
    raw_tokens: list[str],
    state: GameState,
) -> tuple[str, dict[str, Any], list[str]]:
    if not action_ref.isdigit():
        action = resolve_action(action_ref, effective_available_actions(state))
        return action, parse_action_args(action, raw_tokens), raw_tokens

    entries = effective_visible_action_entries(state)
    index = int(action_ref)
    if index < 0 or index >= len(entries):
        raise BridgeError(
            "invalid_action",
            "Action index is outside the current visible action list.",
            details={
                "action": action_ref,
                "available_actions": [
                    {"index": item_index, "action": entry.action, "args": entry.args}
                    for item_index, entry in enumerate(entries)
                ],
            },
            retryable=False,
        )
    entry = entries[index]
    if raw_tokens:
        return entry.action, {**entry.args, **parse_action_args(entry.action, raw_tokens)}, raw_tokens
    if entry.args:
        return entry.action, dict(entry.args), _tokens_for_prefilled_args(entry.args)
    return entry.action, parse_action_args(entry.action, []), []


def _tokens_for_prefilled_args(args: dict[str, Any]) -> list[str]:
    if "option_index" in args:
        return [str(args["option_index"])]
    return []


def _validate_action_against_state(action: str, state: GameState) -> None:
    if action not in {"resolve_rewards", "collect_rewards_and_proceed"}:
        return
    unloaded_cards = _claimable_unloaded_card_rewards(state)
    if not unloaded_cards:
        return
    raise BridgeError(
        "unsafe_reward_resolution",
        "Refusing to resolve rewards while a claimable Card reward has no visible card choices.",
        details={
            "action": action,
            "card_rewards": unloaded_cards,
            "suggestion": "Run claim_reward with the Card reward option_index first, then choose or skip the visible card options.",
        },
        retryable=False,
    )


def _complete_action_args_from_state(
    action: str,
    args: dict[str, Any],
    raw_tokens: list[str],
    state: GameState,
) -> dict[str, Any]:
    completed = dict(args)
    view = _state_action_index_view(state)
    _complete_option_index(action, completed, raw_tokens, view)
    _complete_play_card_target(action, completed, raw_tokens, view)
    return completed


def _state_action_index_view(state: GameState) -> dict[str, Any]:
    data = _dump_model(state)
    return {
        "combat": {"playable": _playable_cards_for_args(state)},
        "map": {"choices": _indexed_items(((data.get("map") or {}).get("available_nodes")))},
        "event": {"options": _indexed_items(((data.get("event") or {}).get("options")), lock_key="is_locked")},
        "timeline": {"slots": _indexed_items(((data.get("timeline") or {}).get("slots")), action_key="is_actionable")},
        "rest": {"options": _indexed_items(((data.get("rest") or {}).get("options")), lock_key="is_locked")},
        "reward": {
            "rewards": _indexed_items(((data.get("reward") or {}).get("rewards")), claimable_key="claimable"),
            "card_options": _indexed_items(((data.get("reward") or {}).get("card_options"))),
        },
        "selection": {"cards": _indexed_items(((data.get("selection") or {}).get("cards")))},
        "character_select": {"options": _indexed_items(((data.get("character_select") or {}).get("options")))},
        "shop": {
            "cards": _indexed_items(((data.get("shop") or {}).get("cards")), affordable_key="enough_gold"),
            "relics": _indexed_items(((data.get("shop") or {}).get("relics")), affordable_key="enough_gold"),
            "potions": _indexed_items(((data.get("shop") or {}).get("potions")), affordable_key="enough_gold"),
        },
        "potions": _potions_for_args(data),
    }


def _playable_cards_for_args(state: GameState) -> list[dict[str, Any]]:
    if state.combat is None:
        return []
    targets = [
        {"target_index": enemy.index, "name": enemy.name}
        for enemy in state.combat.enemies
        if enemy.index is not None and enemy.is_alive is not False and enemy.is_hittable is not False
    ]
    return [
        {
            "card_index": card.index,
            "requires_target": card.requires_target,
            "valid_targets": targets if card.requires_target else [],
        }
        for card in state.combat.hand
        if card.playable is True and card.index is not None
    ]


def _indexed_items(
    items: Any,
    *,
    lock_key: str | None = None,
    action_key: str | None = None,
    claimable_key: str | None = None,
    affordable_key: str | None = None,
) -> list[dict[str, Any]]:
    if not isinstance(items, list):
        return []
    result: list[dict[str, Any]] = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            result.append({"option_index": index})
            continue
        row = {"option_index": item.get("index", item.get("option_index", index))}
        if lock_key is not None:
            row["locked"] = item.get(lock_key) or item.get("locked")
        if action_key is not None:
            row["actionable"] = item.get(action_key)
        if claimable_key is not None:
            row["claimable"] = item.get(claimable_key)
        if affordable_key is not None:
            row["affordable"] = item.get(affordable_key)
        result.append(row)
    return result


def _potions_for_args(data: dict[str, Any]) -> list[dict[str, Any]]:
    potions = (data.get("run") or {}).get("potions")
    if not isinstance(potions, list):
        return []
    result = []
    for index, potion in enumerate(potions):
        if not isinstance(potion, dict):
            continue
        result.append(
            {
                "index": potion.get("index", potion.get("i", index)),
                "can_use": potion.get("can_use", potion.get("usable")),
                "can_discard": potion.get("can_discard", potion.get("discard")),
            }
        )
    return result


def _complete_option_index(
    action: str,
    args: dict[str, Any],
    raw_tokens: list[str],
    view: dict[str, Any],
) -> None:
    if not _action_accepts_option_index(action):
        return
    indices = _valid_option_indices(action, view)
    explicit = _explicit_arg_supplied(raw_tokens, {"option_index", "index", "potion_index"})

    if "option_index" in args and explicit:
        _validate_known_index(action, "option_index", args["option_index"], indices)
        return
    if "option_index" in args and raw_tokens:
        _validate_known_index(action, "option_index", args["option_index"], indices)
        return

    if len(indices) == 1:
        args["option_index"] = indices[0]
        return
    if len(indices) > 1:
        args.pop("option_index", None)
        raise BridgeError(
            "ambiguous_action_args",
            f"{action} requires explicit option_index because multiple choices are available.",
            details={"action": action, "valid_option_index": indices},
            retryable=False,
        )


def _complete_play_card_target(
    action: str,
    args: dict[str, Any],
    raw_tokens: list[str],
    view: dict[str, Any],
) -> None:
    if action != "play_card" or "card_index" not in args:
        return
    card = _playable_card(view, args.get("card_index"))
    if card is None or not card.get("requires_target"):
        return
    target_indices = _target_indices(card.get("valid_targets"))
    if "target_index" in args:
        _validate_known_index(action, "target_index", args["target_index"], target_indices)
        return
    if _explicit_arg_supplied(raw_tokens, {"target_index"}):
        return
    if len(target_indices) == 1:
        args["target_index"] = target_indices[0]
        return
    if len(target_indices) > 1:
        raise BridgeError(
            "ambiguous_action_args",
            "play_card requires explicit target_index because multiple targets are available.",
            details={"action": action, "card_index": args.get("card_index"), "valid_target_index": target_indices},
            retryable=False,
        )


def _action_accepts_option_index(action: str) -> bool:
    return action.startswith("buy_") or action in {
        "choose_map_node",
        "claim_reward",
        "choose_event_option",
        "choose_rest_option",
        "choose_reward_card",
        "choose_timeline_epoch",
        "select_character",
        "select_deck_card",
        "use_potion",
        "discard_potion",
    }


def _valid_option_indices(action: str, view: dict[str, Any]) -> list[int]:
    if action == "choose_map_node":
        return _indices((view.get("map") or {}).get("choices"))
    if action == "choose_event_option":
        return _indices((view.get("event") or {}).get("options"), unlocked_only=True)
    if action == "choose_timeline_epoch":
        return _indices((view.get("timeline") or {}).get("slots"), actionable_only=True)
    if action == "choose_rest_option":
        return _indices((view.get("rest") or {}).get("options"), actionable_only=True, unlocked_only=True)
    if action == "claim_reward":
        return _indices((view.get("reward") or {}).get("rewards"), claimable_only=True)
    if action == "choose_reward_card":
        return _indices((view.get("reward") or {}).get("card_options"))
    if action == "select_deck_card":
        return _indices((view.get("selection") or {}).get("cards"))
    if action == "select_character":
        return _indices((view.get("character_select") or {}).get("options"))
    if action == "buy_card":
        return _indices((view.get("shop") or {}).get("cards"), affordable_only=True)
    if action == "buy_relic":
        return _indices((view.get("shop") or {}).get("relics"), affordable_only=True)
    if action == "buy_potion":
        return _indices((view.get("shop") or {}).get("potions"), affordable_only=True)
    if action in {"use_potion", "discard_potion"}:
        key = "can_use" if action == "use_potion" else "can_discard"
        return [
            potion["index"]
            for potion in view.get("potions") or []
            if isinstance(potion, dict) and potion.get(key) and isinstance(potion.get("index"), int)
        ]
    return []


def _indices(
    items: Any,
    *,
    actionable_only: bool = False,
    unlocked_only: bool = False,
    claimable_only: bool = False,
    affordable_only: bool = False,
) -> list[int]:
    if not isinstance(items, list):
        return []
    indices: list[int] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        if actionable_only and item.get("actionable") is False:
            continue
        if unlocked_only and item.get("locked") is True:
            continue
        if claimable_only and item.get("claimable") is False:
            continue
        if affordable_only and item.get("affordable") is False:
            continue
        index = item.get("option_index")
        if isinstance(index, int):
            indices.append(index)
    return indices


def _target_indices(items: Any) -> list[int]:
    if not isinstance(items, list):
        return []
    indices: list[int] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        index = item.get("target_index")
        if isinstance(index, int):
            indices.append(index)
    return indices


def _playable_card(view: dict[str, Any], card_index: Any) -> dict[str, Any] | None:
    combat = view.get("combat") or {}
    cards = combat.get("playable") or combat.get("playable_cards") or []
    for card in cards:
        if isinstance(card, dict) and card.get("card_index") == card_index:
            return card
    return None


def _validate_known_index(action: str, name: str, value: Any, valid_indices: list[int]) -> None:
    if not valid_indices or value in valid_indices:
        return
    raise BridgeError(
        "invalid_action_args",
        f"{action} received invalid {name}.",
        details={"action": action, name: value, f"valid_{name}": valid_indices},
        retryable=False,
    )


def _explicit_arg_supplied(tokens: list[str], names: set[str]) -> bool:
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if not token.startswith("--"):
            return True
        key = token[2:].split("=", 1)[0].replace("-", "_")
        if key in names:
            return True
        if "=" not in token and index + 1 < len(tokens) and not tokens[index + 1].startswith("--"):
            index += 2
        else:
            index += 1
    return False


def _claimable_unloaded_card_rewards(state: GameState) -> list[dict[str, Any]]:
    reward = state.reward if isinstance(state.reward, dict) else None
    if not reward:
        return []
    card_options = reward.get("card_options")
    if isinstance(card_options, list) and card_options:
        return []
    rows = reward.get("rewards")
    if not isinstance(rows, list):
        return []

    result: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        if str(row.get("reward_type")).lower() != "card":
            continue
        if row.get("claimable") is False:
            continue
        result.append(
            {
                "option_index": row.get("index", index),
                "description": row.get("description"),
            }
        )
    return result


def _has_playable_cards(state: GameState) -> bool:
    return bool(state.combat and any(card.playable for card in state.combat.hand))


def _run_text(command: Any) -> None:
    started_at = _now_iso()
    started_monotonic = time.monotonic()
    context = click.get_current_context(silent=True)
    try:
        payload = command()
        typer.echo(payload, nl=not str(payload).endswith("\n"))
        _log_cli_text_result(
            context=context,
            started_at=started_at,
            started_monotonic=started_monotonic,
            return_code=0,
            output=str(payload),
        )
    except BridgeError as exc:
        output = _render_error(exc)
        typer.echo(output, err=False)
        _log_cli_text_result(
            context=context,
            started_at=started_at,
            started_monotonic=started_monotonic,
            return_code=1,
            output=output + "\n",
        )
        raise typer.Exit(code=1) from exc
    except RenderedCliError as exc:
        output = exc.output
        typer.echo(output, nl=not output.endswith("\n"), err=False)
        _log_cli_text_result(
            context=context,
            started_at=started_at,
            started_monotonic=started_monotonic,
            return_code=exc.code,
            output=output if output.endswith("\n") else output + "\n",
        )
        raise typer.Exit(code=exc.code) from exc
    except Exception as exc:
        output = f"ERROR cli_error: {type(exc).__name__}: {exc}"
        typer.echo(output, err=False)
        _log_cli_text_result(
            context=context,
            started_at=started_at,
            started_monotonic=started_monotonic,
            return_code=1,
            output=output + "\n",
        )
        raise typer.Exit(code=1) from exc


class RenderedCliError(RuntimeError):
    def __init__(self, output: str, *, code: int = 1) -> None:
        super().__init__(output)
        self.output = output
        self.code = code


def _log_cli_text_result(
    *,
    context: Any,
    started_at: str,
    started_monotonic: float,
    return_code: int,
    output: str,
) -> None:
    command_path = context.command_path if context is not None else "sts2"
    argv = sys.argv[1:] or command_path.split()[1:]
    if not should_log_cli_call(argv):
        return
    params = dict(context.params) if context is not None else {}
    if context is not None and context.args:
        params["extra_args"] = list(context.args)
    log_cli_call(
        command_path=command_path,
        argv=argv,
        params=params,
        started_at=started_at,
        duration_ms=(time.monotonic() - started_monotonic) * 1000,
        return_code=return_code,
        output=output,
    )


def _dump_model(value: Any) -> Any:
    return _plain_data(value)


def _render_health(data: dict[str, Any]) -> str:
    status = data.get("status") or data.get("state") or "ok"
    lines = [f"Health: {status}"]
    extra = {key: value for key, value in data.items() if key not in {"status", "state"}}
    if extra:
        lines.append(_to_yaml(extra).rstrip())
    return "\n".join(lines) + "\n"


def _render_error(exc: BridgeError) -> str:
    lines = [f"ERROR {exc.code}: {exc.message}"]
    if exc.details:
        lines.extend(["Details:", _to_yaml(exc.details).rstrip()])
    if exc.retryable:
        lines.append("Retryable: true")
    return "\n".join(lines)


def _to_yaml(data: Any) -> str:
    return yaml.safe_dump(_dump_model(data), allow_unicode=True, sort_keys=False).rstrip() + "\n"


def _inline_mapping(data: dict[str, Any]) -> str:
    return ", ".join(f"{key}={value}" for key, value in data.items())


def _try_state(client: Sts2Client) -> GameState | None:
    try:
        return client.state()
    except BridgeError:
        return None


def _recovery_state_summary(state: GameState) -> dict[str, Any]:
    return {
        "screen": state.screen,
        "available_actions": effective_available_actions(state),
        "has_recovery_options": has_recovery_options(state),
        "floor": _run_field(state, "floor"),
        "gold": _run_field(state, "gold"),
    }


def _rest_recovery_point(target: str, x: float | None, y: float | None) -> tuple[float, float]:
    if (x is None) != (y is None):
        raise BridgeError(
            "invalid_cli_arg",
            "--x and --y must be provided together.",
            details={"x": x, "y": y},
            retryable=False,
        )
    if x is not None and y is not None:
        return x, y
    if target not in REST_RECOVERY_TARGETS:
        raise BridgeError(
            "invalid_cli_arg",
            "--target must be one of: relic, top-bar-relic, rest-card, smith-card.",
            details={"target": target},
            retryable=False,
        )
    return REST_RECOVERY_TARGETS[target]


def _rest_recovery_resolved(state: GameState) -> bool:
    return state.screen != "REST" or not has_recovery_options(state)


def _rest_recovery_suggestions(target: str) -> list[str]:
    remaining_targets = [name for name in REST_RECOVERY_TARGETS if name != target]
    suggestions = [f"try: sts2 debug recover-rest --target {name}" for name in remaining_targets]
    suggestions.append("if visual UI is clickable, inspect a screenshot and use sts2 debug click-window with explicit coordinates")
    suggestions.append("if every visual click fails, the REST desync is likely in the backend mod/API state")
    return suggestions


def _run_field(state: GameState, key: str) -> Any:
    return state.run.get(key) if isinstance(state.run, dict) else None


def _plain_data(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return _plain_data(value.model_dump(mode="json", exclude_none=True))
    if isinstance(value, dict):
        return {str(_plain_data(key)): _plain_data(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_plain_data(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if value is None or type(value) in {str, int, float, bool}:
        return value
    if isinstance(value, str):
        return str(value)
    if isinstance(value, bool):
        return bool(value)
    if isinstance(value, int):
        return int(value)
    if isinstance(value, float):
        return float(value)
    return repr(value)


def _require_macos() -> None:
    if sys.platform != "darwin":
        raise BridgeError(
            "unsupported_platform",
            "Window screenshots are currently implemented only on macOS.",
            details={"platform": sys.platform},
            retryable=False,
        )
