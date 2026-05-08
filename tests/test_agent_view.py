import json
from pathlib import Path

from sts2_bridge.agent_view import (
    build_action_result_view,
    build_actions_view,
    build_agent_view,
    build_brief_view,
    build_combat_view,
)
from sts2_bridge.models import GameState


def load_state() -> GameState:
    payload = json.loads(Path("tests/fixtures/state_combat.json").read_text())["data"]
    return GameState.model_validate(payload)


def test_agent_view_keeps_decision_fields() -> None:
    view = build_agent_view(load_state())

    assert view["screen"] == "COMBAT"
    assert view["available_actions"] == ["play_card", "end_turn"]
    assert view["combat"]["player"]["energy"] == 3
    assert view["combat"]["enemies"][0]["intent"] == "attack 6"
    assert view["combat"]["hand"][0]["text"] == "Deal 8 damage."
    assert view["run"]["gold"] == 99


def test_combat_view_lists_playable_targets() -> None:
    view = build_combat_view(load_state())

    assert view["playable_cards"] == [
        {
            "action": "play_card",
            "card_index": 0,
            "card_name": "Strike",
            "requires_target": True,
            "cost": 1,
            "damage": 8,
            "valid_targets": [{"target_index": 0, "name": "Cultist"}],
        }
    ]


def test_actions_view_adds_argument_hints() -> None:
    view = build_actions_view(load_state())

    play_card = view["available_actions"][0]
    assert play_card["action"] == "play_card"
    assert play_card["args"][0]["name"] == "card_index"


def test_brief_view_filters_to_decision_summary() -> None:
    view = build_brief_view(load_state())

    assert view["screen"] == "COMBAT"
    assert view["combat"]["incoming_damage"] == 6
    assert view["combat"]["playable"] == [
        {
            "action": "play_card",
            "card_index": 0,
            "card_name": "Strike",
            "requires_target": True,
            "valid_targets": [{"target_index": 0, "name": "Cultist"}],
            "damage": 8,
            "cost": 1,
        }
    ]
    assert "hand" not in view["combat"]
    assert "incoming 6" in view["summary"]


def test_action_result_view_reports_delta_not_full_state() -> None:
    before = load_state()
    after = before.model_copy(deep=True)
    assert after.combat is not None
    assert after.combat.enemies[0].current_hp == 24
    after.combat.enemies[0].current_hp = 16
    after.available_actions = ["end_turn"]

    view = build_action_result_view(
        action="play_card",
        args={"card_index": 0, "target_index": 0},
        status="completed",
        before=before,
        after=after,
    )

    assert view["changes"]["combat"]["enemies"][0]["current_hp"]["delta"] == -8
    assert view["state"]["available_actions"] == ["end_turn"]
    assert "hand" not in view["state"]["combat"]
