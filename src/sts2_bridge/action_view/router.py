from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import json
from pathlib import Path
from typing import Any

from sts2_bridge.action_view.model import ActionRoute, response_action
from sts2_bridge.models import BridgeError

try:
    from jsonschema import Draft202012Validator
except ImportError:  # pragma: no cover - dependency is declared by pyproject.
    Draft202012Validator = None  # type: ignore[assignment]


ACTION_DOMAINS = {
    "play_card": "gameplay/combat",
    "end_turn": "gameplay/combat",
    "use_potion": "gameplay/combat",
    "discard_potion": "gameplay/combat",
    "select_deck_card": "card_selection",
    "confirm_selection": "card_selection",
    "choose_map_node": "map",
    "choose_event_option": "event",
    "choose_rest_option": "rest",
    "claim_reward": "reward",
    "choose_reward_card": "reward",
    "skip_reward_cards": "reward",
    "collect_rewards_and_proceed": "reward",
    "resolve_rewards": "reward",
    "open_shop_inventory": "shop",
    "close_shop_inventory": "shop",
    "buy_card": "shop",
    "buy_relic": "shop",
    "buy_potion": "shop",
    "remove_card_at_shop": "shop",
    "open_chest": "chest",
    "choose_treasure_relic": "chest",
    "open_timeline": "game_menu",
    "choose_timeline_epoch": "game_menu",
    "confirm_timeline_overlay": "game_menu",
    "close_main_menu_submenu": "game_menu",
    "choose_capstone_option": "game_menu",
    "continue_run": "game_menu",
    "return_to_main_menu": "game_menu",
    "open_character_select": "character_select",
    "select_character": "character_select",
    "increase_ascension": "character_select",
    "decrease_ascension": "character_select",
    "embark": "character_select",
    "proceed": "navigation",
}


@dataclass(frozen=True)
class RouteSchema:
    category: str
    validator: Any
    specificity: int


def route_action_response(
    raw: dict[str, Any] | None,
    *,
    request_action: str | None = None,
    http_status: int | None = None,
) -> ActionRoute:
    action = response_action(raw, request_action)
    if not action:
        raise BridgeError("unmatched_action_route", "Cannot route /action response without an action name.")
    domain = ACTION_DOMAINS.get(action)
    if domain is None:
        raise BridgeError(
            "unmatched_action_route",
            "No /action route is registered for this action.",
            details={"action": action},
            retryable=False,
        )

    if raw is None:
        return ActionRoute(f"action/{domain}/{action}/transport_error", action, "transport_error", http_status=http_status)
    if not isinstance(raw, dict):
        raise BridgeError(
            "invalid_action_response",
            "/action returned a non-object JSON payload.",
            details={"action": action, "payload_type": type(raw).__name__},
            retryable=False,
        )

    matches = _matching_schema_categories(raw)
    if raw.get("ok") is False:
        error = raw.get("error") if isinstance(raw.get("error"), dict) else {}
        code = error.get("code")
        if not isinstance(code, str) or not code:
            raise BridgeError(
                "unmatched_action_route",
                "Cannot route failed /action response without error.code.",
                details={"action": action},
                retryable=False,
            )
        return ActionRoute(
            f"action/{domain}/{action}/error/{code}",
            action,
            f"error/{code}",
            matched_categories=matches,
            http_status=http_status,
        )

    if raw.get("ok") is not True:
        raise BridgeError(
            "unmatched_action_route",
            "/action response must contain ok=true or ok=false.",
            details={"action": action},
            retryable=False,
        )

    data = raw.get("data") if isinstance(raw.get("data"), dict) else {}
    status = data.get("status")
    stable = data.get("stable")
    if status == "pending" or stable is False:
        outcome = "pending"
    elif status in {None, "completed"}:
        outcome = "completed"
    else:
        raise BridgeError(
            "unmatched_action_route",
            "Unknown successful /action status.",
            details={"action": action, "status": status, "stable": stable},
            retryable=False,
        )
    return ActionRoute(
        f"action/{domain}/{action}/{outcome}",
        action,
        outcome,
        matched_categories=matches,
        http_status=http_status,
    )


def _matching_schema_categories(raw: dict[str, Any]) -> tuple[str, ...]:
    routes = _load_route_schemas()
    matches = [route for route in routes if route.validator.is_valid(raw)]
    matches.sort(key=lambda route: (-route.specificity, route.category))
    return tuple(route.category for route in matches)


@lru_cache(maxsize=1)
def _load_route_schemas() -> tuple[RouteSchema, ...]:
    if Draft202012Validator is None:
        return ()
    manifest_path = _archive_dir() / "manifest.json"
    if not manifest_path.exists():
        return ()
    manifest = _load_json(manifest_path)
    routes: list[RouteSchema] = []
    for item in manifest.get("categories", []):
        category = item.get("category")
        schema_ref = item.get("schema")
        if not isinstance(category, str) or not isinstance(schema_ref, str) or not category.startswith("action/"):
            continue
        schema_path = _repo_root() / schema_ref
        if not schema_path.exists():
            continue
        schema = _load_json(schema_path)
        routes.append(RouteSchema(category, Draft202012Validator(schema), _schema_specificity(schema)))
    return tuple(routes)


def _archive_dir() -> Path:
    return _repo_root() / "samples" / "http" / "20260508"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _schema_specificity(node: Any) -> int:
    if isinstance(node, dict):
        score = 0
        if "const" in node:
            score += 20
        if "contains" in node:
            score += 8
        if "pattern" in node:
            score += 5
        score += len(node.get("required") or [])
        score += len(node.get("properties") or {})
        return score + sum(_schema_specificity(value) for value in node.values())
    if isinstance(node, list):
        return sum(_schema_specificity(item) for item in node)
    return 0
