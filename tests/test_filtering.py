import json
from pathlib import Path

from sts2_bridge.filtering import filter_state
from sts2_bridge.models import GameState


def sample(pattern: str) -> dict:
    path = next(Path("samples/http").glob(pattern))
    return json.loads(path.read_text(encoding="utf-8"))


def test_filter_state_uses_map_schema_on_real_sample() -> None:
    state = GameState.model_validate(sample("state/*_map.json")["data"])

    view = filter_state(state)

    assert view["screen"] == "MAP"
    assert view["available_actions"] == ["choose_map_node"]
    assert view["map"]["current"] == {"row": 0, "col": 3}
    assert view["map"]["choices"][0]["option_index"] == 0
    assert view["map"]["choices"][0]["type"] == "Monster"
    assert view["map"]["choices"][0]["highlights"]["E"]
    assert view["map"]["reachable_rows"][0] == {"row": 1, "nodes": ["c0M", "c3M", "c6M"]}
    view_text = json.dumps(view, ensure_ascii=False)
    assert "deck" not in view_text
    assert "nodes" not in view["map"]


def test_filter_state_extracts_chinese_card_numbers_on_real_sample() -> None:
    state = GameState.model_validate(sample("state/*_combat.json")["data"])

    view = filter_state(state)
    playable = view["combat"]["playable"]

    assert any(card.get("damage") for card in playable)
    assert any(card.get("block") for card in playable)
    assert any(card.get("card_type") for card in playable)
    assert any(card.get("rarity") for card in playable)
    assert any(card.get("resolved_rules_text") for card in playable)
    assert view["relics"]
    assert view["glossary"]
    assert view["deck"]
    assert view["potions"]


def test_filter_state_extracts_multi_intents_on_real_sample() -> None:
    state = GameState.model_validate(sample("state/*combat_after_end_turn.json")["data"])

    view = filter_state(state)

    assert view["combat"]["incoming_damage"] == 6
    assert view["combat"]["enemies"][0]["intents"] == "attack 6, defend"


def test_filter_state_extracts_card_selection_options() -> None:
    state = GameState.model_validate(json.loads(Path("tests/fixtures/state_card_selection.json").read_text())["data"])

    view = filter_state(state)

    assert view["screen"] == "CARD_SELECTION"
    assert view["selection"]["kind"] == "combat_hand_select"
    assert view["selection"]["cards"][0]["option_index"] == 0
    assert view["selection"]["cards"][0]["name"] == "Strike"
    assert view["selection"]["cards"][1]["keywords"] == ["Block"]


def test_filter_state_adds_rest_fallback_actions_when_api_omits_options() -> None:
    state = GameState.model_validate(json.loads(Path("tests/fixtures/state_rest_missing_actions.json").read_text())["data"])

    view = filter_state(state)

    assert view["screen"] == "REST"
    assert view.get("available_actions", []) == []
    assert view["summary"] == "REST screen with 0 legal action(s)."
    assert view["rest"]["options"][0]["option_index"] == 0
    assert view["rest"]["options"][0]["source"] == "fallback"
    assert view["rest"]["options"][1]["label"] == "Smith"


def test_filter_state_does_not_show_rest_fallback_options_after_rest_choice() -> None:
    state = GameState.model_validate(json.loads(Path("tests/fixtures/state_rest_proceed.json").read_text())["data"])

    view = filter_state(state)

    assert view["available_actions"] == ["proceed"]
    assert "rest" not in view


def test_filter_state_shows_rest_recovery_when_only_potion_action_exists() -> None:
    state = GameState.model_validate(json.loads(Path("tests/fixtures/state_rest_potion_only.json").read_text())["data"])

    view = filter_state(state)

    assert view["available_actions"] == ["discard_potion"]
    assert view["rest"]["options"][0]["source"] == "fallback"


def test_filter_state_extracts_reward_rows() -> None:
    state = GameState.model_validate(json.loads(Path("tests/fixtures/state_reward_rows.json").read_text())["data"])

    view = filter_state(state)

    assert view["screen"] == "REWARD"
    assert view["reward"]["rewards"][0]["line"] == "Gold: 17金币"
    assert view["reward"]["rewards"][1]["reward_type"] == "Card"
    assert "card_options" not in view["reward"]


def test_filter_state_extracts_reward_card_choices() -> None:
    state = GameState.model_validate(json.loads(Path("tests/fixtures/state_reward_cards.json").read_text())["data"])

    view = filter_state(state)

    assert view["reward"]["pending_card_choice"] is True
    assert view["reward"]["card_options"][0]["option_index"] == 0
    assert view["reward"]["card_options"][0]["name"] == "精准"
    assert view["reward"]["alternatives"][0]["label"] == "跳过"
