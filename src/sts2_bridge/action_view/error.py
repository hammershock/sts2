from __future__ import annotations

from sts2_bridge.action_view.common import finish, inline_mapping, to_yaml
from sts2_bridge.action_view.model import ActionContext


def render(ctx: ActionContext) -> str:
    error = ctx.error
    lines = [
        f"Action: {ctx.action}",
        f"Result: error {error.get('code') or '?'}",
        f"Route: {ctx.route.category}",
    ]
    if ctx.request_args:
        lines.append(f"Args: {inline_mapping(ctx.request_args)}")
    if error.get("message"):
        lines.append(f"Message: {error['message']}")
    if error.get("details"):
        lines.extend(["", "Details:", to_yaml(error["details"]).rstrip()])
    if error.get("retryable") is not None:
        lines.append(f"Retryable: {str(error.get('retryable')).lower()}")
    return finish(lines)
