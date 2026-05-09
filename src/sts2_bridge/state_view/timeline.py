from __future__ import annotations

from dataclasses import dataclass

from sts2_bridge.state_view.common import RenderConfig, actions, finish, header, section
from sts2_bridge.state_view.model import ViewContext, indexed_line


@dataclass(frozen=True)
class TimelineConfig(RenderConfig):
    show_glossary: bool = False


def render(ctx: ViewContext, config: TimelineConfig = TimelineConfig()) -> str:
    agent = ctx.agent.get("timeline") if isinstance(ctx.agent.get("timeline"), dict) else {}
    raw = ctx.data.get("timeline") if isinstance(ctx.data.get("timeline"), dict) else {}
    lines = [header(ctx)]
    status = _status(raw, agent)
    if status:
        lines.append(f"Timeline: {', '.join(status)}")
    slots = _slots(agent, raw)
    if slots:
        lines += section("Timeline slots", [indexed_line(slot, index) for index, slot in enumerate(slots)])
    if config.show_actions:
        lines += section("Legal actions", actions(ctx))
    return finish(lines)


def _status(raw: dict[str, object], agent: dict[str, object]) -> list[str]:
    return [
        label
        for label, enabled in (
            ("inspect_open", raw.get("inspect_open")),
            ("can_confirm", raw.get("can_confirm_overlay", agent.get("confirm"))),
            ("can_choose", raw.get("can_choose_epoch")),
        )
        if enabled
    ]


def _slots(agent: dict[str, object], raw: dict[str, object]) -> list[object]:
    slots = agent.get("slots")
    if isinstance(slots, list) and slots:
        return slots
    raw_slots = raw.get("slots")
    if not isinstance(raw_slots, list):
        return []
    return [
        {
            "i": slot.get("index", index),
            "line": " | ".join(str(item) for item in (slot.get("title"), slot.get("state"), slot.get("epoch_id")) if item),
        }
        for index, slot in enumerate(raw_slots)
        if isinstance(slot, dict)
    ]
