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
from sts2_bridge.state_actions import effective_available_actions, has_recovery_options
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
        _validate_action_against_state(resolved_action, before)
        result = client.act(resolved_action, args)
        embedded_after = result.state if isinstance(result.state, GameState) else None
        after = _fresh_state_after_action(client, embedded_after)
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
        else:
            data["state"] = build_agent_view(after)
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
            if effective_available_actions(game_state) or has_recovery_options(game_state):
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
        if _state_has_rest_recovery_options(state):
            lines.extend(
                [
                    "",
                    "REST recovery:",
                    "The API accepted the action but left REST without an executable rest-progress action.",
                    "Next: sts2 debug recover-rest",
                ]
            )
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


def _state_has_rest_recovery_options(state: Any) -> bool:
    if not isinstance(state, dict) or state.get("screen") != "REST":
        return False
    rest = state.get("rest")
    if not isinstance(rest, dict):
        return False
    options = rest.get("options")
    if not isinstance(options, list):
        return False
    return any(isinstance(option, dict) and option.get("source") == "fallback" for option in options)


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


def _fresh_state_after_action(client: Sts2Client, fallback: GameState | None) -> GameState | None:
    last_state: GameState | None = None
    for attempt in range(4):
        state = _try_state(client)
        if state is None:
            return fallback if last_state is None else last_state
        last_state = state
        if not _looks_like_transition_state(state):
            return state
        if attempt < 3:
            time.sleep(0.15)
    return last_state or fallback


def _looks_like_transition_state(state: GameState) -> bool:
    if state.screen != "COMBAT" or state.combat is None:
        return False
    if effective_available_actions(state):
        return False
    player = state.combat.player
    if player is None:
        return True
    unknown_player = player.current_hp is None and player.max_hp is None and player.energy is None and player.block is None
    no_combat_content = not state.combat.enemies and not state.combat.hand
    return unknown_player and no_combat_content


def _macos_window_status_or_error() -> dict[str, Any]:
    try:
        _require_macos()
        from sts2_bridge.macos_screenshot import window_status

        return window_status()
    except BridgeError as exc:
        return {"error": exc.to_dict()["error"]}


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
