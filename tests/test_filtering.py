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
    assert "deck" not in json.dumps(view, ensure_ascii=False)


def test_filter_state_extracts_chinese_card_numbers_on_real_sample() -> None:
    state = GameState.model_validate(sample("state/*_combat.json")["data"])

    view = filter_state(state)
    playable = view["combat"]["playable"]

    assert any(card.get("damage") for card in playable)
    assert any(card.get("block") for card in playable)
