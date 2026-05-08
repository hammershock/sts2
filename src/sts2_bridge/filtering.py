from __future__ import annotations

from copy import deepcopy
from importlib.resources import files
import re
from typing import Any

import yaml
from pydantic import BaseModel

from sts2_bridge.models import Card, Enemy, GameState, Intent


Schema = dict[str, Any]


def filter_state(state: GameState, view: str = "brief") -> dict[str, Any]:
    schema_name = _state_schema_name(state, view)
    return apply_schema(state, _load_schema(schema_name))


def filter_action_result(payload: dict[str, Any]) -> dict[str, Any]:
    schema_name = "action/with_state.yaml" if payload.get("state") is not None else "action/generic.yaml"
    return apply_schema(payload, _load_schema(schema_name))


def apply_schema(value: Any, schema: Schema) -> dict[str, Any]:
    return _clean(_apply_rule(value, value, schema, value)) or {}


def estimate_incoming_damage(state: GameState) -> int:
    if state.combat is None:
        return 0
    total = 0
    for enemy in state.combat.enemies:
        if enemy.is_alive is False:
            continue
        for intent in enemy.intents:
            if _intent_type(intent) == "attack":
                if intent.total_damage is not None:
                    total += intent.total_damage
                elif intent.damage is not None:
                    total += intent.damage * (intent.hits or 1)
    return total


def _state_schema_name(state: GameState, view: str) -> str:
    if view == "decision":
        return "state/decision.yaml"
    if view == "combat":
        return "state/combat.yaml"
    if view == "agent":
        return "state/agent.yaml"

    if state.screen == "COMBAT":
        return "state/combat_brief.yaml"
    if state.screen == "MAP":
        return "state/map.yaml"
    if state.screen in {"REWARD", "CARD_REWARD"}:
        return "state/reward.yaml"
    return "state/common.yaml"


def _load_schema(name: str) -> Schema:
    schema_path = files("sts2_bridge").joinpath("schemas", name)
    with schema_path.open("r", encoding="utf-8") as handle:
        schema = yaml.safe_load(handle) or {}

    parent = schema.get("extends")
    if parent:
        merged = _load_schema(parent)
        schema = _merge_schema(merged, schema)
    return schema


def _merge_schema(parent: Schema, child: Schema) -> Schema:
    merged = deepcopy(parent)
    for key, value in child.items():
        if key == "fields" and isinstance(value, dict) and isinstance(merged.get("fields"), dict):
            merged["fields"] = {**merged["fields"], **value}
        elif key != "extends":
            merged[key] = value
    return merged


def _apply_rule(root: Any, current: Any, rule: Any, state: Any) -> Any:
    if isinstance(rule, str):
        return _get_path(current, rule)
    if not isinstance(rule, dict):
        return rule

    if "path" in rule and set(rule) == {"path"}:
        return _get_path(current, rule["path"])

    if "transform" in rule:
        return _transform(root, current, rule, state)

    if "list" in rule:
        items = _get_path(current, rule["list"])
        if not isinstance(items, list):
            return []
        item_rule = rule.get("item", {"path": "."})
        where = rule.get("where")
        if where:
            items = [item for item in items if _get_path(item, where)]
        return [_apply_rule(root, item, item_rule, state) for item in items]

    fields = rule.get("fields")
    if isinstance(fields, dict):
        return {name: _apply_rule(root, current, field_rule, state) for name, field_rule in fields.items()}

    return None


def _transform(root: Any, current: Any, rule: Schema, state: Any) -> Any:
    name = rule["transform"]
    if name == "hp_pair":
        paths = rule.get("paths", [])
        return {"current": _get_path(current, paths[0]), "max": _get_path(current, paths[1])}
    if name == "card_text":
        return _get_path(current, "resolved_rules_text") or _get_path(current, "rules_text")
    if name == "incoming_damage":
        if isinstance(root, GameState):
            return estimate_incoming_damage(root)
        return 0
    if name == "intent_summary":
        return _intent_summary(current)
    if name == "valid_targets":
        enemies = _get_path(root, rule.get("path", "combat.enemies"))
        if not isinstance(enemies, list):
            return []
        return [
            {"target_index": enemy.index, "name": enemy.name}
            for enemy in enemies
            if isinstance(enemy, Enemy) and enemy.is_alive is not False and enemy.is_hittable is not False
        ]
    if name == "card_action":
        return _card_action(root, current)
    if name == "state_view":
        state_value = _get_path(current, rule.get("path", "state"))
        return filter_state(state_value) if isinstance(state_value, GameState) else None
    if name == "summary":
        if isinstance(root, GameState):
            return _summary(root)
        return None
    return None


def _card_action(root: Any, card: Any) -> dict[str, Any] | None:
    if not isinstance(card, Card):
        return None
    action: dict[str, Any] = {
        "action": "play_card",
        "card_index": card.index,
        "card_name": card.name,
        "requires_target": card.requires_target,
        "cost": card.energy_cost,
    }
    damage = _card_damage(card)
    block = _card_block(card)
    if damage:
        action["damage"] = damage
    if block:
        action["block"] = block
    if card.requires_target:
        action["valid_targets"] = _transform(root, card, {"transform": "valid_targets"}, root)
    return action


def _summary(state: GameState) -> str:
    if state.combat:
        player = state.combat.player
        incoming = estimate_incoming_damage(state)
        block = 0 if player is None or player.block is None else player.block
        hp = "unknown hp" if player is None else f"{player.current_hp}/{player.max_hp} hp"
        playable = sum(1 for card in state.combat.hand if card.playable)
        enemies = [
            f"{enemy.name or 'Enemy'} {enemy.current_hp}/{enemy.max_hp}"
            for enemy in state.combat.enemies
            if enemy.is_alive is not False
        ]
        return f"{hp}, incoming {incoming} ({max(0, incoming - block)} after block), {playable} playable; enemies: {', '.join(enemies[:3])}"
    return f"{state.screen} screen with {len(state.available_actions)} legal action(s)."


def _intent_summary(enemy: Any) -> str | None:
    if not isinstance(enemy, Enemy):
        return None
    parts: list[str] = []
    for intent in enemy.intents:
        if not isinstance(intent, Intent):
            continue
        intent_type = _intent_type(intent)
        if intent_type == "attack" and intent.damage is not None:
            damage = intent.total_damage if intent.total_damage is not None else intent.damage * (intent.hits or 1)
            parts.append(f"attack {damage}")
        elif intent_type:
            parts.append(intent_type)
    return ", ".join(parts) if parts else enemy.move_id or enemy.intent


def _intent_type(intent: Intent) -> str:
    return (intent.type or intent.intent_type or "").lower()


def _card_damage(card: Card) -> int:
    text = card.resolved_rules_text or card.rules_text or ""
    total = 0
    for match in re.finditer(r"Deal\s+(\d+)\s+damage(?:\s+(\d+)\s+times)?", text, flags=re.IGNORECASE):
        total += int(match.group(1)) * int(match.group(2) or 1)
    for match in re.finditer(r"造成\s*(\d+)\s*点伤害", text):
        total += int(match.group(1))
    return total


def _card_block(card: Card) -> int:
    text = card.resolved_rules_text or card.rules_text or ""
    total = 0
    for match in re.finditer(r"Gain\s+(\d+)\s+Block", text, flags=re.IGNORECASE):
        total += int(match.group(1))
    for match in re.finditer(r"获得\s*(\d+)\s*点格挡", text):
        total += int(match.group(1))
    return total


def _get_path(value: Any, path: str) -> Any:
    if path == ".":
        return value
    current = value
    for part in path.split("."):
        if current is None:
            return None
        if isinstance(current, BaseModel):
            current = getattr(current, part, None)
        elif isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list) and part.isdigit():
            index = int(part)
            current = current[index] if 0 <= index < len(current) else None
        else:
            return None
    return current


def _clean(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return _clean(value.model_dump(mode="json", exclude_none=True))
    if isinstance(value, dict):
        return {
            key: cleaned
            for key, item in value.items()
            if (cleaned := _clean(item)) is not None and cleaned != [] and cleaned != {}
        }
    if isinstance(value, list):
        return [cleaned for item in value if (cleaned := _clean(item)) is not None]
    return value
