from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ActionRoute:
    category: str
    action: str
    outcome: str
    matched_categories: tuple[str, ...] = ()
    http_status: int | None = None


@dataclass(frozen=True)
class ActionContext:
    route: ActionRoute
    raw: dict[str, Any] | None
    request_action: str | None = None
    request_args: dict[str, Any] | None = None
    transport_error: dict[str, Any] | None = None

    @property
    def data(self) -> dict[str, Any]:
        if not isinstance(self.raw, dict):
            return {}
        data = self.raw.get("data")
        return data if isinstance(data, dict) else {}

    @property
    def error(self) -> dict[str, Any]:
        if not isinstance(self.raw, dict):
            return {}
        error = self.raw.get("error")
        return error if isinstance(error, dict) else {}

    @property
    def action(self) -> str:
        return self.route.action

    @property
    def status(self) -> str:
        if self.route.outcome.startswith("error"):
            return "error"
        return str(self.data.get("status") or self.route.outcome)

    @property
    def stable(self) -> Any:
        return self.data.get("stable")

    @property
    def message(self) -> Any:
        return self.data.get("message") or self.error.get("message")


def response_action(raw: dict[str, Any] | None, request_action: str | None) -> str | None:
    if isinstance(raw, dict):
        data = raw.get("data")
        if isinstance(data, dict) and isinstance(data.get("action"), str):
            return data["action"]
        error = raw.get("error")
        details = error.get("details") if isinstance(error, dict) else None
        if isinstance(details, dict) and isinstance(details.get("action"), str):
            return details["action"]
    return request_action
