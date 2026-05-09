from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sts2_bridge.state_view.common import RenderConfig, actions, finish, header, run_lines, section
from sts2_bridge.state_view.model import ViewContext, indexed_line


@dataclass(frozen=True)
class MapConfig(RenderConfig):
    show_reachable: bool = True


def render(ctx: ViewContext, config: MapConfig = MapConfig(show_glossary=False)) -> str:
    agent_map = ctx.agent.get("map") if isinstance(ctx.agent.get("map"), dict) else {}
    raw_map = ctx.data.get("map") if isinstance(ctx.data.get("map"), dict) else {}
    lines = [header(ctx)]
    if agent_map.get("current"):
        lines.append(f"Current: {_coord(agent_map.get('current'))}")
    options = agent_map.get("options")
    if isinstance(options, list) and options:
        lines += section("Map choices", [indexed_line(option, index) for index, option in enumerate(options)])
    if config.show_reachable:
        reachable = _reachable_rows(raw_map)
        if reachable:
            lines += section("Reachable map", reachable)
    run = run_lines(ctx) if config.show_run else []
    if run:
        lines += section("Run", run)
    if config.show_actions:
        lines += section("Legal actions", actions(ctx))
    return finish(lines)


def _reachable_rows(raw_map: dict[str, Any]) -> list[str]:
    nodes = [node for node in raw_map.get("nodes") or [] if isinstance(node, dict)]
    if not nodes:
        return []
    rows: dict[int, list[str]] = {}
    for node in nodes:
        if node.get("state") not in {"Travelable", "Untravelable"} and not node.get("is_available"):
            continue
        row = node.get("row")
        col = node.get("col")
        if isinstance(row, int) and isinstance(col, int):
            rows.setdefault(row, []).append(f"c{col}{_node_symbol(node)}")
    return [f"r{row}: {', '.join(values)}" for row, values in sorted(rows.items())]


def _node_symbol(node: dict[str, Any]) -> str:
    return {
        "Ancient": "A",
        "Boss": "B",
        "Elite": "E",
        "Monster": "M",
        "RestSite": "R",
        "Shop": "S",
        "Treasure": "T",
        "Unknown": "?",
    }.get(str(node.get("node_type") or "Unknown"), "?")


def _coord(value: object) -> object:
    if isinstance(value, str) and "," in value:
        row, col = value.split(",", 1)
        return f"r{row}c{col}"
    return value
