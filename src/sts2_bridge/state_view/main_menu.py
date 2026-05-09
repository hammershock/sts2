from __future__ import annotations

from dataclasses import dataclass

from sts2_bridge.state_view.common import RenderConfig, actions, finish, header, section
from sts2_bridge.state_view.model import ViewContext


@dataclass(frozen=True)
class MainMenuConfig(RenderConfig):
    show_glossary: bool = False


def render(ctx: ViewContext, config: MainMenuConfig = MainMenuConfig()) -> str:
    session = ctx.data.get("session") if isinstance(ctx.data.get("session"), dict) else {}
    lines = [header(ctx)]
    if session:
        parts = [
            f"mode={session.get('mode')}",
            f"phase={session.get('phase')}",
            f"control={session.get('control_scope')}",
        ]
        lines.append("Session: " + " | ".join(part for part in parts if not part.endswith("=None")))
    if config.show_actions:
        lines += section("Legal actions", actions(ctx))
    return finish(lines)
