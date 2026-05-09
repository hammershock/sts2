from __future__ import annotations

from copy import deepcopy
from importlib.resources import files
import re
from typing import Any

import yaml
from pydantic import BaseModel

from sts2_bridge.models import Card, Enemy, GameState, Intent
from sts2_bridge.state_actions import effective_available_actions, effective_rest_options


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
    if state.screen == "CARD_SELECTION":
        return "state/selection.yaml"
    if state.screen == "REST":
        return "state/rest.yaml"
    if state.screen == "EVENT":
        return "state/event.yaml"
    if state.screen == "SHOP":
        return "state/shop.yaml"
    if state.screen == "GAME_OVER":
        return "state/game_over.yaml"
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
    if name == "available_actions":
        return effective_available_actions(root) if isinstance(root, GameState) else []
    if name == "card_text":
        return _get_path(current, "resolved_rules_text") or _get_path(current, "rules_text")
    if name == "card_type":
        return _card_field(root, current, "card_type")
    if name == "card_rarity":
        return _card_field(root, current, "rarity")
    if name == "card_keywords":
        return _card_keywords(root, current)
    if name == "relics":
        return _relics(root)
    if name == "map_view":
        return _map_view(root)
    if name == "deck":
        return _deck_view(root)
    if name == "piles":
        return _piles_view(root)
    if name == "potions":
        return _potions_view(root)
    if name == "selection":
        return _selection_view(root)
    if name == "rest":
        return _rest_view(root)
    if name == "reward":
        return _reward_view(root)
    if name == "event":
        return _event_view(root)
    if name == "shop":
        return _shop_view(root)
    if name == "game_over":
        return _game_over_view(root)
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
    text = card.resolved_rules_text or card.rules_text
    action: dict[str, Any] = {
        "action": "play_card",
        "card_index": card.index,
        "card_name": card.name,
        "card_type": _card_field(root, card, "card_type"),
        "rarity": _card_field(root, card, "rarity"),
        "requires_target": card.requires_target,
        "cost": card.energy_cost,
        "resolved_rules_text": card.resolved_rules_text,
        "text": text,
        "keywords": _card_keywords(root, card),
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


def _card_field(root: Any, card: Any, field: str) -> Any:
    direct_value = _get_path(card, field)
    if direct_value is not None:
        return direct_value
    if not isinstance(card, Card) or not card.card_id:
        return None

    for candidate in _run_cards(root):
        if not isinstance(candidate, dict):
            continue
        if candidate.get("card_id") != card.card_id:
            continue
        if card.upgraded is not None and candidate.get("upgraded") not in {None, card.upgraded}:
            continue
        value = candidate.get(field)
        if value is not None:
            return value
    return None


def _card_keywords(root: Any, card: Any) -> list[str]:
    direct_value = _get_path(card, "keywords")
    if isinstance(direct_value, list):
        return [str(item) for item in direct_value if item]

    index = _get_path(card, "index")
    for path in ("agent_view.combat.hand", "agent_view.selection.cards", "agent_view.reward.cards"):
        items = _get_path(root, path)
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict) or item.get("i") != index:
                continue
            keywords = item.get("keywords")
            if isinstance(keywords, list):
                return [str(keyword) for keyword in keywords if keyword]
    return []


def _run_cards(root: Any) -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []
    paths = [
        "run.deck",
        "run.piles.draw_cards",
        "run.piles.discard_cards",
        "run.piles.exhaust_cards",
    ]
    for path in paths:
        items = _get_path(root, path)
        if isinstance(items, list):
            cards.extend(item for item in items if isinstance(item, dict))
    return cards


def _relics(root: Any) -> list[dict[str, Any]]:
    items = _get_path(root, "run.relics")
    if not isinstance(items, list):
        return []

    relics: list[dict[str, Any]] = []
    for index, item in enumerate(items):
        if isinstance(item, str):
            relics.append({"index": index, "name": item})
            continue
        if not isinstance(item, dict):
            continue
        relics.append(
            {
                "index": item.get("index", index),
                "name": item.get("name"),
                "relic_id": item.get("relic_id"),
                "description": item.get("description"),
                "stack": item.get("stack"),
                "is_melted": item.get("is_melted"),
            }
        )
    return relics


def _deck_view(root: Any) -> list[str]:
    deck = _get_path(root, "run.deck")
    return _card_stack_summary(deck if isinstance(deck, list) else [])


def _piles_view(root: Any) -> dict[str, Any]:
    piles = _get_path(root, "run.piles")
    result: dict[str, Any] = {}
    for name in ("draw", "discard", "exhaust"):
        cards = []
        if isinstance(piles, dict):
            cards = _pile_cards(piles, name)
        summary = _card_stack_summary(cards)
        count = _get_path(root, f"combat.{name}_pile_count")
        result[name] = summary if summary else ([] if count is None else {"count": count})
    return result


def _potions_view(root: Any) -> list[dict[str, Any]]:
    potions = _get_path(root, "run.potions")
    if not isinstance(potions, list):
        return []

    result: list[dict[str, Any]] = []
    for index, potion in enumerate(potions):
        if not isinstance(potion, dict):
            continue
        result.append(
            {
                "index": potion.get("index", index),
                "name": potion.get("name"),
                "potion_id": potion.get("potion_id"),
                "occupied": potion.get("occupied"),
                "can_use": potion.get("can_use"),
                "can_discard": potion.get("can_discard"),
                "requires_target": potion.get("requires_target"),
                "target_type": potion.get("target_type"),
                "target_index_space": potion.get("target_index_space"),
                "valid_target_indices": potion.get("valid_target_indices"),
                "description": potion.get("description") or potion.get("usage"),
            }
        )
    return result


def _selection_view(root: Any) -> dict[str, Any]:
    selection = _get_path(root, "selection")
    if not isinstance(selection, dict):
        return {}

    cards = selection.get("cards") if isinstance(selection.get("cards"), list) else []
    return {
        "kind": selection.get("kind"),
        "prompt": selection.get("prompt"),
        "min_select": selection.get("min_select"),
        "max_select": selection.get("max_select"),
        "selected_count": selection.get("selected_count"),
        "requires_confirmation": selection.get("requires_confirmation"),
        "can_confirm": selection.get("can_confirm"),
        "cards": [_selection_card_view(root, card) for card in cards if isinstance(card, dict)],
    }


def _selection_card_view(root: Any, card: dict[str, Any]) -> dict[str, Any]:
    return {
        "option_index": card.get("index"),
        "name": card.get("name") or card.get("card_id"),
        "card_id": card.get("card_id"),
        "upgraded": card.get("upgraded"),
        "card_type": card.get("card_type"),
        "rarity": card.get("rarity"),
        "cost": card.get("energy_cost"),
        "resolved_rules_text": card.get("resolved_rules_text") or card.get("rules_text"),
        "keywords": _card_keywords(root, card),
    }


def _rest_view(root: Any) -> dict[str, Any]:
    if not isinstance(root, GameState):
        return {}
    return {"options": effective_rest_options(root)}


def _reward_view(root: Any) -> dict[str, Any]:
    reward = _get_path(root, "reward")
    if not isinstance(reward, dict):
        return {}

    return {
        "pending_card_choice": reward.get("pending_card_choice"),
        "can_proceed": reward.get("can_proceed"),
        "rewards": _reward_rows(root, reward),
        "card_options": _reward_cards(root, reward),
        "alternatives": _reward_alternatives(root, reward),
    }


def _reward_rows(root: Any, reward: dict[str, Any]) -> list[dict[str, Any]]:
    rows = reward.get("rewards") if isinstance(reward.get("rewards"), list) else []
    agent_rows = _indexed_agent_lines(_get_path(root, "agent_view.reward.rewards"))
    result: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        option_index = row.get("index", index)
        result.append(
            {
                "option_index": option_index,
                "reward_type": row.get("reward_type"),
                "description": row.get("description"),
                "claimable": row.get("claimable"),
                "line": agent_rows.get(option_index),
            }
        )
    return result


def _reward_cards(root: Any, reward: dict[str, Any]) -> list[dict[str, Any]]:
    cards = reward.get("card_options") if isinstance(reward.get("card_options"), list) else []
    return [_selection_card_view(root, card) for card in cards if isinstance(card, dict)]


def _reward_alternatives(root: Any, reward: dict[str, Any]) -> list[dict[str, Any]]:
    alternatives = reward.get("alternatives") if isinstance(reward.get("alternatives"), list) else []
    agent_alternatives = _indexed_agent_lines(_get_path(root, "agent_view.reward.alternatives"))
    result: list[dict[str, Any]] = []
    for index, option in enumerate(alternatives):
        if not isinstance(option, dict):
            continue
        option_index = option.get("index", index)
        result.append(
            {
                "option_index": option_index,
                "label": option.get("label") or agent_alternatives.get(option_index),
            }
        )
    return result


def _event_view(root: Any) -> dict[str, Any]:
    event = _get_path(root, "event")
    if not isinstance(event, dict):
        return {}

    agent_options = _indexed_agent_lines(_get_path(root, "agent_view.event.options"))
    options = event.get("options") if isinstance(event.get("options"), list) else []
    return {
        "event_id": event.get("event_id"),
        "title": event.get("title"),
        "description": event.get("description"),
        "is_finished": event.get("is_finished"),
        "options": [
            _event_option_view(option, index, agent_options)
            for index, option in enumerate(options)
            if isinstance(option, dict)
        ],
    }


def _event_option_view(option: dict[str, Any], index: int, agent_options: dict[int, str]) -> dict[str, Any]:
    option_index = option.get("index", index)
    return {
        "option_index": option_index,
        "title": option.get("title") or option.get("label") or option.get("name"),
        "description": option.get("description"),
        "line": agent_options.get(option_index) if isinstance(option_index, int) else None,
        "locked": option.get("is_locked") or option.get("locked"),
        "proceed": option.get("is_proceed") or option.get("proceed"),
        "will_kill_player": option.get("will_kill_player"),
        "has_relic_preview": option.get("has_relic_preview"),
    }


def _shop_view(root: Any) -> dict[str, Any]:
    shop = _get_path(root, "shop")
    if not isinstance(shop, dict):
        return {}

    actions = effective_available_actions(root) if isinstance(root, GameState) else []
    include_inventory = bool(shop.get("is_open") or any(action.startswith("buy_") for action in actions))
    result: dict[str, Any] = {
        "open": shop.get("is_open"),
        "can_open": shop.get("can_open"),
        "can_close": shop.get("can_close"),
        "card_removal": _shop_card_removal(shop.get("card_removal")),
    }
    if include_inventory:
        result.update(
            {
                "cards": [_shop_card(card, index) for index, card in enumerate(_stocked_items(shop.get("cards")))],
                "relics": [_shop_relic(relic, index) for index, relic in enumerate(_stocked_items(shop.get("relics")))],
                "potions": [
                    _shop_potion(potion, index) for index, potion in enumerate(_stocked_items(shop.get("potions")))
                ],
            }
        )
    return result


def _stocked_items(items: Any) -> list[dict[str, Any]]:
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, dict) and item.get("is_stocked") is not False]


def _shop_card(card: dict[str, Any], index: int) -> dict[str, Any]:
    return {
        "option_index": card.get("index", index),
        "name": card.get("name") or card.get("card_id"),
        "card_id": card.get("card_id"),
        "category": card.get("category"),
        "rarity": card.get("rarity"),
        "card_type": card.get("card_type"),
        "cost": "X" if card.get("costs_x") else card.get("energy_cost"),
        "price": card.get("price"),
        "on_sale": card.get("on_sale"),
        "affordable": card.get("enough_gold"),
        "stocked": card.get("is_stocked"),
        "resolved_rules_text": card.get("resolved_rules_text") or card.get("rules_text"),
    }


def _shop_relic(relic: dict[str, Any], index: int) -> dict[str, Any]:
    return {
        "option_index": relic.get("index", index),
        "name": relic.get("name") or relic.get("relic_id"),
        "relic_id": relic.get("relic_id"),
        "rarity": relic.get("rarity"),
        "price": relic.get("price"),
        "affordable": relic.get("enough_gold"),
        "stocked": relic.get("is_stocked"),
    }


def _shop_potion(potion: dict[str, Any], index: int) -> dict[str, Any]:
    return {
        "option_index": potion.get("index", index),
        "name": potion.get("name") or potion.get("potion_id"),
        "potion_id": potion.get("potion_id"),
        "rarity": potion.get("rarity"),
        "usage": potion.get("usage"),
        "price": potion.get("price"),
        "affordable": potion.get("enough_gold"),
        "stocked": potion.get("is_stocked"),
    }


def _shop_card_removal(card_removal: Any) -> dict[str, Any]:
    if not isinstance(card_removal, dict):
        return {}
    return {
        "price": card_removal.get("price"),
        "available": card_removal.get("available"),
        "used": card_removal.get("used"),
        "affordable": card_removal.get("enough_gold"),
    }


def _game_over_view(root: Any) -> dict[str, Any]:
    game_over = _get_path(root, "game_over")
    if not isinstance(game_over, dict):
        return {}

    player = _local_player(root)
    hp = _player_hp(player)
    is_dead = _player_is_dead(player, hp)
    api_victory = game_over.get("is_victory")
    result = "death" if is_dead else ("victory" if api_victory is True else "unknown")
    return {
        "result": result,
        "api_is_victory": api_victory,
        "result_reason": "player_hp_zero" if is_dead else None,
        "floor": game_over.get("floor") or _get_path(root, "run.floor"),
        "character": game_over.get("character_id") or _get_path(root, "run.character_id"),
        "player_hp": hp,
        "player_alive": None if player is None else player.get("is_alive"),
        "can_continue": game_over.get("can_continue"),
        "can_return_to_main_menu": game_over.get("can_return_to_main_menu"),
        "showing_summary": game_over.get("showing_summary"),
    }


def _local_player(root: Any) -> dict[str, Any] | None:
    players = _get_path(root, "run.players")
    if not isinstance(players, list):
        return None
    dict_players = [player for player in players if isinstance(player, dict)]
    for player in dict_players:
        if player.get("is_local"):
            return player
    return dict_players[0] if dict_players else None


def _player_hp(player: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(player, dict):
        return {}
    return {"current": player.get("current_hp"), "max": player.get("max_hp")}


def _player_is_dead(player: dict[str, Any] | None, hp: dict[str, Any]) -> bool:
    if not isinstance(player, dict):
        return False
    return player.get("is_alive") is False or hp.get("current") == 0


def _indexed_agent_lines(items: Any) -> dict[int, str]:
    if not isinstance(items, list):
        return {}
    result: dict[int, str] = {}
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        option_index = item.get("i", index)
        line = item.get("line")
        if isinstance(option_index, int) and isinstance(line, str):
            result[option_index] = line
    return result


def _pile_cards(piles: dict[str, Any], name: str) -> list[Any]:
    card_items = piles.get(f"{name}_cards")
    if isinstance(card_items, list) and card_items:
        return card_items
    line_items = piles.get(name)
    if isinstance(line_items, list):
        return line_items
    return []


def _card_stack_summary(cards: list[Any]) -> list[str]:
    counts: dict[str, int] = {}
    order: list[str] = []
    for card in cards:
        label = _card_label(card)
        if not label:
            continue
        if label not in counts:
            order.append(label)
            counts[label] = 0
        counts[label] += 1
    return [label if counts[label] == 1 else f"{label}*{counts[label]}" for label in order]


def _card_label(card: Any) -> str | None:
    if isinstance(card, dict):
        line = card.get("line")
        if isinstance(line, str) and line:
            return line.split("[", 1)[0].strip()
        name = card.get("name") or card.get("card_id")
        if not name:
            return None
        upgraded = "+" if card.get("upgraded") else ""
        return f"{name}{upgraded}"
    return None


def _map_view(root: Any) -> dict[str, Any]:
    game_map = _get_path(root, "map")
    if not isinstance(game_map, dict):
        return {}

    nodes = [node for node in game_map.get("nodes") or [] if isinstance(node, dict)]
    nodes_by_coord = {(_get_int(node, "row"), _get_int(node, "col")): node for node in nodes}
    available_nodes = [node for node in game_map.get("available_nodes") or [] if isinstance(node, dict)]
    current = game_map.get("current_node") if isinstance(game_map.get("current_node"), dict) else None
    choices = [_map_choice(option, nodes_by_coord) for option in available_nodes]
    reachable = _reachable_from_choices(available_nodes, nodes_by_coord)

    return {
        "current": _coord(current),
        "choices": choices,
        "reachable_rows": _reachable_rows(reachable),
    }


def _map_choice(
    option: dict[str, Any],
    nodes_by_coord: dict[tuple[int | None, int | None], dict[str, Any]],
) -> dict[str, Any]:
    row = _get_int(option, "row")
    col = _get_int(option, "col")
    node = nodes_by_coord.get((row, col), option)
    reachable = _reachable_from(node, nodes_by_coord)
    children = [_coord(child) for child in node.get("children") or [] if isinstance(child, dict)]

    return {
        "option_index": option.get("index"),
        "type": _node_type(node),
        "row": row,
        "col": col,
        "next": [_map_node_ref(nodes_by_coord.get((child.get("row"), child.get("col")), child)) for child in children[:4]],
        "highlights": _map_highlights(reachable),
    }


def _reachable_from_choices(
    choices: list[dict[str, Any]],
    nodes_by_coord: dict[tuple[int | None, int | None], dict[str, Any]],
) -> list[dict[str, Any]]:
    reachable_by_coord: dict[tuple[int | None, int | None], dict[str, Any]] = {}
    for choice in choices:
        node = nodes_by_coord.get((_get_int(choice, "row"), _get_int(choice, "col")), choice)
        for item in _reachable_from(node, nodes_by_coord):
            reachable_by_coord[(_get_int(item, "row"), _get_int(item, "col"))] = item
    return sorted(
        reachable_by_coord.values(),
        key=lambda node: (_get_int(node, "row") or -1, _get_int(node, "col") or -1),
    )


def _reachable_from(
    start: dict[str, Any],
    nodes_by_coord: dict[tuple[int | None, int | None], dict[str, Any]],
) -> list[dict[str, Any]]:
    pending = [start]
    seen: set[tuple[int | None, int | None]] = set()
    reachable: list[dict[str, Any]] = []

    while pending:
        node = pending.pop(0)
        coord = (_get_int(node, "row"), _get_int(node, "col"))
        if coord in seen:
            continue
        seen.add(coord)
        reachable.append(node)
        for child in node.get("children") or []:
            if not isinstance(child, dict):
                continue
            child_node = nodes_by_coord.get((_get_int(child, "row"), _get_int(child, "col")))
            if child_node is not None:
                pending.append(child_node)
    return reachable


def _reachable_rows(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: dict[int, list[str]] = {}
    for node in nodes:
        row = _get_int(node, "row")
        col = _get_int(node, "col")
        if row is None or col is None:
            continue
        rows.setdefault(row, []).append(f"c{col}{_node_symbol(node)}")
    return [{"row": row, "nodes": rows[row]} for row in sorted(rows)]


def _map_highlights(nodes: list[dict[str, Any]]) -> dict[str, list[str]]:
    wanted = {"Elite": "E", "RestSite": "R", "Shop": "S", "Treasure": "T"}
    highlights: dict[str, list[str]] = {symbol: [] for symbol in wanted.values()}
    for node in nodes:
        symbol = wanted.get(_node_type(node))
        row = _get_int(node, "row")
        col = _get_int(node, "col")
        if symbol is not None and row is not None and col is not None:
            highlights[symbol].append(f"r{row}c{col}")
    return {symbol: values[:4] for symbol, values in highlights.items() if values}


def _map_node_ref(node: dict[str, Any]) -> str:
    row = _get_int(node, "row")
    col = _get_int(node, "col")
    if row is None or col is None:
        return _node_symbol(node)
    return f"r{row}c{col}{_node_symbol(node)}"


def _coord(node: dict[str, Any] | None) -> dict[str, int | None]:
    if not isinstance(node, dict):
        return {}
    return {"row": _get_int(node, "row"), "col": _get_int(node, "col")}


def _node_type(node: dict[str, Any]) -> str:
    return str(node.get("node_type") or "Unknown")


def _node_symbol(node: dict[str, Any]) -> str:
    return {
        "Ancient": "A",
        "Boss": "B",
        "Elite": "E",
        "Monster": "M",
        "RestSite": "R",
        "Shop": "S",
        "Treasure": "T",
        "Unknown": "?",
    }.get(_node_type(node), _node_type(node)[:1] or "?")


def _get_int(value: dict[str, Any], key: str) -> int | None:
    item = value.get(key)
    return item if isinstance(item, int) else None


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
    return f"{state.screen} screen with {len(effective_available_actions(state))} legal action(s)."


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
