from __future__ import annotations

from dataclasses import dataclass

from sts2_bridge.state_view.common import RenderConfig, actions, finish, glossary_lines, header, run_lines, section
from sts2_bridge.state_view.model import ViewContext, indexed_line


@dataclass(frozen=True)
class CombatConfig(RenderConfig):
    show_piles: bool = True


def render(ctx: ViewContext, config: CombatConfig = CombatConfig()) -> str:
    agent_combat = ctx.agent.get("combat") if isinstance(ctx.agent.get("combat"), dict) else {}
    raw_combat = ctx.data.get("combat") if isinstance(ctx.data.get("combat"), dict) else {}
    player = _player(agent_combat, raw_combat)
    enemies = _enemies(agent_combat, raw_combat)
    hand = _hand(agent_combat, raw_combat)
    lines = [
        header(ctx),
        f"Player: HP {player.get('hp', '?')} | Block {player.get('block', '?')} | Energy {player.get('energy', '?')} | Stars {player.get('stars', '?')}",
    ]
    if enemies:
        lines += section("Enemies", [_enemy_line(enemy, index) for index, enemy in enumerate(enemies)])
    if hand:
        lines += section("Hand", [_hand_line(card, index) for index, card in enumerate(hand)])
    if config.show_piles:
        piles = _pile_lines(agent_combat)
        if piles:
            lines += section("Piles", piles)
    if config.show_run:
        run = run_lines(ctx)
        if run:
            lines += section("Run", run)
    if config.show_actions:
        lines += section("Legal actions", actions(ctx))
    glossary = glossary_lines(ctx) if config.show_glossary else []
    if glossary:
        lines += section("Glossary", glossary)
    return finish(lines)


def _player(agent_combat: dict[str, object], raw_combat: dict[str, object]) -> dict[str, object]:
    player = agent_combat.get("player")
    if isinstance(player, dict) and player:
        return player
    raw_player = raw_combat.get("player")
    if not isinstance(raw_player, dict):
        return {}
    return {
        "hp": _hp(raw_player),
        "block": raw_player.get("block"),
        "energy": raw_player.get("energy"),
        "stars": raw_player.get("stars"),
    }


def _enemies(agent_combat: dict[str, object], raw_combat: dict[str, object]) -> list[object]:
    enemies = agent_combat.get("enemies")
    if isinstance(enemies, list) and enemies:
        return enemies
    raw_enemies = raw_combat.get("enemies")
    if not isinstance(raw_enemies, list):
        return []
    return [
        {
            "i": enemy.get("index", index),
            "name": enemy.get("name") or enemy.get("enemy_id"),
            "hp": _hp(enemy),
            "block": enemy.get("block"),
            "intent": _intent(enemy),
            "alive": enemy.get("is_alive"),
        }
        for index, enemy in enumerate(raw_enemies)
        if isinstance(enemy, dict)
    ]


def _hand(agent_combat: dict[str, object], raw_combat: dict[str, object]) -> list[object]:
    hand = agent_combat.get("hand")
    if isinstance(hand, list) and hand:
        raw_by_index = {
            card.get("index", index): card
            for index, card in enumerate(raw_combat.get("hand") or [])
            if isinstance(card, dict)
        }
        result: list[object] = []
        for index, item in enumerate(hand):
            if not isinstance(item, dict):
                result.append(item)
                continue
            card = dict(item)
            raw_card = raw_by_index.get(card.get("i", index))
            if isinstance(raw_card, dict):
                card.setdefault("playable", raw_card.get("playable"))
                card.setdefault("why", raw_card.get("unplayable_reason"))
                if raw_card.get("requires_target"):
                    card.setdefault("targets", _raw_targets(raw_combat))
            result.append(card)
        return result
    raw_hand = raw_combat.get("hand")
    if not isinstance(raw_hand, list):
        return []
    return [
        {
            "i": card.get("index", index),
            "line": _card_line(card),
            "playable": card.get("playable"),
            "targets": [],
            "why": card.get("unplayable_reason"),
        }
        for index, card in enumerate(raw_hand)
        if isinstance(card, dict)
    ]


def _enemy_line(enemy: object, index: int) -> str:
    if not isinstance(enemy, dict):
        return str(enemy)
    status = "alive" if enemy.get("alive") is not False else "dead"
    return f"[{enemy.get('i', index)}] {enemy.get('name') or 'Enemy'} | HP {enemy.get('hp', '?')} | Block {enemy.get('block', '?')} | Intent {enemy.get('intent') or enemy.get('move_id') or '?'} | {status}"


def _hand_line(card: object, index: int) -> str:
    if not isinstance(card, dict):
        return str(card)
    playable = "playable" if card.get("playable") else f"unplayable {card.get('why') or ''}".rstrip()
    targets = card.get("targets") or []
    target = "self" if not targets else "targets " + ", ".join(str(item) for item in targets)
    return f"{indexed_line(card, index)} | {playable} | {target}"


def _pile_lines(combat: dict[str, object]) -> list[str]:
    result = []
    for name in ("draw", "discard", "exhaust"):
        pile = combat.get(name)
        if isinstance(pile, list):
            result.append(f"{name}: {len(pile)} item(s)" if len(pile) > 5 else f"{name}: {', '.join(indexed_line(item) for item in pile) or 'empty'}")
    return result


def _hp(item: dict[str, object]) -> str:
    current = item.get("current_hp")
    maximum = item.get("max_hp")
    return f"{current}/{maximum}" if current is not None or maximum is not None else "?"


def _intent(enemy: dict[str, object]) -> object:
    intents = enemy.get("intents")
    if isinstance(intents, list) and intents:
        return ", ".join(str(intent.get("type") or intent.get("intent_type") or intent) for intent in intents if isinstance(intent, dict))
    return enemy.get("intent") or enemy.get("move_id")


def _card_line(card: dict[str, object]) -> str:
    name = card.get("name") or card.get("card_id") or "Card"
    cost = card.get("energy_cost")
    text = card.get("resolved_rules_text") or card.get("rules_text")
    return f"{name} [{cost}]: {text}" if text else f"{name} [{cost}]"


def _raw_targets(raw_combat: dict[str, object]) -> list[int]:
    enemies = raw_combat.get("enemies")
    if not isinstance(enemies, list):
        return []
    result: list[int] = []
    for enemy in enemies:
        if not isinstance(enemy, dict) or enemy.get("is_alive") is False or enemy.get("is_hittable") is False:
            continue
        index = enemy.get("index")
        if isinstance(index, int):
            result.append(index)
    return result
