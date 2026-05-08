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


def test_filter_state_extracts_multi_intents_on_real_sample() -> None:
    state = GameState.model_validate(sample("state/*combat_after_end_turn.json")["data"])

    view = filter_state(state)

    assert view["combat"]["incoming_damage"] == 6
    assert view["combat"]["enemies"][0]["intents"] == "attack 6, defend"
