from __future__ import annotations

from dataclasses import dataclass

from sts2_bridge.state_view.common import RenderConfig, actions, finish, header, section
from sts2_bridge.state_view.model import ViewContext, indexed_line


@dataclass(frozen=True)
class ChestConfig(RenderConfig):
    pass


def render(ctx: ViewContext, config: ChestConfig = ChestConfig(show_glossary=False)) -> str:
    chest = ctx.agent.get("chest") if isinstance(ctx.agent.get("chest"), dict) else {}
    lines = [header(ctx)]
    relics = chest.get("relics") or chest.get("options")
    if isinstance(relics, list) and relics:
        lines += section("Chest choices", [indexed_line(item, index) for index, item in enumerate(relics)])
    if config.show_actions:
        lines += section("Legal actions", actions(ctx))
    return finish(lines)
