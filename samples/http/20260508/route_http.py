#!/usr/bin/env python3
"""Route STS2 HTTP records with the 20260508 routing schemas.

This script is intentionally small and self-contained so future agents can use
it as a reference for state routing. It accepts either the original HTTP JSONL
trace records or raw response JSON files.

Examples:
  python samples/http/20260508/route_http.py logs/http/20260508.jsonl --summary
  python samples/http/20260508/route_http.py samples/http/20260508/state/map/route_selection/0078_20260508190621_map.json
  python samples/http/20260508/route_http.py logs/http/20260508.jsonl --explain --limit 5
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

try:
    from jsonschema import Draft202012Validator
except ImportError as exc:  # pragma: no cover - dependency hint for ad-hoc use.
    raise SystemExit("Missing dependency: install jsonschema to use this router.") from exc


ARCHIVE_DIR = Path(__file__).resolve().parent
MANIFEST_PATH = ARCHIVE_DIR / "manifest.json"

# Some routing schemas intentionally overlap. For example, a combat state with
# both play_card and use_potion matches both "actionable" and
# "potion_and_combat". This priority table preserves the game-logic taxonomy
# used when the archive was generated.
CATEGORY_PRIORITY = {
    "health/service_ready": 0,
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
    "state/game_menu/unknown": 101,
}


ACTION_TRANSPORT_ROUTES = {
    "choose_event_option": "action/event/choose_event_option/transport_error",
}


@dataclass(frozen=True)
class RouteSchema:
    category: str
    label: str
    schema_path: Path
    validator: Draft202012Validator
    specificity: int


def load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def load_manifest(archive_dir: Path) -> dict[str, Any]:
    return load_json(archive_dir / "manifest.json")


def schema_specificity(node: Any) -> int:
    """Score schemas so stricter schemas win when priority ties."""
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
        for value in node.values():
            score += schema_specificity(value)
        return score
    if isinstance(node, list):
        return sum(schema_specificity(item) for item in node)
    return 0


def load_route_schemas(archive_dir: Path) -> list[RouteSchema]:
    manifest = load_manifest(archive_dir)
    routes: list[RouteSchema] = []
    for item in manifest["categories"]:
        schema_ref = item.get("schema")
        if not schema_ref:
            continue
        schema_path = archive_dir.parent.parent.parent / schema_ref
        if not schema_path.exists():
            schema_path = Path(schema_ref)
        schema = load_json(schema_path)
        routes.append(
            RouteSchema(
                category=item["category"],
                label=item.get("label") or item["category"],
                schema_path=schema_path,
                validator=Draft202012Validator(schema),
                specificity=schema_specificity(schema),
            )
        )
    return routes


def parse_request_body(record: dict[str, Any]) -> Any:
    body = (record.get("request") or {}).get("body")
    if isinstance(body, str):
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            return body
    return body


def parse_response_json(record: dict[str, Any]) -> Any | None:
    response = record.get("response") or {}
    text = response.get("text")
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def request_kind(record: dict[str, Any]) -> tuple[str | None, str | None, str | None]:
    request = record.get("request") or {}
    method = request.get("method")
    path = urlparse(request.get("url") or "").path
    body = parse_request_body(record)
    action = body.get("action") if isinstance(body, dict) else None
    return method, path, action


def candidate_schemas(
    routes: list[RouteSchema],
    *,
    method: str | None = None,
    path: str | None = None,
) -> list[RouteSchema]:
    if method == "GET" and path == "/health":
        prefix = "health/"
    elif method == "GET" and path == "/state":
        prefix = "state/"
    elif method == "POST" and path == "/action":
        prefix = "action/"
    else:
        return routes
    return [route for route in routes if route.category.startswith(prefix)]


def sort_key(route: RouteSchema) -> tuple[int, int, str]:
    return (
        CATEGORY_PRIORITY.get(route.category, 1_000),
        -route.specificity,
        route.category,
    )


def classify_state_payload(data: dict[str, Any]) -> str | None:
    """Mirror the archive taxonomy for schemas that deliberately overlap."""
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


def preferred_category(response_json: Any) -> str | None:
    if not isinstance(response_json, dict):
        return None
    data = response_json.get("data")
    if isinstance(data, dict) and "screen" in data:
        return classify_state_payload(data)
    return None


def route_response(
    response_json: Any,
    routes: list[RouteSchema],
    *,
    method: str | None = None,
    path: str | None = None,
) -> tuple[RouteSchema | None, list[RouteSchema]]:
    candidates = candidate_schemas(routes, method=method, path=path)
    matches = [route for route in candidates if route.validator.is_valid(response_json)]
    if not matches:
        return None, []
    preferred = preferred_category(response_json)
    if preferred:
        for route in matches:
            if route.category == preferred:
                matches.sort(key=sort_key)
                return route, matches
    matches.sort(key=sort_key)
    return matches[0], matches


def fallback_transport_category(action: str | None) -> str:
    if action in ACTION_TRANSPORT_ROUTES:
        return ACTION_TRANSPORT_ROUTES[action]
    safe_action = re.sub(r"[^a-zA-Z0-9]+", "_", action or "unknown").strip("_").lower()
    return f"action/other/{safe_action or 'unknown'}/transport_error"


def route_record(record: dict[str, Any], routes: list[RouteSchema]) -> dict[str, Any]:
    method, path, action = request_kind(record)
    response = record.get("response") or {}
    response_json = parse_response_json(record)

    result: dict[str, Any] = {
        "method": method,
        "path": path,
        "status_code": response.get("status_code"),
        "request_action": action,
    }

    if response_json is None:
        result["category"] = fallback_transport_category(action)
        result["schema"] = None
        result["matched"] = False
        return result

    route, matches = route_response(response_json, routes, method=method, path=path)
    result["matched"] = route is not None
    result["category"] = route.category if route else "unmatched"
    result["schema"] = str(route.schema_path) if route else None
    result["matched_categories"] = [item.category for item in matches]

    if isinstance(response_json, dict):
        data = response_json.get("data")
        if isinstance(data, dict):
            if "screen" in data:
                result["screen"] = data.get("screen")
            if "available_actions" in data:
                result["available_actions"] = data.get("available_actions")
            embedded = data.get("state")
            if isinstance(embedded, dict):
                result["embedded_state_screen"] = embedded.get("screen")
        error = response_json.get("error")
        if isinstance(error, dict):
            result["error_code"] = error.get("code")
            result["error_message"] = error.get("message")
    return result


def read_inputs(path: Path) -> list[tuple[int | None, dict[str, Any]]]:
    text = path.read_text(encoding="utf-8")
    stripped = text.lstrip()
    if stripped.startswith("{"):
        try:
            return [(None, json.loads(text))]
        except json.JSONDecodeError:
            pass
    records: list[tuple[int | None, dict[str, Any]]] = []
    for line_no, line in enumerate(text.splitlines(), 1):
        if line.strip():
            records.append((line_no, json.loads(line)))
    return records


def route_raw_json(raw: dict[str, Any], routes: list[RouteSchema]) -> dict[str, Any]:
    route, matches = route_response(raw, routes)
    result = {
        "category": route.category if route else "unmatched",
        "schema": str(route.schema_path) if route else None,
        "matched": route is not None,
        "matched_categories": [item.category for item in matches],
    }
    data = raw.get("data") if isinstance(raw, dict) else None
    if isinstance(data, dict):
        result["screen"] = data.get("screen")
        result["available_actions"] = data.get("available_actions")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="HTTP JSONL trace or raw response JSON")
    parser.add_argument(
        "--archive-dir",
        type=Path,
        default=ARCHIVE_DIR,
        help="Archive directory containing manifest.json and schemas/.",
    )
    parser.add_argument("--limit", type=int, default=None, help="Only route the first N records")
    parser.add_argument("--summary", action="store_true", help="Print category counts instead of per-record JSONL")
    parser.add_argument("--explain", action="store_true", help="Include all matching categories in output")
    args = parser.parse_args(argv)

    routes = load_route_schemas(args.archive_dir.resolve())
    inputs = read_inputs(args.input)
    counts: Counter[str] = Counter()

    for index, (line_no, item) in enumerate(inputs, 1):
        if args.limit is not None and index > args.limit:
            break

        is_http_record = isinstance(item, dict) and "request" in item
        if is_http_record:
            output = route_record(item, routes)
        else:
            output = route_raw_json(item, routes)

        if line_no is not None:
            output["line"] = line_no
        counts[output["category"]] += 1

        if args.summary:
            continue
        if not args.explain:
            output.pop("matched_categories", None)
        print(json.dumps(output, ensure_ascii=False, sort_keys=True))

    if args.summary:
        for category, count in counts.most_common():
            print(f"{count:5d} {category}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
