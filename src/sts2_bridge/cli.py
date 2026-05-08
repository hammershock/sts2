from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import Annotated, Any

import click
import typer
import yaml
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
from sts2_bridge.state_actions import effective_available_actions
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
StateLayerOption = Annotated[str, typer.Option("--layer", help="State layer: view, filtered, raw.")]


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
    with_window: Annotated[
        bool,
        typer.Option("--with-window", help="Include macOS STS2 window/frontmost status when available."),
    ] = False,
) -> None:
    """Read the current game state."""
    client = _client(base_url, api_timeout)

    def command() -> str:
        game_state = client.state()
        selected_layer = _select_state_layer(raw=raw, agent_view=agent_view, layer=layer)
        selected_view = _select_state_view(raw=raw, agent_view=agent_view, view=view)

        if selected_layer == "raw":
            data = _dump_model(game_state)
        else:
            data = build_state_view(game_state, selected_view)
        if with_window:
            data["window"] = _macos_window_status_or_error()

        if selected_layer == "view":
            return render_state_view(data)
        return _to_yaml(data)

    _run_text(command)


@app.command()
def actions(
    base_url: BaseUrlOption = None,
    api_timeout: TimeoutOption = 10.0,
) -> None:
    """List actions available in the current state."""
    client = _client(base_url, api_timeout)
    _run_text(lambda: _render_actions(build_actions_view(client.state())))


@app.command(context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
def act(
    ctx: typer.Context,
    action: Annotated[str, typer.Argument(help="Action name, alias, or index from Legal actions.")],
    base_url: BaseUrlOption = None,
    api_timeout: TimeoutOption = 10.0,
    raw_result: Annotated[
        bool,
        typer.Option("--raw-result", help="Return the full action result and post-action agent view as text."),
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
        resolved_action = resolve_action(action, effective_available_actions(before))
        args = parse_action_args(resolved_action, list(ctx.args))
        result = client.act(resolved_action, args)
        after = result.state if isinstance(result.state, GameState) else _try_state(client)
        if not raw_result:
            return _render_action_result(
                build_action_result_view(
                    action=resolved_action,
                    args=args,
                    status=result.status,
                    before=before,
                    after=after,
                )
            )
        data = _dump_model(result)
        if after is None:
            data["state_error"] = {"code": "state_unavailable", "message": "Could not read post-action state."}
        elif data.get("state") is None:
            data["state"] = build_agent_view(after)
        elif isinstance(result.state, GameState):
            data["state"] = build_agent_view(result.state)
        return _to_yaml(data)

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
                game_state = client.state()
            except BridgeError as exc:
                last_error = exc.to_dict()["error"]
                if not exc.retryable:
                    raise
                time.sleep(interval)
                continue
            if effective_available_actions(game_state):
                return render_state_view(build_state_view(game_state, "brief"))
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
    return action, parse_action_args(action, tokens[1:])


def _default_interactive_action(state: GameState) -> tuple[str, dict[str, Any]] | None:
    actions = effective_available_actions(state)
    non_card_actions = [action for action in actions if action != "play_card"]
    if len(actions) == 1 and actions[0] != "play_card":
        action = actions[0]
        return action, parse_action_args(action, [])
    if len(non_card_actions) == 1 and not _has_playable_cards(state):
        action = non_card_actions[0]
        return action, parse_action_args(action, [])
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
    return action, parse_action_args(action, [])


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
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json", exclude_none=True)
    return value


def _render_health(data: dict[str, Any]) -> str:
    status = data.get("status") or data.get("state") or "ok"
    lines = [f"Health: {status}"]
    extra = {key: value for key, value in data.items() if key not in {"status", "state"}}
    if extra:
        lines.append(_to_yaml(extra).rstrip())
    return "\n".join(lines) + "\n"


def _render_actions(data: dict[str, Any]) -> str:
    actions = data.get("available_actions") or []
    if not actions:
        return "Legal actions: none\n"
    lines = ["Legal actions:"]
    for index, action in enumerate(actions):
        name = action.get("action") if isinstance(action, dict) else str(action)
        args = action.get("args") if isinstance(action, dict) else []
        lines.append(f"[{index}] {_action_signature_text(name, args)}")
    return "\n".join(lines) + "\n"


def _render_action_result(data: dict[str, Any]) -> str:
    action = data.get("action")
    action_name = action.get("name") if isinstance(action, dict) else action
    args = action.get("args") if isinstance(action, dict) else None
    lines = [
        f"Action: {action_name or '?'}",
        f"Status: {data.get('status') or '?'}",
    ]
    if args:
        lines.append(f"Args: {_inline_mapping(args)}")
    changes = data.get("changes")
    if changes:
        lines.extend(["", "Changes:", _to_yaml(changes).rstrip()])
    state = data.get("state")
    if state:
        lines.extend(["", "State:", render_state_view(state).rstrip()])
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


def _action_signature_text(name: str, args: list[Any]) -> str:
    if not args:
        return name
    parts: list[str] = []
    for arg in args:
        if not isinstance(arg, dict):
            continue
        arg_name = arg.get("name")
        if not arg_name:
            continue
        if arg_name == "option_index":
            parts.append("option_index=0")
        elif arg.get("required") is True:
            parts.append(str(arg_name))
        else:
            parts.append(f"optional {arg_name}")
    return f"{name}({', '.join(parts)})" if parts else name


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
