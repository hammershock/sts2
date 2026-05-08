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


def parse_action_args(action: str, tokens: list[str], legacy_args: list[str] | None = None) -> dict[str, Any]:
    parsed: dict[str, Any] = {}
    _merge_args(parsed, _parse_legacy_args(legacy_args or []))
    _merge_args(parsed, _parse_tokens(action, tokens))
    return parsed


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
        return key.replace("-", "_"), _parse_value(raw_value), index + 1

    if index + 1 >= len(tokens) or tokens[index + 1].startswith("--"):
        raise BridgeError(
            "invalid_cli_arg",
            "Action --key arguments require a value.",
            details={"arg": token},
            retryable=False,
        )
    return raw.replace("-", "_"), _parse_value(tokens[index + 1]), index + 2


def _parse_legacy_args(items: list[str]) -> dict[str, Any]:
    parsed: dict[str, Any] = {}
    for item in items:
        if "=" not in item:
            raise BridgeError(
                "invalid_cli_arg",
                "Action arguments must use key=value form.",
                details={"arg": item},
                retryable=False,
            )
        key, raw_value = item.split("=", 1)
        if not key:
            raise BridgeError("invalid_cli_arg", "Action argument key cannot be empty.", details={"arg": item})
        _set_arg(parsed, key, _parse_value(raw_value))
    return parsed


def _merge_args(target: dict[str, Any], source: dict[str, Any]) -> None:
    for key, value in source.items():
        _set_arg(target, key, value)


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
