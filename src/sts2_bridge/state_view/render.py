from __future__ import annotations

from typing import Callable

from sts2_bridge.models import BridgeError
from sts2_bridge.state_view import (
    card_selection,
    character_select,
    chest,
    combat,
    event,
    game_menu,
    main_menu,
    rest,
    reward,
    shop,
    timeline,
    capstone,
)
from sts2_bridge.state_view import map as map_view
from sts2_bridge.state_view.model import ViewContext, response_data
from sts2_bridge.state_view.router import route_state_response


Renderer = Callable[[ViewContext], str]

ROUTE_RENDERERS: dict[str, Renderer] = {
    "state/gameplay/combat/actionable": combat.render,
    "state/gameplay/combat/end_turn_only": combat.render,
    "state/gameplay/combat/no_actions_transition": combat.render,
    "state/gameplay/combat/potion_and_combat": combat.render,
    "state/gameplay/combat/potion_only": combat.render,
    "state/map/route_selection": map_view.render,
    "state/event/choice": event.render,
    "state/rest/options": rest.render,
    "state/rest/proceed": rest.render,
    "state/rest/potion_only": rest.render,
    "state/rest/recovery_or_wait": rest.render,
    "state/reward/card_choice": reward.render,
    "state/reward/collect_or_resolve": reward.render,
    "state/reward/rows": reward.render,
    "state/card_selection/combat_discard": card_selection.render,
    "state/card_selection/combat_retain": card_selection.render,
    "state/card_selection/deck_remove": card_selection.render,
    "state/card_selection/deck_upgrade": card_selection.render,
    "state/card_selection/generic_card_choice": card_selection.render,
    "state/shop/closed": shop.render,
    "state/shop/inventory": shop.render,
    "state/chest/open": chest.render,
    "state/chest/proceed": chest.render,
    "state/chest/relic_choice": chest.render,
    "state/game_menu/game_over": game_menu.render,
    "state/character_select/select": character_select.render,
    "state/game_menu/timeline": timeline.render,
    "state/game_menu/main": main_menu.render,
    "state/game_menu/capstone_selection": capstone.render,
    "state/game_menu/unknown": game_menu.render,
}


def render_state_response(raw: dict[str, object]) -> str:
    if not isinstance(raw, dict):
        raise BridgeError("invalid_state_response", "/state returned a non-object JSON payload.", retryable=False)
    route = route_state_response(raw)
    renderer = ROUTE_RENDERERS.get(route.category)
    if renderer is None:
        raise BridgeError(
            "unhandled_state_route",
            "The /state response matched a route with no renderer.",
            details={"route": route.category},
            retryable=False,
        )
    return renderer(ViewContext(route=route, raw=raw, data=response_data(raw)))
