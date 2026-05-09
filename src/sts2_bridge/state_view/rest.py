from __future__ import annotations

from dataclasses import dataclass

from sts2_bridge.state_view.common import RenderConfig, actions, finish, header, run_lines, section
from sts2_bridge.state_view.model import ViewContext, indexed_line


@dataclass(frozen=True)
class RestConfig(RenderConfig):
    pass


def render(ctx: ViewContext, config: RestConfig = RestConfig(show_glossary=False)) -> str:
    rest = ctx.agent.get("rest") if isinstance(ctx.agent.get("rest"), dict) else {}
    raw_rest = ctx.data.get("rest") if isinstance(ctx.data.get("rest"), dict) else {}
    lines = [header(ctx)]
    options = rest.get("options") or _raw_options(raw_rest)
    if isinstance(options, list) and options:
        lines += section("Rest options", [indexed_line(option, index) for index, option in enumerate(options)])
    run = run_lines(ctx) if config.show_run else []
    if run:
        lines += section("Run", run)
    if config.show_actions:
        lines += section("Legal actions", actions(ctx))
    return finish(lines)


def _raw_options(rest: dict[str, object]) -> list[dict[str, object]]:
    options = rest.get("options")
    if not isinstance(options, list):
        return []
    result: list[dict[str, object]] = []
    for index, option in enumerate(options):
        if isinstance(option, dict):
            result.append({"i": option.get("index", index), "line": option.get("title") or option.get("label") or option.get("name") or option.get("text")})
        else:
            result.append({"i": index, "line": option})
    return result
