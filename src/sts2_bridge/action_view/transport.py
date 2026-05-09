from __future__ import annotations

from sts2_bridge.action_view.common import finish, inline_mapping, to_yaml
from sts2_bridge.action_view.model import ActionContext


def render(ctx: ActionContext) -> str:
    lines = [
        f"Action: {ctx.action}",
        "Result: transport_error",
        f"Route: {ctx.route.category}",
    ]
    if ctx.request_args:
        lines.append(f"Args: {inline_mapping(ctx.request_args)}")
    if ctx.transport_error:
        lines.extend(["", "Transport error:", to_yaml(ctx.transport_error).rstrip()])
    return finish(lines)
