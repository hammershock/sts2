from __future__ import annotations

from sts2_bridge.action_view.common import base_lines, finish, state_lines
from sts2_bridge.action_view.model import ActionContext


def render(ctx: ActionContext) -> str:
    return finish(base_lines(ctx) + state_lines(ctx))
