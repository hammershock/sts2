from __future__ import annotations

from typing import Any

import sts2_bridge.action_view.completed as completed
import sts2_bridge.action_view.error as error
import sts2_bridge.action_view.pending as pending
import sts2_bridge.action_view.transport as transport
from sts2_bridge.action_view.model import ActionContext
from sts2_bridge.action_view.router import route_action_response
from sts2_bridge.models import BridgeError


def render_action_response(
    raw: dict[str, Any] | None,
    *,
    request_action: str | None = None,
    request_args: dict[str, Any] | None = None,
    http_status: int | None = None,
    transport_error: dict[str, Any] | None = None,
) -> str:
    route = route_action_response(raw, request_action=request_action, http_status=http_status)
    ctx = ActionContext(
        route=route,
        raw=raw,
        request_action=request_action,
        request_args=request_args,
        transport_error=transport_error,
    )
    if route.outcome == "completed":
        return completed.render(ctx)
    if route.outcome == "pending":
        return pending.render(ctx)
    if route.outcome.startswith("error/"):
        return error.render(ctx)
    if route.outcome == "transport_error":
        return transport.render(ctx)
    raise BridgeError(
        "unhandled_action_route",
        "The /action response matched a route with no renderer.",
        details={"route": route.category},
        retryable=False,
    )
