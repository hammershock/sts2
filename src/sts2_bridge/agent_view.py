from __future__ import annotations

from typing import Any

from sts2_bridge.filtering import filter_action_result, filter_state
from sts2_bridge.models import Card, Enemy, GameState
from sts2_bridge.state_actions import effective_available_actions


def build_state_view(state: GameState, view: str = "brief") -> dict[str, Any]:
    return filter_state(state, view)


def build_agent_view(state: GameState) -> dict[str, Any]:
    return filter_state(state, "agent")


def build_brief_view(state: GameState) -> dict[str, Any]:
    return filter_state(state, "brief")


def build_decision_view(state: GameState) -> dict[str, Any]:
    view = filter_state(state, "decision")
    view["legal_actions"] = build_actions_view(state)["available_actions"]
    return _clean(view)


def build_combat_view(state: GameState) -> dict[str, Any]:
    return filter_state(state, "combat").get("combat", {})


def build_action_result_view(
    *,
    action: str,
    args: dict[str, Any],
    status: str | None,
    before: GameState | None,
    after: GameState | None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "status": status or "completed",
        "action": {"name": action, "args": args},
    }
    if after is not None:
        payload["state"] = filter_state(after)
    if before is not None and after is not None:
        payload["changes"] = _state_delta(before, after)
    return filter_action_result(payload)


def build_actions_view(state: GameState) -> dict[str, Any]:
    return {
        "screen": state.screen,
        "available_actions": [
            {
                "action": action,
                "args": _action_args(action),
            }
            for action in effective_available_actions(state)
        ],
    }


def _action_args(action: str) -> list[dict[str, Any]]:
    if action == "play_card":
        return [
            {"name": "card_index", "type": "int", "required": True},
            {"name": "target_index", "type": "int", "required": "when card requires target"},
        ]
    if action in {"use_potion", "discard_potion"}:
        return [
            {"name": "option_index", "type": "int", "required": True},
            {"name": "target_index", "type": "int", "required": "when potion requires target"},
        ]
    if action in {
        "choose_map_node",
        "claim_reward",
        "choose_event_option",
        "choose_rest_option",
        "choose_reward_card",
        "select_character",
        "select_deck_card",
    }:
        return [{"name": "option_index", "type": "int", "required": True}]
    if action.startswith("buy_"):
        return [{"name": "option_index", "type": "int", "required": True}]
    return []


def _state_delta(before: GameState, after: GameState) -> dict[str, Any]:
    delta: dict[str, Any] = {}
    for field in ("screen", "turn", "in_combat"):
        before_value = getattr(before, field)
        after_value = getattr(after, field)
        if before_value != after_value:
            delta[field] = {"from": before_value, "to": after_value}

    if before.combat or after.combat:
        combat_delta = _combat_delta(before, after)
        if combat_delta:
            delta["combat"] = combat_delta

    before_actions = effective_available_actions(before)
    after_actions = effective_available_actions(after)
    if before_actions != after_actions:
        delta["available_actions"] = {"from": before_actions, "to": after_actions}

    return delta


def _combat_delta(before: GameState, after: GameState) -> dict[str, Any]:
    before_combat = before.combat
    after_combat = after.combat
    delta: dict[str, Any] = {}

    before_player = before_combat.player if before_combat else None
    after_player = after_combat.player if after_combat else None
    if before_player or after_player:
        player_delta = _field_delta(before_player, after_player, ("current_hp", "block", "energy", "stars"))
        if player_delta:
            delta["player"] = player_delta

    before_enemies = {enemy.index: enemy for enemy in before_combat.enemies} if before_combat else {}
    after_enemies = {enemy.index: enemy for enemy in after_combat.enemies} if after_combat else {}
    enemy_changes: list[dict[str, Any]] = []
    for index in sorted(set(before_enemies) | set(after_enemies), key=lambda value: -1 if value is None else value):
        enemy_delta = _enemy_delta(before_enemies.get(index), after_enemies.get(index))
        if enemy_delta:
            enemy_changes.append(enemy_delta)
    if enemy_changes:
        delta["enemies"] = enemy_changes

    before_hand = _hand_signature(before_combat.hand if before_combat else [])
    after_hand = _hand_signature(after_combat.hand if after_combat else [])
    if before_hand != after_hand:
        delta["hand"] = {"from": before_hand, "to": after_hand}

    return delta


def _enemy_delta(before: Enemy | None, after: Enemy | None) -> dict[str, Any]:
    reference = after or before
    if reference is None:
        return {}
    delta = {"index": reference.index, "name": reference.name}
    delta.update(_field_delta(before, after, ("current_hp", "block", "is_alive")))
    return _clean(delta) if len(delta) > 2 else {}


def _field_delta(before: Any, after: Any, fields: tuple[str, ...]) -> dict[str, Any]:
    delta: dict[str, Any] = {}
    for field in fields:
        before_value = getattr(before, field, None)
        after_value = getattr(after, field, None)
        if before_value != after_value:
            change: dict[str, Any] = {"from": before_value, "to": after_value}
            if isinstance(before_value, int) and isinstance(after_value, int):
                change["delta"] = after_value - before_value
            delta[field] = change
    return delta


def _hand_signature(cards: list[Card]) -> list[dict[str, Any]]:
    return [_clean({"index": card.index, "name": card.name, "playable": card.playable}) for card in cards]


def _clean(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: cleaned
            for key, item in value.items()
            if (cleaned := _clean(item)) is not None and cleaned != [] and cleaned != {}
        }
    if isinstance(value, list):
        return [cleaned for item in value if (cleaned := _clean(item)) is not None]
    return value
