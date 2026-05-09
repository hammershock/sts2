from __future__ import annotations

from dataclasses import dataclass

from sts2_bridge.state_view.common import RenderConfig, actions, finish, glossary_lines, header, run_lines, section
from sts2_bridge.state_view.model import ViewContext


@dataclass(frozen=True)
class CapstoneConfig(RenderConfig):
    pass


def render(ctx: ViewContext, config: CapstoneConfig = CapstoneConfig()) -> str:
    lines = [header(ctx)]
    run = ctx.agent.get("run") if isinstance(ctx.agent.get("run"), dict) else {}
    character = run.get("character") or ctx.run.get("character_name") or ctx.run.get("character_id")
    if character:
        lines.append(f"Character: {character}")
    if config.show_run:
        run_info = run_lines(ctx)
        if run_info:
            lines += section("Run", run_info)
    if config.show_actions:
        lines += section("Legal actions", actions(ctx))
    glossary = glossary_lines(ctx) if config.show_glossary else []
    if glossary:
        lines += section("Glossary", glossary)
    return finish(lines)
