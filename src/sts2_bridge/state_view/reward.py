from __future__ import annotations

from dataclasses import dataclass

from sts2_bridge.state_view.common import RenderConfig, actions, finish, header, section
from sts2_bridge.state_view.model import ViewContext, indexed_line


@dataclass(frozen=True)
class RewardConfig(RenderConfig):
    pass


def render(ctx: ViewContext, config: RewardConfig = RewardConfig(show_glossary=False)) -> str:
    reward = ctx.agent.get("reward") if isinstance(ctx.agent.get("reward"), dict) else {}
    raw_reward = ctx.data.get("reward") if isinstance(ctx.data.get("reward"), dict) else {}
    selection = ctx.agent.get("selection") if isinstance(ctx.agent.get("selection"), dict) else {}
    lines = [header(ctx)]
    if raw_reward:
        lines.append(
            f"Reward: pending_card_choice={str(raw_reward.get('pending_card_choice')).lower()}, can_proceed={str(raw_reward.get('can_proceed')).lower()}"
        )
    rewards = reward.get("rewards") or _raw_rewards(raw_reward)
    if isinstance(rewards, list) and rewards:
        lines += section("Rewards", [indexed_line(row, index) for index, row in enumerate(rewards)])
    cards = reward.get("cards") or reward.get("card_options") or selection.get("cards") or _raw_cards(raw_reward)
    if isinstance(cards, list) and cards:
        lines += section("Card choices", [indexed_line(card, index) for index, card in enumerate(cards)])
    alternatives = reward.get("alternatives")
    if isinstance(alternatives, list) and alternatives:
        lines += section("Alternatives", [indexed_line(option, index) for index, option in enumerate(alternatives)])
    if config.show_actions:
        lines += section("Legal actions", actions(ctx))
    return finish(lines)


def _raw_rewards(reward: dict[str, object]) -> list[dict[str, object]]:
    rows = reward.get("rewards")
    if not isinstance(rows, list):
        return []
    return [
        {
            "i": row.get("index", index),
            "line": f"{row.get('reward_type') or 'Reward'}: {row.get('description') or ''}".rstrip(),
        }
        for index, row in enumerate(rows)
        if isinstance(row, dict)
    ]


def _raw_cards(reward: dict[str, object]) -> list[dict[str, object]]:
    cards = reward.get("card_options")
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
