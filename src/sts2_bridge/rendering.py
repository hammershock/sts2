from __future__ import annotations

import re
from typing import Any


def render_state_view(data: dict[str, Any]) -> str:
    if data.get("screen") == "COMBAT" and isinstance(data.get("combat"), dict):
        return render_combat_view(data)
    if data.get("screen") == "MAP" and isinstance(data.get("map"), dict):
        return render_map_view(data)
    return render_generic_view(data)


def render_combat_view(data: dict[str, Any]) -> str:
    combat = data["combat"]
    player = combat.get("player") or {}
    hp = player.get("hp") or {}
    enemies = combat.get("enemies") or []
    playable = combat.get("playable") or combat.get("playable_cards") or []
    relics = data.get("relics") or []
    glossary = data.get("glossary") or {}

    player_parts = [
        f"HP {_hp(hp)}",
        f"Block {_value(player.get('block'))}",
        f"Energy {_value(player.get('energy'))}",
    ]
    if player.get("stars"):
        player_parts.append(f"Stars {player['stars']}")

    lines = [
        _header_line(data),
        f"Player: {', '.join(player_parts)}",
        f"Player powers: {_powers(player.get('powers'))}",
        f"Incoming attack damage: {_value(combat.get('incoming_damage'))}",
        "",
    ]

    if relics:
        lines.append("Relics:")
        for relic in relics:
            lines.append(_relic_line(relic))
        lines.append("")

    if enemies:
        lines.append("Enemies:")
        for enemy in enemies:
            lines.append(_enemy_line(enemy))
        lines.append("")

    if playable:
        lines.append("Hand:")
        for card in playable:
            lines.append(_card_line(card))
        lines.append("")

    piles = combat.get("piles") or {}
    if piles:
        lines.append("Piles:")
        for name in ("draw", "discard", "exhaust"):
            lines.append(f"{name.title()}: {_card_list_or_count(piles.get(name))}")
        lines.append("")

    deck = data.get("deck") or []
    if deck:
        lines.append(f"Deck: {_card_list(deck)}")
        lines.append("")

    potions = data.get("potions") or []
    if potions:
        lines.append("Potions:")
        for potion in potions:
            lines.append(_potion_line(potion))
        lines.append("")

    actions = data.get("available_actions") or []
    if actions:
        lines.append("Legal actions:")
        for index, action in enumerate(actions):
            lines.append(f"[{index}] {_action_signature(action, data)}")

    if glossary:
        if actions:
            lines.append("")
        lines.append("Glossary:")
        for term in sorted(glossary):
            lines.append(f"- {term}: {_clean_markup(glossary[term])}")

    return "\n".join(lines).rstrip() + "\n"


def render_generic_view(data: dict[str, Any]) -> str:
    lines = [_header_line(data)]
    summary = data.get("summary")
    if summary:
        lines.append(f"Summary: {summary}")

    actions = data.get("available_actions") or []
    if actions:
        lines.extend(["", "Legal actions:"])
        for index, action in enumerate(actions):
            lines.append(f"[{index}] {_action_signature(action, data)}")
    return "\n".join(lines).rstrip() + "\n"


def render_map_view(data: dict[str, Any]) -> str:
    game_map = data["map"]
    current = game_map.get("current") or {}
    choices = game_map.get("choices") or []
    reachable_rows = game_map.get("reachable_rows") or []

    lines = [
        _header_line(data),
        f"Current: r{_value(current.get('row'))}c{_value(current.get('col'))}",
        "Legend: M=Monster, E=Elite, R=Rest, T=Treasure, S=Shop, ?=Unknown, B=Boss",
        "",
    ]

    if choices:
        lines.append("Choices:")
        for choice in choices:
            lines.append(_map_choice_line(choice))
        lines.append("")

    if reachable_rows:
        lines.append("Reachable map:")
        for row in reachable_rows:
            lines.append(f"r{row.get('row')}: {', '.join(row.get('nodes') or [])}")
        lines.append("")

    actions = data.get("available_actions") or []
    if actions:
        lines.append("Legal actions:")
        for index, action in enumerate(actions):
            lines.append(f"[{index}] {_action_signature(action, data)}")

    return "\n".join(lines).rstrip() + "\n"


def _header_line(data: dict[str, Any]) -> str:
    parts = [str(data.get("screen") or "UNKNOWN")]
    if data.get("turn") is not None:
        parts.append(f"turn={data['turn']}")
    if data.get("floor") is not None:
        parts.append(f"floor={data['floor']}")
    if data.get("gold") is not None:
        parts.append(f"gold={data['gold']}")
    return " ".join(parts)


def _enemy_line(enemy: dict[str, Any]) -> str:
    hp = enemy.get("hp") or {}
    parts = [
        f"[{_value(enemy.get('index'))}] {enemy.get('name') or 'Enemy'}:",
        f"HP {_hp(hp)},",
        f"Block {_value(enemy.get('block'))},",
        f"Intents {_value(enemy.get('intents') or enemy.get('intent'))},",
        f"Powers {_powers(enemy.get('powers'))}",
    ]
    return " ".join(parts)


def _card_line(card: dict[str, Any]) -> str:
    traits = [
        f"[{_value(card.get('card_index'))}] {card.get('card_name') or 'Card'}",
    ]
    metadata = " ".join(str(value) for value in [card.get("rarity"), card.get("card_type")] if value)
    if metadata:
        traits.append(metadata)
    traits.extend([f"cost {card.get('cost')}", "playable"])

    text = card.get("resolved_rules_text") or card.get("text")
    if not text:
        if card.get("damage") is not None:
            traits.append(f"damage {card['damage']}")
        if card.get("block") is not None:
            traits.append(f"block {card['block']}")

    target = "self"
    if card.get("requires_target"):
        targets = card.get("valid_targets") or []
        target_ids = [f"enemy[{target['target_index']}]" for target in targets if target.get("target_index") is not None]
        target = ", ".join(target_ids) if target_ids else "enemy"
    traits.append(f"target {target}")
    if text:
        traits.append(_clean_markup(str(text)))
    keywords = card.get("keywords") or []
    if keywords:
        traits.append(f"keywords {', '.join(str(keyword) for keyword in keywords)}")
    return " | ".join(traits)


def _relic_line(relic: dict[str, Any]) -> str:
    name = relic.get("name") or relic.get("relic_id") or "Relic"
    prefix = f"[{_value(relic.get('index'))}] {name}"
    description = relic.get("description")
    if description:
        return f"{prefix}: {_clean_markup(str(description))}"
    return prefix


def _potion_line(potion: dict[str, Any]) -> str:
    index = _value(potion.get("index"))
    if not potion.get("occupied"):
        return f"[{index}] empty"
    traits = [f"[{index}] {potion.get('name') or potion.get('potion_id') or 'Potion'}"]
    traits.append("usable" if potion.get("can_use") else "not usable")
    if potion.get("can_discard"):
        traits.append("discardable")
    target = potion.get("target_type") or potion.get("target_index_space")
    if target:
        traits.append(f"target {target}")
    if potion.get("requires_target") is not None:
        traits.append("requires target" if potion.get("requires_target") else "no explicit target")
    valid_targets = potion.get("valid_target_indices") or []
    if valid_targets:
        traits.append(f"targets {', '.join(str(target) for target in valid_targets)}")
    description = potion.get("description")
    if description:
        traits.append(_clean_markup(str(description)))
    return " | ".join(traits)


def _powers(powers: Any) -> str:
    if not powers:
        return "none"
    parts: list[str] = []
    for power in powers:
        if not isinstance(power, dict):
            continue
        name = power.get("name") or power.get("power_id") or "Power"
        amount = power.get("amount")
        parts.append(str(name) if amount is None else f"{name} {amount}")
    return ", ".join(parts) if parts else "none"


def _card_list_or_count(value: Any) -> str:
    if isinstance(value, dict) and value.get("count") is not None:
        return f"{value['count']} card(s)"
    if isinstance(value, list):
        return _card_list(value)
    return "empty"


def _card_list(cards: list[Any]) -> str:
    return ", ".join(str(card) for card in cards) if cards else "empty"


def _map_choice_line(choice: dict[str, Any]) -> str:
    option = _value(choice.get("option_index"))
    row = _value(choice.get("row"))
    col = _value(choice.get("col"))
    symbol = _map_symbol(choice.get("type"))
    parts = [f"[{option}] {symbol} r{row}c{col}"]
    next_nodes = choice.get("next") or []
    if next_nodes:
        parts.append(f"next {', '.join(next_nodes)}")
    highlights = choice.get("highlights") or {}
    if highlights:
        summary = " ".join(f"{key}:{','.join(values)}" for key, values in highlights.items() if values)
        if summary:
            parts.append(f"key {summary}")
    return " | ".join(parts)


def _map_symbol(node_type: Any) -> str:
    return {
        "Ancient": "A",
        "Boss": "B",
        "Elite": "E",
        "Monster": "M",
        "RestSite": "R",
        "Shop": "S",
        "Treasure": "T",
        "Unknown": "?",
    }.get(str(node_type), str(node_type or "?")[:1])


def _action_signature(action: str, data: dict[str, Any]) -> str:
    if action == "play_card":
        default_target = _default_target_index(data)
        if default_target is None:
            return "play_card(card_index)"
        return f"play_card(card_index, target_index={default_target})"
    if action in {
        "choose_map_node",
        "claim_reward",
        "choose_event_option",
        "choose_rest_option",
        "choose_reward_card",
        "select_character",
        "select_deck_card",
        "use_potion",
        "discard_potion",
    }:
        return f"{action}(option_index=0)"
    if action.startswith("buy_"):
        return f"{action}(option_index=0)"
    return action


def _default_target_index(data: dict[str, Any]) -> int | None:
    combat = data.get("combat") or {}
    playable = combat.get("playable") or combat.get("playable_cards") or []
    for card in playable:
        for target in card.get("valid_targets") or []:
            target_index = target.get("target_index")
            if target_index is not None:
                return target_index
    return None


def _hp(hp: dict[str, Any]) -> str:
    current = _value(hp.get("current"))
    maximum = _value(hp.get("max"))
    return f"{current}/{maximum}"


def _value(value: Any) -> str:
    return "?" if value is None else str(value)


def _clean_markup(text: str) -> str:
    return re.sub(r"\[/?[A-Za-z0-9_#-]+\]", "", text)
