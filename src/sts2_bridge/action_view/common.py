from __future__ import annotations

from typing import Any

import yaml

from sts2_bridge.action_view.model import ActionContext
from sts2_bridge.state_view import render_state_response


def base_lines(ctx: ActionContext) -> list[str]:
    lines = [
        f"Action: {ctx.action}",
        f"Result: {ctx.status} stable={str(ctx.stable).lower()}",
        f"Route: {ctx.route.category}",
    ]
    if ctx.request_args:
        lines.append(f"Args: {inline_mapping(ctx.request_args)}")
    if ctx.message:
        lines.append(f"Message: {ctx.message}")
    return lines


def state_lines(ctx: ActionContext) -> list[str]:
    state = ctx.data.get("state")
    if not isinstance(state, dict):
        return []
    request_id = ctx.raw.get("request_id") if isinstance(ctx.raw, dict) else None
    view = render_state_response({"ok": True, "request_id": request_id or "embedded_action_state", "data": state})
    return ["", "State:", view.rstrip()]


def finish(lines: list[str]) -> str:
    return "\n".join(lines).rstrip() + "\n"


def to_yaml(data: Any) -> str:
    return yaml.safe_dump(data, allow_unicode=True, sort_keys=False).rstrip() + "\n"


def inline_mapping(data: dict[str, Any]) -> str:
    return ", ".join(f"{key}={value}" for key, value in data.items())
