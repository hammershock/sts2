from __future__ import annotations

from typing import Any


def render_state_view(data: dict[str, Any]) -> str:
    if data.get("screen") == "COMBAT" and isinstance(data.get("combat"), dict):
        return render_combat_view(data)
    return render_generic_view(data)


def render_combat_view(data: dict[str, Any]) -> str:
    combat = data["combat"]
    player = combat.get("player") or {}
    hp = player.get("hp") or {}
    enemies = combat.get("enemies") or []
    playable = combat.get("playable") or combat.get("playable_cards") or []

    lines = [
        _header_line(data),
        (
            "Player: "
            f"HP {_hp(hp)}, "
            f"Block {_value(player.get('block'))}, "
            f"Energy {_value(player.get('energy'))}, "
            f"Stars {_value(player.get('stars'))}"
        ),
        f"Incoming: {_value(combat.get('incoming_damage'))}",
        "",
    ]

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

    actions = data.get("available_actions") or []
    if actions:
        lines.append("Legal actions:")
        for action in actions:
            if action == "play_card":
                lines.append("- play_card(card_index, optional target_index)")
            else:
                lines.append(f"- {action}")

    return "\n".join(lines).rstrip() + "\n"


def render_generic_view(data: dict[str, Any]) -> str:
    lines = [_header_line(data)]
    summary = data.get("summary")
    if summary:
        lines.append(f"Summary: {summary}")

    actions = data.get("available_actions") or []
    if actions:
        lines.extend(["", "Legal actions:"])
        for action in actions:
            lines.append(f"- {action}")
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
        f"Intent {_value(enemy.get('intent'))}",
    ]
    return " ".join(parts)


def _card_line(card: dict[str, Any]) -> str:
    traits = [
        f"[{_value(card.get('card_index'))}] {card.get('card_name') or 'Card'}",
        f"cost {card.get('cost')}",
        "playable",
    ]
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
    return " | ".join(traits)


def _hp(hp: dict[str, Any]) -> str:
    current = _value(hp.get("current"))
    maximum = _value(hp.get("max"))
    return f"{current}/{maximum}"


def _value(value: Any) -> str:
    return "?" if value is None else str(value)
