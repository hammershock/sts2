from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Annotated, Any

import typer
from pydantic import BaseModel

from sts2_bridge.action_args import parse_action_args, resolve_action
from sts2_bridge.agent_view import (
    build_action_result_view,
    build_actions_view,
    build_agent_view,
    build_state_view,
)
from sts2_bridge.client import DEFAULT_BASE_URL, Sts2Client
from sts2_bridge.models import BridgeError, GameState
from sts2_bridge.rendering import render_state_view

app = typer.Typer(no_args_is_help=True, help="Layered CLI bridge for Slay the Spire 2 agent control.")
debug_app = typer.Typer(no_args_is_help=True, help="Debug commands for API and macOS window inspection.")
app.add_typer(debug_app, name="debug")


BaseUrlOption = Annotated[
    str | None,
    typer.Option("--base-url", help="STS2 Mod API base URL. Defaults to STS2_API_BASE_URL or localhost:8080."),
]
TimeoutOption = Annotated[float, typer.Option("--api-timeout", help="HTTP request timeout in seconds.")]
PrettyOption = Annotated[bool, typer.Option("--pretty", help="Pretty-print JSON output.")]
StateLayerOption = Annotated[str, typer.Option("--layer", help="State layer: view, filtered, raw.")]
FormatOption = Annotated[str, typer.Option("--format", help="Output format: text, json.")]


@debug_app.command()
def health(
    base_url: BaseUrlOption = None,
    api_timeout: TimeoutOption = 10.0,
    pretty: PrettyOption = False,
) -> None:
    """Check whether the STS2 Mod API is reachable."""
    client = _client(base_url, api_timeout)
    _run_json(lambda: {"ok": True, "data": client.health()}, pretty)


@app.command()
def state(
    base_url: BaseUrlOption = None,
    api_timeout: TimeoutOption = 10.0,
    raw: Annotated[bool, typer.Option("--raw", help="Return the parsed full state payload.")] = False,
    agent_view: Annotated[bool, typer.Option("--agent-view", help="Return a compact agent-oriented state view.")] = False,
    view: Annotated[
        str,
        typer.Option("--view", help="Filtered schema view: brief, decision, combat, agent."),
    ] = "brief",
    layer: StateLayerOption = "view",
    output_format: FormatOption = "text",
    with_window: Annotated[
        bool,
        typer.Option("--with-window", help="Include macOS STS2 window/frontmost status when available."),
    ] = False,
    pretty: PrettyOption = False,
) -> None:
    """Read the current game state."""
    client = _client(base_url, api_timeout)

    def command() -> dict[str, Any] | str:
        game_state = client.state()
        selected_layer = _select_state_layer(raw=raw, agent_view=agent_view, layer=layer)
        selected_view = _select_state_view(raw=raw, agent_view=agent_view, view=view)

        if selected_layer == "raw":
            data = _dump_model(game_state)
        else:
            data = build_state_view(game_state, selected_view)
        if with_window:
            data["window"] = _macos_window_status_or_error()

        selected_format = _select_output_format(output_format, selected_layer)
        if selected_format == "text":
            return render_state_view(data)
        return {"ok": True, "data": data}

    _run_output(command, pretty)


@app.command()
def actions(
    base_url: BaseUrlOption = None,
    api_timeout: TimeoutOption = 10.0,
    pretty: PrettyOption = False,
) -> None:
    """List actions available in the current state."""
    client = _client(base_url, api_timeout)
    _run_json(lambda: {"ok": True, "data": build_actions_view(client.state())}, pretty)


@app.command(context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
def act(
    ctx: typer.Context,
    action: Annotated[str, typer.Argument(help="Action name, alias, or index from Legal actions.")],
    base_url: BaseUrlOption = None,
    api_timeout: TimeoutOption = 10.0,
    raw_result: Annotated[
        bool,
        typer.Option("--raw-result", help="Return the full action result and post-action agent view."),
    ] = False,
    pretty: PrettyOption = False,
) -> None:
    """Execute one game action. Extra tokens after ACTION are parsed as action args."""
    client = _client(base_url, api_timeout)

    def command() -> dict[str, Any]:
        before = _try_state(client)
        if before is None:
            raise BridgeError(
                "state_unavailable",
                "Cannot resolve action name or index because current state is unavailable.",
                retryable=True,
            )
        resolved_action = resolve_action(action, before.available_actions)
        args = parse_action_args(resolved_action, list(ctx.args))
        result = client.act(resolved_action, args)
        after = result.state if isinstance(result.state, GameState) else _try_state(client)
        if not raw_result:
            return {
                "ok": True,
                "data": build_action_result_view(
                    action=resolved_action,
                    args=args,
                    status=result.status,
                    before=before,
                    after=after,
                ),
            }
        data = _dump_model(result)
        if after is None:
            data["state_error"] = {"code": "state_unavailable", "message": "Could not read post-action state."}
        elif data.get("state") is None:
            data["state"] = build_agent_view(after)
        elif isinstance(result.state, GameState):
            data["state"] = build_agent_view(result.state)
        return {"ok": True, "data": data}

    _run_json(command, pretty)


@app.command()
def wait(
    base_url: BaseUrlOption = None,
    api_timeout: TimeoutOption = 10.0,
    timeout: Annotated[float, typer.Option("--timeout", help="Maximum time to wait in seconds.")] = 30.0,
    interval: Annotated[float, typer.Option("--interval", help="Polling interval in seconds.")] = 0.5,
    pretty: PrettyOption = False,
) -> None:
    """Wait until the game state is readable and has at least one available action."""
    client = _client(base_url, api_timeout)

    def command() -> dict[str, Any]:
        deadline = time.monotonic() + timeout
        last_error: dict[str, Any] | None = None
        while time.monotonic() <= deadline:
            try:
                game_state = client.state()
            except BridgeError as exc:
                last_error = exc.to_dict()["error"]
                if not exc.retryable:
                    raise
                time.sleep(interval)
                continue
            if game_state.available_actions:
                return {"ok": True, "data": build_agent_view(game_state)}
            time.sleep(interval)
        raise BridgeError(
            "wait_timeout",
            "Timed out waiting for an actionable STS2 state.",
            details={"timeout": timeout, "last_error": last_error},
            retryable=True,
        )

    _run_json(command, pretty)


@debug_app.command()
def windows(
    owner: Annotated[str, typer.Option("--owner", help="macOS window owner name to search for.")] = "Slay the Spire 2",
    pretty: PrettyOption = False,
) -> None:
    """List candidate STS2 windows for screenshot fallback debugging."""

    def command() -> dict[str, Any]:
        _require_macos()
        from sts2_bridge.macos_screenshot import list_windows, select_game_window

        windows_data = list_windows(owner)
        selected = None
        try:
            selected = select_game_window(windows_data).to_dict()
        except BridgeError:
            selected = None
        return {
            "ok": True,
            "data": {
                "selected": selected,
                "windows": [window.to_dict() for window in windows_data],
            },
        }

    _run_json(command, pretty)


@debug_app.command("window-status")
def window_status_command(
    owner: Annotated[str, typer.Option("--owner", help="macOS window owner name to search for.")] = "Slay the Spire 2",
    pretty: PrettyOption = False,
) -> None:
    """Report whether the STS2 window exists and is the frontmost app."""

    def command() -> dict[str, Any]:
        _require_macos()
        from sts2_bridge.macos_screenshot import window_status

        return {"ok": True, "data": window_status(owner)}

    _run_json(command, pretty)


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
    pretty: PrettyOption = False,
) -> None:
    """Capture the STS2 game window without bringing it to the foreground."""

    def command() -> dict[str, Any]:
        _require_macos()
        from sts2_bridge.macos_screenshot import capture_window

        return {
            "ok": True,
            "data": capture_window(
                output,
                owner=owner,
                window_id=window_id,
                include_shadow=include_shadow,
                allow_rect_fallback=not no_rect_fallback,
                activate_fallback=activate_fallback,
            ),
        }

    _run_json(command, pretty)


def _client(base_url: str | None, timeout: float) -> Sts2Client:
    return Sts2Client(base_url or os.environ.get("STS2_API_BASE_URL", DEFAULT_BASE_URL), timeout=timeout)


def _run_json(command: Any, pretty: bool) -> None:
    try:
        payload = command()
        _emit(payload, pretty)
    except BridgeError as exc:
        _emit(exc.to_dict(), pretty)
        raise typer.Exit(code=1) from exc


def _run_output(command: Any, pretty: bool) -> None:
    try:
        payload = command()
        if isinstance(payload, str):
            typer.echo(payload, nl=False)
        else:
            _emit(payload, pretty)
    except BridgeError as exc:
        _emit(exc.to_dict(), pretty)
        raise typer.Exit(code=1) from exc


def _emit(payload: dict[str, Any], pretty: bool) -> None:
    typer.echo(json.dumps(payload, ensure_ascii=False, indent=2 if pretty else None, sort_keys=pretty))


def _dump_model(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json", exclude_none=True)
    return value


def _select_state_view(*, raw: bool, agent_view: bool, view: str) -> str:
    if raw:
        return "raw"
    if agent_view:
        return "agent"
    if view not in {"brief", "decision", "combat", "agent"}:
        raise BridgeError(
            "invalid_cli_arg",
            "--view must be one of: brief, decision, combat, agent.",
            details={"view": view},
            retryable=False,
        )
    return view


def _select_state_layer(*, raw: bool, agent_view: bool, layer: str) -> str:
    if raw:
        return "raw"
    if agent_view:
        return "filtered"
    if layer not in {"view", "filtered", "raw"}:
        raise BridgeError(
            "invalid_cli_arg",
            "--layer must be one of: view, filtered, raw.",
            details={"layer": layer},
            retryable=False,
        )
    return layer


def _select_output_format(output_format: str, layer: str) -> str:
    if output_format not in {"text", "json"}:
        raise BridgeError(
            "invalid_cli_arg",
            "--format must be one of: text, json.",
            details={"format": output_format},
            retryable=False,
        )
    if output_format == "text" and layer == "raw":
        return "json"
    if output_format == "text" and layer == "filtered":
        return "json"
    return output_format


def _try_state(client: Sts2Client) -> GameState | None:
    try:
        return client.state()
    except BridgeError:
        return None


def _macos_window_status_or_error() -> dict[str, Any]:
    try:
        _require_macos()
        from sts2_bridge.macos_screenshot import window_status

        return window_status()
    except BridgeError as exc:
        return {"error": exc.to_dict()["error"]}


def _require_macos() -> None:
    if sys.platform != "darwin":
        raise BridgeError(
            "unsupported_platform",
            "Window screenshots are currently implemented only on macOS.",
            details={"platform": sys.platform},
            retryable=False,
        )
