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
    if data.get("screen") == "EVENT" and isinstance(data.get("event"), dict):
        return render_event_view(data)
    if data.get("screen") == "SHOP" and isinstance(data.get("shop"), dict):
        return render_shop_view(data)
    if data.get("screen") == "GAME_OVER" and isinstance(data.get("game_over"), dict):
        return render_game_over_view(data)
    if data.get("screen") == "MAIN_MENU" and isinstance(data.get("timeline"), dict):
        return render_main_menu_view(data)
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
        if _has_fallback_options(options):
            lines.append("Recovery command: sts2 debug recover-rest")

    actions = data.get("available_actions") or []
    if actions:
        lines.extend(["", "Legal actions:"])
        for index, action in enumerate(actions):
            lines.append(f"[{index}] {_action_signature(action, data)}")

    return "\n".join(lines).rstrip() + "\n"


def render_event_view(data: dict[str, Any]) -> str:
    event = data["event"]
    options = event.get("options") or []

    lines = [_header_line(data)]
    title = event.get("title")
    if title:
        event_id = event.get("event_id")
        suffix = f" ({event_id})" if event_id else ""
        lines.append(f"Event: {_one_line(title)}{suffix}")
    description = event.get("description")
    if description:
        lines.append(f"Text: {_one_line(description)}")

    if options:
        lines.extend(["", "Options:"])
        for option in options:
            lines.append(_event_option_line(option))

    actions = data.get("available_actions") or []
    if actions:
        lines.extend(["", "Legal actions:"])
        for index, action in enumerate(actions):
            lines.append(f"[{index}] {_action_signature(action, data)}")

    return "\n".join(lines).rstrip() + "\n"


def render_shop_view(data: dict[str, Any]) -> str:
    shop = data["shop"]
    lines = [_header_line(data)]
    status = "open" if shop.get("open") else "closed"
    lines.append(f"Shop: {status}")

    removal = shop.get("card_removal") or {}
    if removal:
        lines.append(f"Card removal: {_shop_price_line(removal)}")

    cards = shop.get("cards") or []
    if cards:
        lines.extend(["", "Cards:"])
        for card in cards:
            lines.append(_shop_card_line(card))

    relics = shop.get("relics") or []
    if relics:
        lines.extend(["", "Relics:"])
        for relic in relics:
            lines.append(_shop_item_line(relic))

    potions = shop.get("potions") or []
    if potions:
        lines.extend(["", "Potions:"])
        for potion in potions:
            lines.append(_shop_item_line(potion))

    actions = data.get("available_actions") or []
    if actions:
        lines.extend(["", "Legal actions:"])
        for index, action in enumerate(actions):
            lines.append(f"[{index}] {_action_signature(action, data)}")

    return "\n".join(lines).rstrip() + "\n"


def render_game_over_view(data: dict[str, Any]) -> str:
    game_over = data["game_over"]
    lines = [_header_line(data), f"Result: {game_over.get('result') or 'unknown'}"]
    hp = game_over.get("player_hp") or {}
    details = [
        f"floor {_value(game_over.get('floor'))}",
        f"character {_value(game_over.get('character'))}",
        f"HP {_hp(hp)}",
        f"alive {str(game_over.get('player_alive')).lower()}",
    ]
    lines.append(f"Final: {', '.join(details)}")
    if game_over.get("result") == "death" and game_over.get("api_is_victory") is True:
        lines.append("Note: API victory flag ignored because player HP is 0/dead.")

    actions = data.get("available_actions") or []
    if actions:
        lines.extend(["", "Legal actions:"])
        for index, action in enumerate(actions):
            lines.append(f"[{index}] {_action_signature(action, data)}")

    return "\n".join(lines).rstrip() + "\n"


def render_main_menu_view(data: dict[str, Any]) -> str:
    timeline = data.get("timeline") or {}
    lines = [_header_line(data)]
    if timeline:
        status = []
        if timeline.get("inspect_open"):
            status.append("inspect_open")
        if timeline.get("can_confirm_overlay"):
            status.append("can_confirm")
        if timeline.get("can_choose_epoch"):
            status.append("can_choose")
        if status:
            lines.append(f"Timeline: {', '.join(status)}")

        overlay = timeline.get("overlay") or {}
        if overlay.get("open"):
            if overlay.get("content_available"):
                title = overlay.get("title") or overlay.get("epoch_id") or "selected epoch"
                text = overlay.get("text")
                lines.append(f"Overlay: {_one_line(title)}")
                if text:
                    lines.append(f"Overlay text: {_one_line(text)}")
            else:
                lines.append("Overlay: open, content unavailable from API")

        slots = timeline.get("slots") or []
        if slots:
            lines.extend(["", "Timeline slots:"])
            for slot in slots:
                lines.append(_timeline_slot_line(slot))

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


def _event_option_line(option: dict[str, Any]) -> str:
    title = option.get("title")
    description = option.get("description")
    line = option.get("line")
    if line and not title and not description:
        text = line
    else:
        text = " | ".join(str(item) for item in (title, description) if item)
    traits = [f"[{_value(option.get('option_index'))}] {_one_line(text or 'Option')}"]
    if option.get("locked"):
        traits.append("locked")
    if option.get("proceed"):
        traits.append("proceed")
    if option.get("will_kill_player"):
        traits.append("will kill")
    if option.get("has_relic_preview"):
        traits.append("relic preview")
    return " | ".join(traits)


def _shop_card_line(card: dict[str, Any]) -> str:
    traits = [f"[{_value(card.get('option_index'))}] {card.get('name') or 'Card'}"]
    metadata = " ".join(str(value) for value in [card.get("rarity"), card.get("card_type")] if value)
    if metadata:
        traits.append(metadata)
    if card.get("cost") is not None:
        traits.append(f"cost {card.get('cost')}")
    traits.append(_shop_price_line(card))
    text = card.get("resolved_rules_text")
    if text:
        traits.append(_one_line(text))
    category = card.get("category")
    if category:
        traits.append(str(category))
    return " | ".join(traits)


def _shop_item_line(item: dict[str, Any]) -> str:
    traits = [f"[{_value(item.get('option_index'))}] {item.get('name') or 'Item'}"]
    rarity = item.get("rarity")
    if rarity:
        traits.append(str(rarity))
    usage = item.get("usage")
    if usage:
        traits.append(str(usage))
    traits.append(_shop_price_line(item))
    return " | ".join(traits)


def _shop_price_line(item: dict[str, Any]) -> str:
    price = item.get("price")
    traits = [f"{_value(price)}g"]
    if item.get("on_sale"):
        traits.append("sale")
    if item.get("affordable") is False:
        traits.append("unaffordable")
    elif item.get("affordable") is True:
        traits.append("affordable")
    if item.get("available") is False:
        traits.append("unavailable")
    if item.get("used"):
        traits.append("used")
    return " ".join(traits)


def _timeline_slot_line(slot: dict[str, Any]) -> str:
    traits = [f"[{_value(slot.get('option_index'))}] {slot.get('title') or slot.get('epoch_id') or 'Epoch'}"]
    if slot.get("state"):
        traits.append(str(slot.get("state")))
    if slot.get("epoch_id"):
        traits.append(str(slot.get("epoch_id")))
    if slot.get("actionable") is False:
        traits.append("not actionable")
    elif slot.get("actionable") is True:
        traits.append("actionable")
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
        target_indices = _play_card_target_indices(data)
        if len(target_indices) == 1:
            return f"play_card(card_index, target_index={target_indices[0]})"
        if len(target_indices) > 1:
            return f"play_card(card_index, target_index in {_index_list(target_indices)})"
        return "play_card(card_index)"
    if _action_uses_option_index(action):
        option_indices = _valid_option_indices(action, data)
        if len(option_indices) == 1:
            return f"{action}(option_index={option_indices[0]})"
        if len(option_indices) > 1:
            return f"{action}(option_index in {_index_list(option_indices)})"
        if action in {"use_potion", "discard_potion"}:
            return f"{action}(option_index, optional target_index)"
        return f"{action}(option_index)"
    if action.startswith("buy_"):
        option_indices = _valid_option_indices(action, data)
        if len(option_indices) == 1:
            return f"{action}(option_index={option_indices[0]})"
        if len(option_indices) > 1:
            return f"{action}(option_index in {_index_list(option_indices)})"
        return f"{action}(option_index)"
    if action == "resolve_rewards" and _has_claimable_card_reward((data.get("reward") or {}).get("rewards") or []):
        return "resolve_rewards(may skip unresolved card reward)"
    return action


def _action_uses_option_index(action: str) -> bool:
    return action in {
        "choose_map_node",
        "claim_reward",
        "choose_event_option",
        "choose_rest_option",
        "choose_reward_card",
        "choose_timeline_epoch",
        "select_character",
        "select_deck_card",
        "use_potion",
        "discard_potion",
    }


def _valid_option_indices(action: str, data: dict[str, Any]) -> list[int]:
    if action == "choose_map_node":
        return _indices((data.get("map") or {}).get("choices"))
    if action == "choose_event_option":
        return _indices((data.get("event") or {}).get("options"), unlocked_only=True)
    if action == "choose_timeline_epoch":
        return _indices((data.get("timeline") or {}).get("slots"), actionable_only=True)
    if action == "choose_rest_option":
        return _indices((data.get("rest") or {}).get("options"), actionable_only=True, unlocked_only=True)
    if action == "claim_reward":
        return _indices((data.get("reward") or {}).get("rewards"), claimable_only=True)
    if action == "choose_reward_card":
        return _indices((data.get("reward") or {}).get("card_options"))
    if action == "select_deck_card":
        return _indices((data.get("selection") or {}).get("cards"))
    if action == "buy_card":
        return _indices((data.get("shop") or {}).get("cards"), affordable_only=True)
    if action == "buy_relic":
        return _indices((data.get("shop") or {}).get("relics"), affordable_only=True)
    if action == "buy_potion":
        return _indices((data.get("shop") or {}).get("potions"), affordable_only=True)
    if action in {"use_potion", "discard_potion"}:
        potions = data.get("potions") or []
        key = "can_use" if action == "use_potion" else "can_discard"
        return [
            int(potion["index"])
            for potion in potions
            if isinstance(potion, dict) and potion.get(key) and isinstance(potion.get("index"), int)
        ]
    return []


def _indices(
    items: Any,
    *,
    actionable_only: bool = False,
    unlocked_only: bool = False,
    claimable_only: bool = False,
    affordable_only: bool = False,
) -> list[int]:
    if not isinstance(items, list):
        return []
    indices: list[int] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        if actionable_only and item.get("actionable") is False:
            continue
        if unlocked_only and item.get("locked") is True:
            continue
        if claimable_only and item.get("claimable") is False:
            continue
        if affordable_only and item.get("affordable") is False:
            continue
        index = item.get("option_index")
        if isinstance(index, int):
            indices.append(index)
    return indices


def _index_list(indices: list[int]) -> str:
    return ", ".join(str(index) for index in indices)


def _play_card_target_indices(data: dict[str, Any]) -> list[int]:
    combat = data.get("combat") or {}
    playable = combat.get("playable") or combat.get("playable_cards") or []
    target_indices: list[int] = []
    for card in playable:
        for target in card.get("valid_targets") or []:
            target_index = target.get("target_index")
            if isinstance(target_index, int) and target_index not in target_indices:
                target_indices.append(target_index)
    return target_indices


def _hp(hp: dict[str, Any]) -> str:
    current = _value(hp.get("current"))
    maximum = _value(hp.get("max"))
    return f"{current}/{maximum}"


def _value(value: Any) -> str:
    return "?" if value is None else str(value)


def _clean_markup(text: str) -> str:
    return re.sub(r"\[/?[A-Za-z0-9_#-]+\]", "", text)


def _one_line(value: Any) -> str:
    return re.sub(r"\s+", " ", _clean_markup(str(value))).strip()
