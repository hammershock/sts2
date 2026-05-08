from __future__ import annotations

from typing import Any

from sts2_bridge.models import GameState


def effective_available_actions(state: GameState) -> list[str]:
    """Return actions the CLI should expose for the current state."""
    return list(state.available_actions)


def has_recovery_options(state: GameState) -> bool:
    return any(option.get("source") == "fallback" for option in effective_rest_options(state))


def effective_rest_options(state: GameState) -> list[dict[str, Any]]:
    options = _raw_rest_options(state)
    if options:
        return options
    if state.screen != "REST" or (state.available_actions and "choose_rest_option" not in state.available_actions):
        return []
    return [
        {
            "option_index": 0,
            "label": "Rest",
            "description": "Heal at the rest site.",
            "source": "fallback",
        },
        {
            "option_index": 1,
            "label": "Smith",
            "description": "Upgrade one card.",
            "source": "fallback",
        },
    ]


def _raw_rest_options(state: GameState) -> list[dict[str, Any]]:
    rest = state.rest
    if not isinstance(rest, dict):
        return []
    options = rest.get("options")
    if not isinstance(options, list):
        return []

    result: list[dict[str, Any]] = []
    for index, option in enumerate(options):
        if isinstance(option, str):
            result.append({"option_index": index, "label": option, "source": "api"})
        elif isinstance(option, dict):
            result.append(
                {
                    "option_index": option.get("index", option.get("option_index", index)),
                    "label": option.get("title") or option.get("label") or option.get("name") or option.get("text"),
                    "description": option.get("description"),
                    "locked": option.get("is_locked") or option.get("locked"),
                    "source": "api",
                }
            )
    return result
