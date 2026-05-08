import pytest

from sts2_bridge.action_args import parse_action_args
from sts2_bridge.models import BridgeError


def test_parse_action_args_supports_positional_values() -> None:
    assert parse_action_args("play_card", ["0"]) == {"card_index": 0}
    assert parse_action_args("play_card", ["0", "1"]) == {"card_index": 0, "target_index": 1}


def test_parse_action_args_supports_keyword_values() -> None:
    assert parse_action_args("play_card", ["--card_index", "0"]) == {"card_index": 0}
    assert parse_action_args("play_card", ["--card-index=0", "--target_index", "1"]) == {
        "card_index": 0,
        "target_index": 1,
    }


def test_parse_action_args_supports_mixed_positional_and_keyword_values() -> None:
    assert parse_action_args("play_card", ["0", "--target_index", "1"]) == {"card_index": 0, "target_index": 1}


def test_parse_action_args_keeps_legacy_key_value_args() -> None:
    assert parse_action_args("play_card", [], ["card_index=0", "target_index=1"]) == {
        "card_index": 0,
        "target_index": 1,
    }


def test_parse_action_args_rejects_duplicate_args() -> None:
    with pytest.raises(BridgeError) as exc_info:
        parse_action_args("play_card", ["0", "--card_index", "1"])

    assert exc_info.value.code == "invalid_cli_arg"
