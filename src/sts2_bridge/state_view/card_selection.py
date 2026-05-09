from __future__ import annotations

from dataclasses import dataclass

from sts2_bridge.state_view.common import RenderConfig, actions, finish, header, section
from sts2_bridge.state_view.model import ViewContext, indexed_line, one_line


@dataclass(frozen=True)
class CardSelectionConfig(RenderConfig):
    pass


def render(ctx: ViewContext, config: CardSelectionConfig = CardSelectionConfig()) -> str:
    selection = ctx.agent.get("selection") if isinstance(ctx.agent.get("selection"), dict) else {}
    raw_selection = ctx.data.get("selection") if isinstance(ctx.data.get("selection"), dict) else {}
    lines = [header(ctx)]
    prompt = selection.get("prompt") or raw_selection.get("prompt")
    if prompt:
        lines.append(f"Prompt: {one_line(prompt)}")
    cards = selection.get("cards") or _raw_cards(raw_selection)
    if isinstance(cards, list) and cards:
        lines += section("Options", [indexed_line(card, index) for index, card in enumerate(cards)])
    if config.show_actions:
        lines += section("Legal actions", actions(ctx))
    return finish(lines)


def _raw_cards(selection: dict[str, object]) -> list[dict[str, object]]:
    cards = selection.get("cards")
    if not isinstance(cards, list):
        return []
    return [
        {
            "i": card.get("index", index),
            "line": _card_line(card),
        }
        for index, card in enumerate(cards)
        if isinstance(card, dict)
    ]


def _card_line(card: dict[str, object]) -> str:
    name = card.get("name") or card.get("card_id") or "Card"
    cost = card.get("energy_cost")
    text = card.get("resolved_rules_text") or card.get("rules_text")
    return f"{name} [{cost}]: {text}" if text else f"{name} [{cost}]"
