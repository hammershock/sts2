from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any


@dataclass(frozen=True)
class Route:
    category: str
    matched_categories: tuple[str, ...] = ()


@dataclass(frozen=True)
class ViewContext:
    route: Route
    raw: dict[str, Any]
    data: dict[str, Any]

    @property
    def screen(self) -> str:
        return str(self.data.get("screen") or "UNKNOWN")

    @property
    def actions(self) -> list[str]:
        actions = self.data.get("available_actions")
        return [str(action) for action in actions] if isinstance(actions, list) else []

    @property
    def agent(self) -> dict[str, Any]:
        agent = self.data.get("agent_view")
        return agent if isinstance(agent, dict) else {}

    @property
    def run(self) -> dict[str, Any]:
        run = self.data.get("run")
        return run if isinstance(run, dict) else {}

    @property
    def floor(self) -> Any:
        return self.run.get("floor")

    @property
    def gold(self) -> Any:
        return self.run.get("gold")

    @property
    def turn(self) -> Any:
        return self.data.get("turn")


def response_data(raw: dict[str, Any]) -> dict[str, Any]:
    data = raw.get("data")
    return data if isinstance(data, dict) else raw


def one_line(value: Any) -> str:
    text = re.sub(r"\[/?[A-Za-z_#][A-Za-z0-9_#-]*\]", "", str(value))
    return " ".join(text.split())


def indexed_line(item: Any, fallback_index: int | None = None) -> str:
    if not isinstance(item, dict):
        return str(item)
    index = item.get("i", item.get("index", fallback_index))
    line = item.get("line") or item.get("title") or item.get("name") or item.get("card_id") or item.get("potion_id")
    prefix = f"[{index}] " if index is not None else ""
    return f"{prefix}{one_line(line or 'Option')}"
