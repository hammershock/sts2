from __future__ import annotations

import json
from typing import Any

from sts2_bridge.models import BridgeError


POSITIONAL_ARGUMENTS: dict[str, tuple[str, ...]] = {
    "play_card": ("card_index", "target_index"),
    "use_potion": ("potion_index", "target_index"),
    "discard_potion": ("potion_index", "target_index"),
    "choose_map_node": ("option_index",),
    "claim_reward": ("option_index",),
    "choose_event_option": ("option_index",),
    "choose_rest_option": ("option_index",),
    "choose_reward_card": ("option_index",),
    "select_character": ("option_index",),
    "select_deck_card": ("option_index",),
}

DEFAULT_ARGUMENTS: dict[str, dict[str, Any]] = {
    "choose_map_node": {"option_index": 0},
    "claim_reward": {"option_index": 0},
    "choose_event_option": {"option_index": 0},
    "choose_rest_option": {"option_index": 0},
    "choose_reward_card": {"option_index": 0},
    "select_character": {"option_index": 0},
    "select_deck_card": {"option_index": 0},
}


def resolve_action(action_ref: str, available_actions: list[str]) -> str:
    if action_ref.isdigit():
        index = int(action_ref)
        if 0 <= index < len(available_actions):
            return available_actions[index]
        raise BridgeError(
            "invalid_action",
            "Action index is outside the current available action list.",
            details={"action": action_ref, "available_actions": _indexed_actions(available_actions)},
            retryable=False,
        )

    normalized_ref = _normalize_action_name(action_ref)
    for action in available_actions:
        if _normalize_action_name(action) == normalized_ref:
            return action

    raise BridgeError(
        "invalid_action",
        "Action is not available in the current state.",
        details={"action": action_ref, "available_actions": _indexed_actions(available_actions)},
        retryable=False,
    )


def parse_action_args(action: str, tokens: list[str]) -> dict[str, Any]:
    return _parse_tokens(action, tokens)


def _parse_tokens(action: str, tokens: list[str]) -> dict[str, Any]:
    parsed: dict[str, Any] = {}
    positional_names = _positional_names(action)
    positional_index = 0
    seen_keyword = False
    index = 0

    while index < len(tokens):
        token = tokens[index]
        if token.startswith("--"):
            seen_keyword = True
            key, value, index = _parse_keyword(tokens, index)
            _set_arg(parsed, key, value)
            continue

        if seen_keyword:
            raise BridgeError(
                "invalid_cli_arg",
                "Positional action arguments must appear before --key arguments.",
                details={"arg": token},
                retryable=False,
            )
        if positional_index >= len(positional_names):
            raise BridgeError(
                "invalid_cli_arg",
                f"Too many positional arguments for action {action}.",
                details={"action": action, "arg": token, "expected": list(positional_names)},
                retryable=False,
            )
        _set_arg(parsed, positional_names[positional_index], _parse_value(token))
        positional_index += 1
        index += 1

    for key, value in DEFAULT_ARGUMENTS.get(action, {}).items():
        parsed.setdefault(key, value)
    return parsed


def _parse_keyword(tokens: list[str], index: int) -> tuple[str, Any, int]:
    token = tokens[index]
    raw = token[2:]
    if not raw:
        raise BridgeError("invalid_cli_arg", "Action argument name cannot be empty.", details={"arg": token})

    if "=" in raw:
        key, raw_value = raw.split("=", 1)
        if not key:
            raise BridgeError("invalid_cli_arg", "Action argument name cannot be empty.", details={"arg": token})
        key = key.replace("-", "_")
        _reject_legacy_arg(key)
        return key, _parse_value(raw_value), index + 1

    if index + 1 >= len(tokens) or tokens[index + 1].startswith("--"):
        raise BridgeError(
            "invalid_cli_arg",
            "Action --key arguments require a value.",
            details={"arg": token},
            retryable=False,
        )
    key = raw.replace("-", "_")
    _reject_legacy_arg(key)
    return key, _parse_value(tokens[index + 1]), index + 2


def _set_arg(parsed: dict[str, Any], key: str, value: Any) -> None:
    if key in parsed:
        raise BridgeError(
            "invalid_cli_arg",
            "Duplicate action argument.",
            details={"arg": key},
            retryable=False,
        )
    parsed[key] = value


def _positional_names(action: str) -> tuple[str, ...]:
    if action.startswith("buy_"):
        return ("index",)
    return POSITIONAL_ARGUMENTS.get(action, ())


def _normalize_action_name(action: str) -> str:
    return action.replace("_", "").replace("-", "").lower()


def _indexed_actions(actions: list[str]) -> list[dict[str, Any]]:
    return [{"index": index, "action": action} for index, action in enumerate(actions)]


def _reject_legacy_arg(key: str) -> None:
    if key == "arg":
        raise BridgeError(
            "invalid_cli_arg",
            "The legacy --arg key=value syntax is no longer supported. Use positional args or --field value.",
            retryable=False,
        )


def _parse_value(raw_value: str) -> Any:
    lowered = raw_value.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if lowered == "null":
        return None
    try:
        return json.loads(raw_value)
    except json.JSONDecodeError:
        return raw_value
