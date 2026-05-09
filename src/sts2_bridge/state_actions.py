from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sts2_bridge.models import GameState


@dataclass(frozen=True)
class ActionEntry:
    action: str
    args: dict[str, Any] = field(default_factory=dict)


def effective_available_actions(state: GameState) -> list[str]:
    """Return actions the CLI should expose for the current state."""
    return list(state.available_actions)


def effective_visible_action_entries(state: GameState) -> list[ActionEntry]:
    return visible_action_entries(state.available_actions, state.reward if isinstance(state.reward, dict) else None)


def visible_action_entries(actions: list[str], reward: dict[str, Any] | None = None) -> list[ActionEntry]:
    """Return executable action entries shown to users.

    Some raw actions are technically exposed by the HTTP state but guarded by the
    CLI because they would skip unresolved choices. Hide those entries from the
    visible list so numeric action ids match runnable commands.
    """
    if _has_visible_reward_card_choice(reward):
        return [ActionEntry(action) for action in actions if action in {"choose_reward_card", "skip_reward_cards"}]

    card_reward_indices = _claimable_unopened_card_reward_indices(reward)
    claimable_reward_indices = _claimable_reward_indices(reward)
    entries: list[ActionEntry] = []
    for action in actions:
        if card_reward_indices and action in {"resolve_rewards", "collect_rewards_and_proceed"}:
            continue
        if card_reward_indices and action == "claim_reward":
            entries.extend(ActionEntry(action, {"option_index": index}) for index in claimable_reward_indices)
            continue
        entries.append(ActionEntry(action))
    return entries


def has_recovery_options(state: GameState) -> bool:
    return any(option.get("source") == "fallback" for option in effective_rest_options(state))


def effective_rest_options(state: GameState) -> list[dict[str, Any]]:
    options = _raw_rest_options(state)
    if options:
        return options
    if state.screen != "REST" or _has_rest_progress_action(state.available_actions):
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


def _has_rest_progress_action(actions: list[str]) -> bool:
    return any(action in {"choose_rest_option", "proceed", "confirm_selection"} for action in actions)


def _claimable_unopened_card_reward_indices(reward: dict[str, Any] | None) -> list[int]:
    if not reward:
        return []
    card_options = reward.get("card_options")
    if isinstance(card_options, list) and card_options:
        return []
    rows = reward.get("rewards")
    if not isinstance(rows, list):
        return []
    result: list[int] = []
    for fallback_index, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        if str(row.get("reward_type")).lower() != "card":
            continue
        if row.get("claimable") is False:
            continue
        index = row.get("index", fallback_index)
        if isinstance(index, int):
            result.append(index)
    return result


def _has_visible_reward_card_choice(reward: dict[str, Any] | None) -> bool:
    if not reward:
        return False
    card_options = reward.get("card_options")
    return isinstance(card_options, list) and bool(card_options)


def _claimable_reward_indices(reward: dict[str, Any] | None) -> list[int]:
    if not reward:
        return []
    rows = reward.get("rewards")
    if not isinstance(rows, list):
        return []
    result: list[int] = []
    for fallback_index, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        if row.get("claimable") is False:
            continue
        index = row.get("index", fallback_index)
        if isinstance(index, int):
            result.append(index)
    return result
