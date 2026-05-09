from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import json
from pathlib import Path
from typing import Any

from sts2_bridge.models import BridgeError
from sts2_bridge.state_view.model import Route, response_data

try:
    from jsonschema import Draft202012Validator
except ImportError:  # pragma: no cover - dependency is declared by pyproject.
    Draft202012Validator = None  # type: ignore[assignment]


CATEGORY_PRIORITY = {
    "state/reward/card_choice": 10,
    "state/card_selection/deck_remove": 20,
    "state/card_selection/deck_upgrade": 21,
    "state/card_selection/combat_retain": 22,
    "state/card_selection/combat_discard": 23,
    "state/card_selection/generic_card_choice": 24,
    "state/shop/inventory": 30,
    "state/shop/closed": 31,
    "state/rest/options": 40,
    "state/rest/proceed": 41,
    "state/rest/potion_only": 42,
    "state/rest/recovery_or_wait": 43,
    "state/gameplay/combat/potion_and_combat": 50,
    "state/gameplay/combat/potion_only": 51,
    "state/gameplay/combat/end_turn_only": 52,
    "state/gameplay/combat/no_actions_transition": 53,
    "state/gameplay/combat/actionable": 54,
    "state/reward/rows": 60,
    "state/reward/collect_or_resolve": 61,
    "state/map/route_selection": 70,
    "state/event/choice": 80,
    "state/chest/open": 90,
    "state/chest/relic_choice": 91,
    "state/chest/proceed": 92,
    "state/game_menu/game_over": 100,
    "state/character_select/select": 101,
    "state/game_menu/timeline": 102,
    "state/game_menu/main": 103,
    "state/game_menu/capstone_selection": 104,
    "state/game_menu/unknown": 105,
}


@dataclass(frozen=True)
class RouteSchema:
    category: str
    validator: Any
    specificity: int


def route_state_response(raw: dict[str, Any]) -> Route:
    routes = _load_route_schemas()
    matches = [route for route in routes if route.category.startswith("state/") and route.validator.is_valid(raw)]
    preferred = _preferred_category(raw)
    if preferred:
        matches = sorted(matches, key=_sort_key)
        for route in matches:
            if route.category == preferred:
                return Route(route.category, tuple(item.category for item in matches))
        if preferred in CATEGORY_PRIORITY:
            matched = tuple(item.category for item in matches)
            return Route(preferred, matched + (preferred,))
    if matches:
        matches = sorted(matches, key=_sort_key)
        route = matches[0]
        return Route(route.category, tuple(item.category for item in matches))

    # Some development fixtures are already unwrapped. Route those only when the
    # discriminator table can still classify the payload exactly.
    fallback = _classify_state_payload(response_data(raw))
    if fallback in CATEGORY_PRIORITY:
        return Route(fallback, (fallback,))
    raise BridgeError(
        "unmatched_state_route",
        "The /state response does not match any known state route.",
        details={"screen": response_data(raw).get("screen"), "available_actions": response_data(raw).get("available_actions")},
        retryable=False,
    )


@lru_cache(maxsize=1)
def _load_route_schemas() -> tuple[RouteSchema, ...]:
    if Draft202012Validator is None:
        return ()
    archive_dir = _archive_dir()
    manifest_path = archive_dir / "manifest.json"
    if not manifest_path.exists():
        return ()
    manifest = _load_json(manifest_path)
    routes: list[RouteSchema] = []
    for item in manifest.get("categories", []):
        category = item.get("category")
        schema_ref = item.get("schema")
        if not isinstance(category, str) or not isinstance(schema_ref, str) or not category.startswith("state/"):
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
        if "maxItems" in node:
            score += 4
        score += len(node.get("required") or [])
        score += len(node.get("properties") or {})
        return score + sum(_schema_specificity(value) for value in node.values())
    if isinstance(node, list):
        return sum(_schema_specificity(item) for item in node)
    return 0


def _sort_key(route: RouteSchema) -> tuple[int, int, str]:
    return (CATEGORY_PRIORITY.get(route.category, 1_000), -route.specificity, route.category)


def _preferred_category(raw: dict[str, Any]) -> str | None:
    return _classify_state_payload(response_data(raw))


def _classify_state_payload(data: dict[str, Any]) -> str | None:
    if not isinstance(data, dict):
        return None
    screen = data.get("screen")
    actions = set(data.get("available_actions") or [])
    selection = data.get("selection") or None
    reward = data.get("reward") or None
    shop = data.get("shop") or None
    rest = data.get("rest") or None
    chest = data.get("chest") or None

    if screen == "MAP" or data.get("map") is not None:
        return "state/map/route_selection"
    if screen == "SHOP" or shop is not None:
        return "state/shop/inventory" if (shop or {}).get("is_open") else "state/shop/closed"
    if screen == "EVENT" or data.get("event") is not None:
        return "state/event/choice"
    if screen == "REST" or rest is not None:
        if "choose_rest_option" in actions:
            return "state/rest/options"
        if "proceed" in actions:
            return "state/rest/proceed"
        if actions == {"discard_potion"}:
            return "state/rest/potion_only"
        return "state/rest/recovery_or_wait"
    if screen == "CARD_SELECTION" or selection is not None:
        kind = (selection or {}).get("kind")
        prompt = (selection or {}).get("prompt") or ""
        if reward is not None or {"choose_reward_card", "skip_reward_cards"} & actions:
            return "state/reward/card_choice"
        if kind == "deck_upgrade_select" or "升级" in prompt:
            return "state/card_selection/deck_upgrade"
        if kind == "deck_card_select" and "移除" in prompt:
            return "state/card_selection/deck_remove"
        if kind == "combat_hand_select" and "丢弃" in prompt:
            return "state/card_selection/combat_discard"
        if kind == "combat_hand_select" and "保留" in prompt:
            return "state/card_selection/combat_retain"
        return "state/card_selection/generic_card_choice"
    if screen == "REWARD" or reward is not None:
        if "choose_reward_card" in actions or (isinstance(reward, dict) and reward.get("pending_card_choice")):
            return "state/reward/card_choice"
        if "claim_reward" in actions:
            return "state/reward/rows"
        return "state/reward/collect_or_resolve"
    if screen == "CHEST" or chest is not None:
        if "open_chest" in actions:
            return "state/chest/open"
        if "choose_treasure_relic" in actions:
            return "state/chest/relic_choice"
        return "state/chest/proceed"
    if screen == "GAME_OVER" or data.get("game_over") is not None:
        return "state/game_menu/game_over"
    if screen == "CHARACTER_SELECT" or data.get("character_select") is not None:
        return "state/character_select/select"
    if screen == "CAPSTONE_SELECTION" or "choose_capstone_option" in actions:
        return "state/game_menu/capstone_selection"
    if screen == "MAIN_MENU":
        if data.get("timeline") is not None or {"choose_timeline_epoch", "confirm_timeline_overlay"} & actions:
            return "state/game_menu/timeline"
        return "state/game_menu/main"
    if screen == "COMBAT" and data.get("combat") is not None:
        if not actions:
            return "state/gameplay/combat/no_actions_transition"
        if {"use_potion", "discard_potion"} & actions and {"play_card", "end_turn"} & actions:
            return "state/gameplay/combat/potion_and_combat"
        if actions <= {"use_potion", "discard_potion"}:
            return "state/gameplay/combat/potion_only"
        if actions == {"end_turn"}:
            return "state/gameplay/combat/end_turn_only"
        return "state/gameplay/combat/actionable"
    return "state/game_menu/unknown"
