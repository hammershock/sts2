from __future__ import annotations

from dataclasses import dataclass

from sts2_bridge.state_view.common import RenderConfig, actions, finish, header, section
from sts2_bridge.state_view.model import ViewContext, indexed_line, one_line


@dataclass(frozen=True)
class EventConfig(RenderConfig):
    pass


def render(ctx: ViewContext, config: EventConfig = EventConfig(show_glossary=False)) -> str:
    event = ctx.agent.get("event") if isinstance(ctx.agent.get("event"), dict) else {}
    raw_event = ctx.data.get("event") if isinstance(ctx.data.get("event"), dict) else {}
    lines = [header(ctx)]
    title = event.get("title") or raw_event.get("title") or event.get("event_id") or raw_event.get("event_id")
    if title:
        suffix = raw_event.get("event_id")
        lines.append(f"Event: {one_line(title)}{f' ({suffix})' if suffix and suffix not in str(title) else ''}")
    description = event.get("description") or raw_event.get("description")
    if description:
        lines.append(f"Text: {one_line(description)}")
    options = event.get("options") or _raw_options(raw_event)
    if isinstance(options, list) and options:
        lines += section("Options", [indexed_line(option, index) for index, option in enumerate(options)])
    if config.show_actions:
        lines += section("Legal actions", actions(ctx))
    return finish(lines)


def _raw_options(event: dict[str, object]) -> list[dict[str, object]]:
    options = event.get("options")
    if not isinstance(options, list):
        return []
    return [
        {
            "i": option.get("index", index),
            "line": " | ".join(str(item) for item in (option.get("title") or option.get("label"), option.get("description")) if item),
        }
        for index, option in enumerate(options)
        if isinstance(option, dict)
    ]
