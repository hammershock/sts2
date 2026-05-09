from __future__ import annotations

from sts2_bridge.action_view.common import base_lines, finish, state_lines
from sts2_bridge.action_view.model import ActionContext


def render(ctx: ActionContext) -> str:
    lines = base_lines(ctx)
    lines.append("Next: continue from embedded state below.")
    return finish(lines + state_lines(ctx))
