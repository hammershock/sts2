from __future__ import annotations

import re
from typing import Any


def render_state_view(data: dict[str, Any]) -> str:
    if data.get("screen") == "COMBAT" and isinstance(data.get("combat"), dict):
        return render_combat_view(data)
    if data.get("screen") == "MAP" and isinstance(data.get("map"), dict):
        return render_map_view(data)
    if data.get("screen") == "CARD_SELECTION" and isinstance(data.get("selection"), dict):
        return render_selection_view(data)
    if data.get("screen") in {"REWARD", "CARD_REWARD"} and isinstance(data.get("reward"), dict):
        return render_reward_view(data)
    if data.get("screen") == "REST" and isinstance(data.get("rest"), dict):
        return render_rest_view(data)
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


def render_selection_view(data: dict[str, Any]) -> str:
    selection = data["selection"]
    cards = selection.get("cards") or []
    prompt = selection.get("prompt")

    lines = [_header_line(data)]
    if prompt:
        lines.append(f"Prompt: {_clean_markup(str(prompt))}")
    details = _selection_details(selection)
    if details:
        lines.append(f"Selection: {details}")

    if cards:
        lines.extend(["", "Options:"])
        for card in cards:
            lines.append(_selection_card_line(card))

    actions = data.get("available_actions") or []
    if actions:
        lines.extend(["", "Legal actions:"])
        for index, action in enumerate(actions):
            lines.append(f"[{index}] {_action_signature(action, data)}")

    glossary = data.get("glossary") or {}
    if glossary:
        lines.extend(["", "Glossary:"])
        for term in sorted(glossary):
            lines.append(f"- {term}: {_clean_markup(glossary[term])}")

    return "\n".join(lines).rstrip() + "\n"


def render_rest_view(data: dict[str, Any]) -> str:
    rest = data["rest"]
    options = rest.get("options") or []

    lines = [_header_line(data)]
    summary = data.get("summary")
    if summary:
        lines.append(f"Summary: {summary}")

    if options:
        heading = "Recovery options:" if _has_fallback_options(options) else "Options:"
        lines.extend(["", heading])
        for option in options:
            lines.append(_rest_option_line(option))

    actions = data.get("available_actions") or []
    if actions:
        lines.extend(["", "Legal actions:"])
        for index, action in enumerate(actions):
            lines.append(f"[{index}] {_action_signature(action, data)}")

    return "\n".join(lines).rstrip() + "\n"


def render_reward_view(data: dict[str, Any]) -> str:
    reward = data["reward"]
    rows = reward.get("rewards") or []
    card_options = reward.get("card_options") or []
    alternatives = reward.get("alternatives") or []

    lines = [_header_line(data)]
    status = _reward_status(reward)
    if status:
        lines.append(f"Reward: {status}")

    if rows:
        lines.extend(["", "Rewards:"])
        for row in rows:
            lines.append(_reward_row_line(row))

    if card_options:
        lines.extend(["", "Card choices:"])
        for card in card_options:
            lines.append(_selection_card_line(card))
    elif _has_claimable_card_reward(rows):
        lines.extend(
            [
                "",
                "Card choices: not loaded",
                "Note: claim the Card reward first; resolve_rewards may skip unresolved card rewards.",
            ]
        )

    if alternatives:
        lines.extend(["", "Alternatives:"])
        for option in alternatives:
            lines.append(_reward_alternative_line(option))

    actions = data.get("available_actions") or []
    if actions:
        lines.extend(["", "Legal actions:"])
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


def _selection_details(selection: dict[str, Any]) -> str:
    parts = []
    if selection.get("kind"):
        parts.append(str(selection["kind"]))
    min_select = selection.get("min_select")
    max_select = selection.get("max_select")
    if min_select is not None or max_select is not None:
        parts.append(f"select {_value(min_select)}-{_value(max_select)}")
    if selection.get("selected_count") is not None:
        parts.append(f"selected {_value(selection.get('selected_count'))}")
    if selection.get("requires_confirmation"):
        parts.append("requires confirm")
    if selection.get("can_confirm"):
        parts.append("can confirm")
    return " | ".join(parts)


def _selection_card_line(card: dict[str, Any]) -> str:
    traits = [
        f"[{_value(card.get('option_index'))}] {card.get('name') or card.get('card_id') or 'Card'}",
    ]
    metadata = " ".join(str(value) for value in [card.get("rarity"), card.get("card_type")] if value)
    if metadata:
        traits.append(metadata)
    if card.get("upgraded"):
        traits.append("upgraded")
    if card.get("cost") is not None:
        traits.append(f"cost {card.get('cost')}")
    text = card.get("resolved_rules_text")
    if text:
        traits.append(_clean_markup(str(text)))
    keywords = card.get("keywords") or []
    if keywords:
        traits.append(f"keywords {', '.join(str(keyword) for keyword in keywords)}")
    return " | ".join(traits)


def _rest_option_line(option: dict[str, Any]) -> str:
    label = option.get("label") or "Option"
    traits = [f"[{_value(option.get('option_index'))}] {label}"]
    description = option.get("description")
    if description:
        traits.append(_clean_markup(str(description)))
    if option.get("locked"):
        traits.append("locked")
    if option.get("source") == "fallback":
        traits.append("recovery: API did not expose executable rest actions")
    return " | ".join(traits)


def _reward_status(reward: dict[str, Any]) -> str:
    parts: list[str] = []
    if reward.get("pending_card_choice") is not None:
        parts.append(f"pending_card_choice={str(reward.get('pending_card_choice')).lower()}")
    if reward.get("can_proceed") is not None:
        parts.append(f"can_proceed={str(reward.get('can_proceed')).lower()}")
    return ", ".join(parts)


def _reward_row_line(row: dict[str, Any]) -> str:
    line = row.get("line")
    if line:
        prefix = f"[{_value(row.get('option_index'))}] {_clean_markup(str(line))}"
    else:
        reward_type = row.get("reward_type") or "Reward"
        description = row.get("description")
        prefix = f"[{_value(row.get('option_index'))}] {reward_type}"
        if description:
            prefix = f"{prefix}: {_clean_markup(str(description))}"
    traits = [prefix]
    if row.get("claimable") is not None:
        traits.append("claimable" if row.get("claimable") else "not claimable")
    return " | ".join(traits)


def _reward_alternative_line(option: dict[str, Any]) -> str:
    return f"[{_value(option.get('option_index'))}] {option.get('label') or 'Alternative'}"


def _has_claimable_card_reward(rows: list[Any]) -> bool:
    for row in rows:
        if not isinstance(row, dict):
            continue
        if str(row.get("reward_type")).lower() == "card" and row.get("claimable") is not False:
            return True
    return False


def _has_fallback_options(options: list[Any]) -> bool:
    return any(isinstance(option, dict) and option.get("source") == "fallback" for option in options)


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
    if action == "resolve_rewards" and _has_claimable_card_reward((data.get("reward") or {}).get("rewards") or []):
        return "resolve_rewards(may skip unresolved card reward)"
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
