from __future__ import annotations

from dataclasses import dataclass

from sts2_bridge.state_view.common import RenderConfig, actions, finish, header, section
from sts2_bridge.state_view.model import ViewContext, indexed_line, one_line


@dataclass(frozen=True)
class GameMenuConfig(RenderConfig):
    pass


def render(ctx: ViewContext, config: GameMenuConfig = GameMenuConfig(show_glossary=False)) -> str:
    game_over = ctx.agent.get("game_over") if isinstance(ctx.agent.get("game_over"), dict) else {}
    raw_game_over = ctx.data.get("game_over") if isinstance(ctx.data.get("game_over"), dict) else {}
    timeline = ctx.agent.get("timeline") if isinstance(ctx.agent.get("timeline"), dict) else {}
    raw_timeline = ctx.data.get("timeline") if isinstance(ctx.data.get("timeline"), dict) else {}
    lines = [header(ctx)]
    if game_over or raw_game_over:
        lines.append(_game_over_line(ctx, game_over or raw_game_over))
    if raw_timeline:
        status = [
            label
            for label, enabled in (
                ("inspect_open", raw_timeline.get("inspect_open")),
                ("can_confirm", raw_timeline.get("can_confirm_overlay")),
                ("can_choose", raw_timeline.get("can_choose_epoch")),
            )
            if enabled
        ]
        if status:
            lines.append(f"Timeline: {', '.join(status)}")
    slots = timeline.get("slots") if isinstance(timeline, dict) else None
    if not slots:
        slots = _raw_slots(raw_timeline)
    if isinstance(slots, list) and slots:
        lines += section("Timeline slots", [indexed_line(slot, index) for index, slot in enumerate(slots)])
    if config.show_actions:
        lines += section("Legal actions", actions(ctx))
    return finish(lines)


def _game_over_line(ctx: ViewContext, game_over: dict[str, object]) -> str:
    players = ctx.run.get("players")
    local = next((player for player in players if isinstance(player, dict) and player.get("is_local")), None) if isinstance(players, list) else None
    hp = f"{local.get('current_hp')}/{local.get('max_hp')}" if isinstance(local, dict) else "?"
    alive = local.get("is_alive") if isinstance(local, dict) else None
    victory = game_over.get("is_victory")
    result = "death" if alive is False or (isinstance(local, dict) and local.get("current_hp") == 0) else ("victory" if victory else "unknown")
    return f"Result: {result} | floor {game_over.get('floor') or ctx.floor} | character {game_over.get('character_id') or ctx.run.get('character_id')} | HP {hp} | alive {str(alive).lower()}"


def _raw_slots(timeline: dict[str, object]) -> list[dict[str, object]]:
    slots = timeline.get("slots")
    if not isinstance(slots, list):
        return []
    return [
        {
            "i": slot.get("index", index),
            "line": " | ".join(str(item) for item in (slot.get("title"), slot.get("state"), slot.get("epoch_id")) if item),
        }
        for index, slot in enumerate(slots)
        if isinstance(slot, dict)
    ]
