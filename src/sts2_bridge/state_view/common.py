from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sts2_bridge.state_view.model import ViewContext, indexed_line, one_line


@dataclass(frozen=True)
class RenderConfig:
    show_run: bool = True
    show_actions: bool = True
    show_glossary: bool = True


def header(ctx: ViewContext) -> str:
    parts = [ctx.screen]
    if ctx.turn is not None:
        parts.append(f"turn={ctx.turn}")
    if ctx.floor is not None:
        parts.append(f"floor={ctx.floor}")
    if ctx.gold is not None:
        parts.append(f"gold={ctx.gold}")
    parts.append(f"route={ctx.route.category}")
    return " ".join(parts)


def section(title: str, lines: list[str]) -> list[str]:
    return ["", f"{title}:"] + [line for line in lines if line]


def actions(ctx: ViewContext) -> list[str]:
    if not ctx.actions:
        return ["No legal actions exposed by /state."]
    return [action_signature(ctx, index, action) for index, action in enumerate(ctx.actions)]


def action_signature(ctx: ViewContext, index: int, action: str) -> str:
    unavailable = _unavailable_action_hint(ctx, action)
    if action == "play_card":
        return _with_unavailable_hint(f"[{index}] sts2 act play_card <card_index>{_target_hint(ctx)}", unavailable)
    if action in {
        "choose_map_node",
        "choose_event_option",
        "choose_rest_option",
        "claim_reward",
        "choose_reward_card",
        "select_deck_card",
        "choose_treasure_relic",
        "choose_timeline_epoch",
        "select_character",
        "choose_capstone_option",
    }:
        values = _valid_option_indices(ctx, action)
        hint = _value_hint("option_index", values)
        return _with_unavailable_hint(f"[{index}] sts2 act {action} {hint}".rstrip(), unavailable)
    if action in {"use_potion", "discard_potion"}:
        values = _valid_potion_indices(ctx, action)
        hint = _value_hint("option_index", values)
        return _with_unavailable_hint(f"[{index}] sts2 act {action} {hint} [target_index]".rstrip(), unavailable)
    if action.startswith("buy_"):
        values = _valid_option_indices(ctx, action)
        hint = _value_hint("option_index", values)
        return _with_unavailable_hint(f"[{index}] sts2 act {action} {hint}".rstrip(), unavailable)
    return _with_unavailable_hint(f"[{index}] sts2 act {action}", unavailable)


def _with_unavailable_hint(line: str, hint: str | None) -> str:
    return f"{line} [unavailable, {hint}]" if hint else line


def _unavailable_action_hint(ctx: ViewContext, action: str) -> str | None:
    if action not in {"resolve_rewards", "collect_rewards_and_proceed"}:
        return None
    card_reward_indices = _claimable_unopened_card_reward_indices(ctx)
    if not card_reward_indices:
        return None
    command = f"sts2 act claim_reward {_value_hint('option_index', card_reward_indices)}"
    return f"use {command} instead"


def run_lines(ctx: ViewContext) -> list[str]:
    run = ctx.agent.get("run") if isinstance(ctx.agent.get("run"), dict) else {}
    relics = run.get("relics") or ctx.run.get("relics") or []
    potions = run.get("potions") or ctx.run.get("potions") or []
    result: list[str] = []
    if relics:
        result.append("Relics: " + ", ".join(str(item) for item in relics))
    if potions:
        result.extend(["Potions:"] + [indexed_line(item, i) for i, item in enumerate(potions)])
    return result


def glossary_lines(ctx: ViewContext) -> list[str]:
    glossary = ctx.agent.get("glossary")
    if not isinstance(glossary, dict) or not glossary:
        return []
    return [f"- {key}: {one_line(value)}" for key, value in sorted(glossary.items())]


def finish(lines: list[str]) -> str:
    return "\n".join(lines).rstrip() + "\n"


def _target_hint(ctx: ViewContext) -> str:
    targets: list[int] = []
    combat = ctx.agent.get("combat")
    hand = combat.get("hand") if isinstance(combat, dict) else []
    for card in hand if isinstance(hand, list) else []:
        if not isinstance(card, dict):
            continue
        for target in card.get("targets") or []:
            if isinstance(target, int) and target not in targets:
                targets.append(target)
    raw_combat = ctx.data.get("combat")
    raw_enemies = raw_combat.get("enemies") if isinstance(raw_combat, dict) else []
    if not targets and isinstance(raw_enemies, list):
        for enemy in raw_enemies:
            if not isinstance(enemy, dict) or enemy.get("is_alive") is False or enemy.get("is_hittable") is False:
                continue
            index = enemy.get("index")
            if isinstance(index, int):
                targets.append(index)
    if len(targets) == 1:
        return f" {targets[0]}"
    if targets:
        return " <target_index>"
    return ""


def _value_hint(name: str, values: list[int]) -> str:
    if len(values) == 1:
        return str(values[0])
    if len(values) > 1:
        return f"<{name} in {', '.join(str(value) for value in values)}>"
    return f"<{name}>"


def _valid_option_indices(ctx: ViewContext, action: str) -> list[int]:
    if action == "choose_map_node":
        return _indices(((ctx.agent.get("map") or {}).get("options"))) or _indices(((ctx.data.get("map") or {}).get("available_nodes")))
    if action == "choose_event_option":
        return _indices(((ctx.agent.get("event") or {}).get("options"))) or _indices(((ctx.data.get("event") or {}).get("options")))
    if action in {"choose_rest_option", "proceed"}:
        return _indices(((ctx.agent.get("rest") or {}).get("options")))
    if action == "claim_reward":
        return _indices(((ctx.agent.get("reward") or {}).get("rewards"))) or _indices(((ctx.data.get("reward") or {}).get("rewards")))
    if action == "choose_reward_card":
        return _indices(((ctx.agent.get("reward") or {}).get("cards")) or ((ctx.agent.get("selection") or {}).get("cards"))) or _indices(((ctx.data.get("reward") or {}).get("card_options")))
    if action in {"select_deck_card", "choose_treasure_relic"}:
        return _indices(((ctx.agent.get("selection") or {}).get("cards")) or ((ctx.agent.get("chest") or {}).get("relics"))) or _indices(((ctx.data.get("selection") or {}).get("cards")))
    if action == "choose_timeline_epoch":
        return _indices(((ctx.agent.get("timeline") or {}).get("slots")), actionable_only=True) or _indices(((ctx.data.get("timeline") or {}).get("slots")), actionable_only=True)
    if action == "select_character":
        return _indices(((ctx.agent.get("character_select") or {}).get("characters"))) or _indices(((ctx.data.get("character_select") or {}).get("characters")))
    if action == "choose_capstone_option":
        return _indices(((ctx.agent.get("capstone") or {}).get("options"))) or _indices(((ctx.data.get("capstone") or {}).get("options")))
    if action == "buy_card":
        return _indices(((ctx.agent.get("shop") or {}).get("cards")))
    if action == "buy_relic":
        return _indices(((ctx.agent.get("shop") or {}).get("relics")))
    if action == "buy_potion":
        return _indices(((ctx.agent.get("shop") or {}).get("potions")))
    return []


def _valid_potion_indices(ctx: ViewContext, action: str) -> list[int]:
    run = ctx.agent.get("run") if isinstance(ctx.agent.get("run"), dict) else {}
    potions = run.get("potions") or []
    flag = "usable" if action == "use_potion" else "discard"
    return [int(item["i"]) for item in potions if isinstance(item, dict) and item.get(flag) and isinstance(item.get("i"), int)]


def _claimable_unopened_card_reward_indices(ctx: ViewContext) -> list[int]:
    reward = ctx.data.get("reward")
    if not isinstance(reward, dict):
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


def _indices(items: Any, *, actionable_only: bool = False) -> list[int]:
    if not isinstance(items, list):
        return []
    result: list[int] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        if actionable_only and item.get("actionable", item.get("is_actionable", True)) is False:
            continue
        index = item.get("i", item.get("index"))
        if isinstance(index, int):
            result.append(index)
    return result
