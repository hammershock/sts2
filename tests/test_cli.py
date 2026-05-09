import json
from pathlib import Path
import sys

import httpx
import pytest
import respx
import yaml
from typer.testing import CliRunner

from sts2_bridge.cli import app, _interactive_action_from_input, _to_yaml
from sts2_bridge.filtering import filter_state
from sts2_bridge.models import BridgeError, GameState

BASE_URL = "http://test.local"
runner = CliRunner()


def fixture(name: str) -> dict:
    return json.loads(Path(f"tests/fixtures/{name}.json").read_text())


def sample(pattern: str) -> dict:
    path = next(Path("samples/http").glob(pattern))
    return json.loads(path.read_text(encoding="utf-8"))


def write_http_log(logs_dir: Path, *records: dict) -> None:
    logs_dir.mkdir(parents=True, exist_ok=True)
    path = logs_dir / "test.jsonl"
    path.write_text("\n".join(json.dumps(record) for record in records) + "\n", encoding="utf-8")


def http_record(method: str, url: str, payload: dict | None, response: dict | None, status_code: int | None = 200) -> dict:
    record: dict = {
        "request": {"method": method, "url": url, "body": payload},
    }
    if response is not None:
        record["response"] = {"status_code": status_code, "text": json.dumps(response)}
    return record


@respx.mock
def test_cli_health_outputs_text(isolated_logs) -> None:
    respx.get(f"{BASE_URL}/health").mock(
        return_value=httpx.Response(200, json={"ok": True, "data": {"status": "ready"}})
    )

    result = runner.invoke(app, ["debug", "health", "--base-url", BASE_URL])

    assert result.exit_code == 0
    assert result.stdout == "Health: ready\n"
    records = _read_log_records(isolated_logs, "cli")
    assert records[-1]["command_path"].endswith("debug health")
    assert records[-1]["return_code"] == 0
    assert records[-1]["output"] == "Health: ready\n"


def test_debug_route_render_samples_rebuilds_file_tree(tmp_path) -> None:
    logs_dir = tmp_path / "http"
    output_dir = tmp_path / "route_render_samples"
    stale = output_dir / "stale.txt"
    stale.parent.mkdir(parents=True)
    stale.write_text("old\n", encoding="utf-8")
    write_http_log(
        logs_dir,
        http_record(
            "GET",
            "http://127.0.0.1:8080/state",
            None,
            {
                "ok": True,
                "request_id": "req_state",
                "data": {
                    "screen": "MAP",
                    "available_actions": ["choose_map_node"],
                    "run": {"floor": 2, "gold": 99},
                    "map": {"available_nodes": [{"index": 0, "row": 1, "col": 0}]},
                },
            },
        ),
        http_record(
            "POST",
            "http://127.0.0.1:8080/action",
            {"action": "play_card", "card_index": 0},
            {
                "ok": True,
                "request_id": "req_action",
                "data": {"action": "play_card", "status": "completed", "stable": True, "message": "Action completed."},
            },
        ),
    )

    result = runner.invoke(
        app,
        [
            "debug",
            "route-render-samples",
            "--logs-dir",
            str(logs_dir),
            "--output-dir",
            str(output_dir),
        ],
    )

    assert result.exit_code == 0
    assert "Route render samples regenerated." in result.stdout
    assert "Routes: 2" in result.stdout
    assert "Samples: 2" in result.stdout
    assert not stale.exists()
    state_file = next((output_dir / "state/map/route_selection").glob("*.txt"))
    action_file = next((output_dir / "action/gameplay/combat/play_card/completed").glob("*.txt"))
    assert state_file.read_text(encoding="utf-8").startswith("MAP floor=2 gold=99")
    assert action_file.read_text(encoding="utf-8").startswith("Action: play_card")
    index = (output_dir / "index.txt").read_text(encoding="utf-8")
    assert "state/map/route_selection" in index
    assert "action/gameplay/combat/play_card/completed" in index


def test_debug_help_omits_old_route_probe_commands() -> None:
    result = runner.invoke(app, ["debug", "--help"])

    assert result.exit_code == 0
    assert "route-render-samples" in result.stdout
    assert "route-sample " not in result.stdout
    assert "route-samples " not in result.stdout
    assert "route-tree " not in result.stdout


@respx.mock
def test_cli_state_defaults_to_text_view() -> None:
    respx.get(f"{BASE_URL}/state").mock(return_value=httpx.Response(200, json=fixture("state_combat")))

    result = runner.invoke(app, ["state", "--base-url", BASE_URL])

    assert result.exit_code == 0
    assert result.stdout.startswith("COMBAT turn=2 floor=3 gold=99 route=state/gameplay/combat/actionable")
    assert "Player: HP 63/75 | Block 4 | Energy 3 | Stars 1" in result.stdout
    assert "[0] Cultist | HP 24/48 | Block 0 | Intent attack | alive" in result.stdout
    assert "[0] Strike [1]: Deal 8 damage. | playable | targets 0" in result.stdout
    assert "- Block: Block prevents attack damage." in result.stdout
    assert "[0] sts2 act play_card <card_index> 0" in result.stdout
    assert "[1] sts2 act end_turn" in result.stdout


@respx.mock
def test_cli_state_filtered_layer_outputs_text() -> None:
    respx.get(f"{BASE_URL}/state").mock(return_value=httpx.Response(200, json=fixture("state_combat")))

    result = runner.invoke(app, ["state", "--layer", "filtered", "--base-url", BASE_URL])

    assert result.exit_code == 2
    assert "No such option: --layer" in result.output


@respx.mock
def test_cli_state_renders_compact_map_view() -> None:
    respx.get(f"{BASE_URL}/state").mock(return_value=httpx.Response(200, json=sample("state/*_map.json")))

    result = runner.invoke(app, ["state", "--base-url", BASE_URL])

    assert result.exit_code == 0
    assert result.stdout.startswith("MAP floor=1 gold=99")
    assert "Current: r0c3" in result.stdout
    assert "[0] Monster (1,0)" in result.stdout
    assert "Reachable map:" in result.stdout
    assert "Legal actions:\n[0] sts2 act choose_map_node <option_index in 0, 1, 2>" in result.stdout
    assert "deck" not in result.stdout


@respx.mock
def test_cli_state_renders_event_title_and_options() -> None:
    event_sample = json.loads(Path("samples/http/state/20260508-224602-02_event.json").read_text())
    respx.get(f"{BASE_URL}/state").mock(
        return_value=httpx.Response(200, json=event_sample)
    )

    result = runner.invoke(app, ["state", "--base-url", BASE_URL])

    assert result.exit_code == 0
    assert result.stdout.startswith("EVENT floor=1 gold=99")
    assert "Event: 涅奥 (NEOW)" in result.stdout
    assert "[0] 轰鸣海螺 | 在精英战的战斗开始时，额外抽2张牌。" in result.stdout
    assert "[1] 金色珍珠 | 拾起时，获得150金币。" in result.stdout
    assert "[2] 沉重石板 | 从3张稀有牌中选择1张加入你的牌组。将1张受伤加入你的牌组。" in result.stdout
    assert "Legal actions:\n[0] sts2 act choose_event_option <option_index in 0, 1, 2>" in result.stdout


@respx.mock
def test_cli_state_renders_main_menu_timeline_slots() -> None:
    respx.get(f"{BASE_URL}/state").mock(return_value=httpx.Response(200, json=fixture("state_main_menu_timeline")))

    result = runner.invoke(app, ["state", "--base-url", BASE_URL])

    assert result.exit_code == 0
    assert result.stdout.startswith("MAIN_MENU")
    assert "Timeline: can_choose" in result.stdout
    assert "Timeline slots:" in result.stdout
    assert "[0] 先子星 | complete | COLORLESS1_EPOCH" in result.stdout
    assert "[6] 涅奥 | complete | NEOW_EPOCH" in result.stdout
    assert "[1] sts2 act choose_timeline_epoch" in result.stdout


@respx.mock
def test_cli_state_renders_timeline_overlay_limit() -> None:
    respx.get(f"{BASE_URL}/state").mock(
        return_value=httpx.Response(200, json=fixture("state_main_menu_timeline_overlay"))
    )

    result = runner.invoke(app, ["state", "--base-url", BASE_URL])

    assert result.exit_code == 0
    assert "Timeline: inspect_open, can_confirm, can_choose" in result.stdout
    assert "[2] sts2 act confirm_timeline_overlay" in result.stdout


@respx.mock
def test_cli_state_renders_character_select_route() -> None:
    respx.get(f"{BASE_URL}/state").mock(
        return_value=httpx.Response(
            200,
            json={
                "ok": True,
                "request_id": "character-select-test",
                "data": {
                    "screen": "CHARACTER_SELECT",
                    "available_actions": ["close_main_menu_submenu", "select_character", "embark"],
                    "character_select": {
                        "selected_character_id": "REGENT",
                        "can_embark": True,
                        "ascension": 0,
                        "player_count": 1,
                        "max_players": 1,
                        "characters": [
                            {"index": 0, "character_id": "IRONCLAD", "name": "铁甲战士", "is_locked": False, "is_selected": False},
                            {"index": 3, "character_id": "REGENT", "name": "储君", "is_locked": False, "is_selected": True},
                        ],
                    },
                },
            },
        )
    )

    result = runner.invoke(app, ["state", "--base-url", BASE_URL])

    assert result.exit_code == 0
    assert result.stdout.startswith("CHARACTER_SELECT route=state/character_select/select")
    assert "Selected: REGENT | Embark: true | Ascension: 0 | Players: 1/1" in result.stdout
    assert "[3] 储君 | selected" in result.stdout
    assert "[1] sts2 act select_character <option_index in 0, 3>" in result.stdout


@respx.mock
def test_cli_state_renders_open_shop_inventory() -> None:
    respx.get(f"{BASE_URL}/state").mock(return_value=httpx.Response(200, json=fixture("state_shop_open")))

    result = runner.invoke(app, ["state", "--base-url", BASE_URL])

    assert result.exit_code == 0
    assert result.stdout.startswith("SHOP floor=22 gold=194")
    assert "Shop: open" in result.stdout
    assert "price=75 available=True used=False" in result.stdout
    assert "[0] sts2 act close_shop_inventory" in result.stdout
    assert "[1] sts2 act buy_card <option_index>" in result.stdout


@respx.mock
def test_cli_state_renders_game_over_death_even_with_victory_flag() -> None:
    respx.get(f"{BASE_URL}/state").mock(
        return_value=httpx.Response(200, json=fixture("state_game_over_death_victory_flag"))
    )

    result = runner.invoke(app, ["state", "--base-url", BASE_URL])

    assert result.exit_code == 0
    assert result.stdout.startswith("GAME_OVER floor=48 gold=49")
    assert "Result: death | floor 48 | character SILENT | HP 0/80 | alive false" in result.stdout
    assert "[0] sts2 act return_to_main_menu" in result.stdout


@respx.mock
def test_cli_state_renders_card_selection_options() -> None:
    respx.get(f"{BASE_URL}/state").mock(return_value=httpx.Response(200, json=fixture("state_card_selection")))

    result = runner.invoke(app, ["state", "--base-url", BASE_URL])

    assert result.exit_code == 0
    assert result.stdout.startswith("CARD_SELECTION turn=3 floor=5 gold=88")
    assert "Prompt: 选择1张牌保留。" in result.stdout
    assert "[0] Strike [1]: Deal 6 damage." in result.stdout
    assert "[1] Defend [1]: Gain 5 Block." in result.stdout
    assert "Legal actions:\n[0] sts2 act select_deck_card <option_index in 0, 1>\n[1] sts2 act confirm_selection" in result.stdout


@respx.mock
def test_cli_state_renders_rest_fallback_options() -> None:
    respx.get(f"{BASE_URL}/state").mock(return_value=httpx.Response(200, json=fixture("state_rest_missing_actions")))

    result = runner.invoke(app, ["state", "--base-url", BASE_URL])

    assert result.exit_code == 0
    assert result.stdout.startswith("REST floor=11 gold=147")
    assert "Recovery options:" not in result.stdout
    assert "No legal actions exposed by /state." in result.stdout


@respx.mock
def test_cli_wait_returns_rest_recovery_state_when_api_omits_actions() -> None:
    respx.get(f"{BASE_URL}/state").mock(return_value=httpx.Response(200, json=fixture("state_rest_missing_actions")))

    result = runner.invoke(app, ["wait", "--base-url", BASE_URL, "--timeout", "0.01"])

    assert result.exit_code == 1
    assert "wait_timeout" in result.stdout


@respx.mock
def test_cli_state_does_not_render_rest_fallback_options_after_choice() -> None:
    respx.get(f"{BASE_URL}/state").mock(return_value=httpx.Response(200, json=fixture("state_rest_proceed")))

    result = runner.invoke(app, ["state", "--base-url", BASE_URL])

    assert result.exit_code == 0
    assert "Options:" not in result.stdout
    assert result.stdout.rstrip().endswith("Legal actions:\n[0] sts2 act proceed")


@respx.mock
def test_cli_state_renders_rest_recovery_when_only_potion_action_exists() -> None:
    respx.get(f"{BASE_URL}/state").mock(return_value=httpx.Response(200, json=fixture("state_rest_potion_only")))

    result = runner.invoke(app, ["state", "--base-url", BASE_URL])

    assert result.exit_code == 0
    assert "Recovery options:" not in result.stdout
    assert "Legal actions:\n[0] sts2 act discard_potion <option_index> [target_index]" in result.stdout


@respx.mock
def test_cli_state_renders_reward_rows_and_unloaded_card_note() -> None:
    respx.get(f"{BASE_URL}/state").mock(return_value=httpx.Response(200, json=fixture("state_reward_rows")))

    result = runner.invoke(app, ["state", "--base-url", BASE_URL])

    assert result.exit_code == 0
    assert result.stdout.startswith("REWARD floor=14 gold=22")
    assert "Reward: pending_card_choice=false, can_proceed=true" in result.stdout
    assert "[0] Gold: 17金币" in result.stdout
    assert "[1] Card: 将一张牌添加到你的牌组。" in result.stdout
    assert "[0] sts2 act resolve_rewards [unavailable, use sts2 act claim_reward 1 instead]" in result.stdout
    assert "[1] sts2 act collect_rewards_and_proceed [unavailable, use sts2 act claim_reward 1 instead]" in result.stdout
    assert "[2] sts2 act claim_reward <option_index in 0, 1>" in result.stdout


@respx.mock
def test_cli_state_renders_reward_card_choices() -> None:
    respx.get(f"{BASE_URL}/state").mock(return_value=httpx.Response(200, json=fixture("state_reward_cards")))

    result = runner.invoke(app, ["state", "--base-url", BASE_URL])

    assert result.exit_code == 0
    assert "Reward: pending_card_choice=true, can_proceed=false" in result.stdout
    assert "Card choices:" in result.stdout
    assert "[0] 精准：小刀额外造成4点伤害。" in result.stdout
    assert "[1] 投掷匕首：造成9点伤害。 抽1张牌。 丢弃一张牌。" in result.stdout
    assert "Alternatives:\n[0] 跳过" in result.stdout
    assert "[0] sts2 act choose_reward_card <option_index in 0, 1>" in result.stdout
    assert "[1] sts2 act skip_reward_cards" in result.stdout


@respx.mock
def test_cli_act_rejects_legacy_arg_option() -> None:
    respx.get(f"{BASE_URL}/state").mock(return_value=httpx.Response(200, json=fixture("state_combat")))

    result = runner.invoke(app, ["act", "play_card", "--arg", "card_index=0", "--base-url", BASE_URL])

    assert result.exit_code == 1
    assert result.stdout.startswith("ERROR invalid_cli_arg:")


@respx.mock
def test_cli_act_parses_action_alias_and_keyword_args() -> None:
    route = respx.post(f"{BASE_URL}/action").mock(
        return_value=httpx.Response(200, json={"ok": True, "data": {"status": "completed"}})
    )
    before_state = {
        "ok": True,
        "data": {
            "screen": "COMBAT",
            "in_combat": True,
            "available_actions": ["play_card", "end_turn"],
            "combat": {"hand": [{"index": 0, "name": "Strike", "playable": True}], "enemies": []},
        },
    }
    after_state = {
        "ok": True,
        "data": {
            "screen": "COMBAT",
            "in_combat": True,
            "available_actions": ["end_turn"],
            "combat": {"hand": [], "enemies": []},
        },
    }
    respx.get(f"{BASE_URL}/state").mock(
        side_effect=[httpx.Response(200, json=before_state), httpx.Response(200, json=after_state)]
    )

    result = runner.invoke(
        app,
        [
            "act",
            "playcard",
            "--card_index",
            "0",
            "--target_index",
            "1",
            "--base-url",
            BASE_URL,
        ],
    )

    assert result.exit_code == 0
    assert json.loads(route.calls.last.request.content) == {"action": "play_card", "card_index": 0, "target_index": 1}
    assert "Action: play_card" in result.stdout
    assert "Args: card_index=0, target_index=1" in result.stdout
    assert "Route: action/gameplay/combat/play_card/completed" in result.stdout
    assert "Changes:" not in result.stdout


@respx.mock
def test_cli_act_parses_positional_action_args() -> None:
    route = respx.post(f"{BASE_URL}/action").mock(
        return_value=httpx.Response(200, json={"ok": True, "data": {"status": "completed"}})
    )
    respx.get(f"{BASE_URL}/state").mock(
        return_value=httpx.Response(
            200,
            json={
                "ok": True,
                "data": {
                    "screen": "COMBAT",
                    "in_combat": True,
                    "available_actions": ["play_card", "end_turn"],
                    "combat": {"hand": [], "enemies": []},
                },
            },
        )
    )

    result = runner.invoke(app, ["act", "play_card", "0", "1", "--base-url", BASE_URL])

    assert result.exit_code == 0
    assert json.loads(route.calls.last.request.content) == {"action": "play_card", "card_index": 0, "target_index": 1}


@respx.mock
def test_cli_act_routes_action_error_response() -> None:
    route = respx.post(f"{BASE_URL}/action").mock(
        return_value=httpx.Response(
            409,
            json={
                "ok": False,
                "request_id": "req_error",
                "error": {
                    "code": "invalid_target",
                    "message": "This card requires target_index.",
                    "details": {"action": "play_card", "card_id": "Strike"},
                    "retryable": False,
                },
            },
        )
    )
    respx.get(f"{BASE_URL}/state").mock(
        return_value=httpx.Response(
            200,
            json={
                "ok": True,
                "data": {
                    "screen": "COMBAT",
                    "in_combat": True,
                    "available_actions": ["play_card"],
                    "combat": {"hand": [{"index": 0, "name": "Strike", "playable": True}], "enemies": []},
                },
            },
        )
    )

    result = runner.invoke(app, ["act", "play_card", "0", "--base-url", BASE_URL])

    assert result.exit_code == 1
    assert route.called
    assert "Route: action/gameplay/combat/play_card/error/invalid_target" in result.stdout
    assert "Message: This card requires target_index." in result.stdout


@respx.mock
def test_cli_act_routes_pending_action_response() -> None:
    pending_state = {
        "screen": "CARD_SELECTION",
        "available_actions": ["select_deck_card"],
        "selection": {
            "kind": "combat_hand_select",
            "prompt": "选择1张牌。",
            "cards": [{"index": 0, "name": "Strike", "energy_cost": 1, "resolved_rules_text": "Deal 6 damage."}],
        },
    }
    respx.post(f"{BASE_URL}/action").mock(
        return_value=httpx.Response(
            200,
            json={
                "ok": True,
                "request_id": "req_pending",
                "data": {
                    "action": "play_card",
                    "status": "pending",
                    "stable": False,
                    "message": "Action is waiting for a follow-up selection.",
                    "state": pending_state,
                },
            },
        )
    )
    respx.get(f"{BASE_URL}/state").mock(
        return_value=httpx.Response(
            200,
            json={
                "ok": True,
                "data": {
                    "screen": "COMBAT",
                    "in_combat": True,
                    "available_actions": ["play_card"],
                    "combat": {"hand": [{"index": 0, "name": "Setup", "playable": True}], "enemies": []},
                },
            },
        )
    )

    result = runner.invoke(app, ["act", "play_card", "0", "--base-url", BASE_URL])

    assert result.exit_code == 0
    assert "Route: action/gameplay/combat/play_card/pending" in result.stdout
    assert "Next: continue from embedded state below." in result.stdout
    assert "State:\nCARD_SELECTION" in result.stdout


@respx.mock
def test_cli_act_parses_numbered_action_and_keyword_args() -> None:
    route = respx.post(f"{BASE_URL}/action").mock(
        return_value=httpx.Response(200, json={"ok": True, "data": {"status": "completed"}})
    )
    respx.get(f"{BASE_URL}/state").mock(
        return_value=httpx.Response(
            200,
            json={
                "ok": True,
                "data": {
                    "screen": "COMBAT",
                    "in_combat": True,
                    "available_actions": ["end_turn", "play_card"],
                    "combat": {"hand": [], "enemies": []},
                },
            },
        )
    )

    result = runner.invoke(app, ["act", "1", "--card_index", "0", "--target_index", "1", "--base-url", BASE_URL])

    assert result.exit_code == 0
    assert json.loads(route.calls.last.request.content) == {"action": "play_card", "card_index": 0, "target_index": 1}


@respx.mock
def test_cli_act_uses_default_option_index_for_numbered_option_action() -> None:
    route = respx.post(f"{BASE_URL}/action").mock(
        return_value=httpx.Response(200, json={"ok": True, "data": {"status": "completed"}})
    )
    respx.get(f"{BASE_URL}/state").mock(
        return_value=httpx.Response(
            200,
            json={
                "ok": True,
                "data": {
                    "screen": "MAP",
                    "available_actions": ["choose_map_node"],
                    "run": {"floor": 2, "gold": 115},
                    "map": {"available_nodes": [{"index": 0}]},
                },
            },
        )
    )

    result = runner.invoke(app, ["act", "0", "--base-url", BASE_URL])

    assert result.exit_code == 0
    assert json.loads(route.calls.last.request.content) == {"action": "choose_map_node", "option_index": 0}


@respx.mock
def test_cli_act_rejects_implicit_option_index_when_multiple_choices_exist() -> None:
    route = respx.post(f"{BASE_URL}/action").mock(
        return_value=httpx.Response(200, json={"ok": True, "data": {"status": "completed"}})
    )
    respx.get(f"{BASE_URL}/state").mock(return_value=httpx.Response(200, json=fixture("state_event_neow_three_options")))

    result = runner.invoke(app, ["act", "0", "--base-url", BASE_URL])

    assert result.exit_code == 1
    assert "ERROR ambiguous_action_args:" in result.stdout
    assert "valid_option_index:" in result.stdout
    assert not route.calls


@respx.mock
def test_cli_act_accepts_explicit_option_index_when_multiple_choices_exist() -> None:
    route = respx.post(f"{BASE_URL}/action").mock(
        return_value=httpx.Response(200, json={"ok": True, "data": {"status": "completed"}})
    )
    respx.get(f"{BASE_URL}/state").mock(
        side_effect=[
            httpx.Response(200, json=fixture("state_event_neow_three_options")),
            httpx.Response(200, json=fixture("state_event_neow_three_options")),
        ]
    )

    result = runner.invoke(app, ["act", "choose_event_option", "1", "--base-url", BASE_URL])

    assert result.exit_code == 0
    assert json.loads(route.calls.last.request.content) == {"action": "choose_event_option", "option_index": 1}


@respx.mock
def test_cli_act_rejects_rest_fallback_action_when_api_omits_actions() -> None:
    route = respx.post(f"{BASE_URL}/action").mock(
        return_value=httpx.Response(200, json={"ok": True, "data": {"status": "completed"}})
    )
    respx.get(f"{BASE_URL}/state").mock(return_value=httpx.Response(200, json=fixture("state_rest_missing_actions")))

    result = runner.invoke(app, ["act", "0", "--base-url", BASE_URL])

    assert result.exit_code == 1
    assert "ERROR invalid_action:" in result.stdout
    assert not route.calls


@respx.mock
def test_cli_act_renders_action_route_without_refetching_state() -> None:
    route = respx.post(f"{BASE_URL}/action").mock(
        return_value=httpx.Response(200, json={"ok": True, "data": {"status": "completed"}})
    )
    before_state = {
        "ok": True,
        "data": {
            "screen": "REST",
            "available_actions": ["choose_rest_option"],
            "run": {"floor": 11, "gold": 147, "current_hp": 26, "max_hp": 70},
            "rest": {"options": [{"index": 0, "label": "Rest"}]},
        },
    }
    respx.get(f"{BASE_URL}/state").mock(
        side_effect=[
            httpx.Response(200, json=before_state),
            httpx.Response(200, json=fixture("state_rest_missing_actions")),
        ]
    )

    result = runner.invoke(app, ["act", "choose_rest_option", "0", "--base-url", BASE_URL])

    assert result.exit_code == 0
    assert json.loads(route.calls.last.request.content) == {"action": "choose_rest_option", "option_index": 0}
    assert "Route: action/rest/choose_rest_option/completed" in result.stdout
    assert "REST recovery:" not in result.stdout


@respx.mock
def test_cli_act_uses_embedded_action_state() -> None:
    before_state = {
        "ok": True,
        "data": {
            "screen": "COMBAT",
            "in_combat": True,
            "available_actions": ["play_card"],
            "combat": {
                "player": {"current_hp": 40, "max_hp": 70, "block": 0, "energy": 1},
                "hand": [{"index": 0, "name": "Setup", "playable": True, "energy_cost": 0}],
                "enemies": [],
            },
        },
    }
    stale_embedded_state = {
        "screen": "COMBAT",
        "in_combat": True,
        "available_actions": ["play_card"],
        "combat": {
            "player": {"current_hp": 40, "max_hp": 70, "block": 0, "energy": 1},
            "hand": [
                {"index": 0, "name": "Defend", "playable": True, "energy_cost": 1},
                {"index": 1, "name": "Strike", "playable": True, "energy_cost": 1, "requires_target": True},
                {"index": 2, "name": "Blade Dance", "playable": True, "energy_cost": 1},
            ],
            "enemies": [],
        },
    }
    fresh_after_state = {
        "ok": True,
        "data": {
            "screen": "COMBAT",
            "in_combat": True,
            "available_actions": ["play_card"],
            "combat": {
                "player": {"current_hp": 40, "max_hp": 70, "block": 0, "energy": 1},
                "hand": [
                    {"index": 0, "name": "Defend", "playable": True, "energy_cost": 1},
                    {"index": 1, "name": "Blade Dance", "playable": True, "energy_cost": 1},
                    {"index": 2, "name": "Strike", "playable": True, "energy_cost": 1, "requires_target": True},
                ],
                "enemies": [],
            },
        },
    }
    respx.post(f"{BASE_URL}/action").mock(
        return_value=httpx.Response(200, json={"ok": True, "data": {"status": "completed", "state": stale_embedded_state}})
    )
    respx.get(f"{BASE_URL}/state").mock(
        side_effect=[httpx.Response(200, json=before_state), httpx.Response(200, json=fresh_after_state)]
    )

    result = runner.invoke(app, ["act", "play_card", "0", "--base-url", BASE_URL])

    assert result.exit_code == 0
    assert "State:\nCOMBAT" in result.stdout
    assert "[1] Strike" in result.stdout
    assert "[2] Blade Dance" in result.stdout


@respx.mock
def test_cli_act_does_not_poll_for_post_action_state() -> None:
    route = respx.post(f"{BASE_URL}/action").mock(
        return_value=httpx.Response(200, json={"ok": True, "data": {"status": "completed"}})
    )
    before_state = {
        "ok": True,
        "data": {
            "screen": "REWARD",
            "available_actions": ["collect_rewards_and_proceed"],
            "run": {"floor": 48, "gold": 49},
            "reward": {"pending_card_choice": False, "can_proceed": True, "rewards": [], "card_options": []},
        },
    }
    bogus_transition = {
        "ok": True,
        "data": {
            "screen": "COMBAT",
            "in_combat": False,
            "available_actions": [],
            "run": {"floor": 48, "gold": 49},
            "combat": {"player": {}, "hand": [], "enemies": []},
        },
    }
    final_event = {
        "ok": True,
        "data": {
            "screen": "EVENT",
            "available_actions": ["choose_event_option"],
            "run": {"floor": 48, "gold": 49},
            "event": {
                "event_id": "THE_ARCHITECT",
                "title": "建筑师",
                "options": [{"index": 0, "title": "继续", "description": "", "is_proceed": True}],
            },
        },
    }
    respx.get(f"{BASE_URL}/state").mock(
        side_effect=[
            httpx.Response(200, json=before_state),
            httpx.Response(200, json=bogus_transition),
            httpx.Response(200, json=final_event),
        ]
    )

    result = runner.invoke(app, ["act", "collect_rewards_and_proceed", "--base-url", BASE_URL])

    assert result.exit_code == 0
    assert route.called
    assert "Route: action/reward/collect_rewards_and_proceed/completed" in result.stdout
    assert "State:" not in result.stdout
    assert "Player: HP ?/?" not in result.stdout


@respx.mock
def test_cli_act_no_longer_synthesizes_state_deltas() -> None:
    route = respx.post(f"{BASE_URL}/action").mock(
        return_value=httpx.Response(200, json={"ok": True, "data": {"status": "completed"}})
    )
    before_state = {
        "ok": True,
        "data": {
            "screen": "COMBAT",
            "in_combat": True,
            "available_actions": ["play_card"],
            "run": {"floor": 48, "gold": 49},
            "combat": {
                "player": {"current_hp": 10, "max_hp": 80, "block": 0, "energy": 1},
                "hand": [{"index": 0, "name": "突然一拳", "playable": True, "energy_cost": 1}],
                "enemies": [{"index": 0, "name": "女王", "current_hp": 11, "max_hp": 300, "block": 0, "is_alive": True}],
            },
        },
    }
    after_state = {
        "ok": True,
        "data": {
            "screen": "REWARD",
            "in_combat": False,
            "available_actions": ["collect_rewards_and_proceed"],
            "run": {"floor": 48, "gold": 49},
            "reward": {"pending_card_choice": False, "can_proceed": True, "rewards": [], "card_options": []},
        },
    }
    respx.get(f"{BASE_URL}/state").mock(
        side_effect=[httpx.Response(200, json=before_state), httpx.Response(200, json=after_state)]
    )

    result = runner.invoke(app, ["act", "play_card", "0", "--base-url", BASE_URL])

    assert result.exit_code == 0
    assert route.called
    assert "Route: action/gameplay/combat/play_card/completed" in result.stdout
    assert "current_hp:" not in result.stdout
    assert "delta:" not in result.stdout


@respx.mock
def test_cli_act_blocks_resolve_rewards_when_card_reward_is_unloaded() -> None:
    route = respx.post(f"{BASE_URL}/action").mock(
        return_value=httpx.Response(200, json={"ok": True, "data": {"status": "completed"}})
    )
    respx.get(f"{BASE_URL}/state").mock(return_value=httpx.Response(200, json=fixture("state_reward_rows")))

    result = runner.invoke(app, ["act", "resolve_rewards", "--base-url", BASE_URL])

    assert result.exit_code == 1
    assert "ERROR unsafe_reward_resolution:" in result.stdout
    assert "claim_reward" in result.stdout
    assert not route.calls


@respx.mock
def test_cli_act_blocks_collect_rewards_when_card_reward_is_unloaded() -> None:
    route = respx.post(f"{BASE_URL}/action").mock(
        return_value=httpx.Response(200, json={"ok": True, "data": {"status": "completed"}})
    )
    respx.get(f"{BASE_URL}/state").mock(return_value=httpx.Response(200, json=fixture("state_reward_rows")))

    result = runner.invoke(app, ["act", "collect_rewards_and_proceed", "--base-url", BASE_URL])

    assert result.exit_code == 1
    assert "ERROR unsafe_reward_resolution:" in result.stdout
    assert not route.calls


@respx.mock
def test_cli_actions_renders_option_index_default_as_text() -> None:
    respx.get(f"{BASE_URL}/state").mock(
        return_value=httpx.Response(
            200,
            json={
                "ok": True,
                "data": {
                    "screen": "MAP",
                    "available_actions": ["choose_map_node"],
                    "run": {"floor": 2, "gold": 115},
                },
            },
        )
    )

    result = runner.invoke(app, ["actions", "--base-url", BASE_URL])

    assert result.exit_code == 2
    assert "No such command" in result.output


@respx.mock
def test_cli_actions_renders_shop_and_potion_option_index() -> None:
    respx.get(f"{BASE_URL}/state").mock(
        return_value=httpx.Response(
            200,
            json={
                "ok": True,
                "data": {
                    "screen": "SHOP",
                    "available_actions": ["buy_card", "buy_potion", "use_potion"],
                    "run": {"floor": 2, "gold": 115},
                },
            },
        )
    )

    result = runner.invoke(app, ["actions", "--base-url", BASE_URL])

    assert result.exit_code == 2
    assert "No such command" in result.output


@respx.mock
def test_cli_rejects_invalid_arg_shape() -> None:
    respx.get(f"{BASE_URL}/state").mock(
        return_value=httpx.Response(
            200,
            json={
                "ok": True,
                "data": {
                    "screen": "COMBAT",
                    "in_combat": True,
                    "available_actions": ["play_card"],
                    "combat": {"hand": [], "enemies": []},
                },
            },
        )
    )

    result = runner.invoke(app, ["act", "play_card", "--arg", "card_index", "--base-url", BASE_URL])

    assert result.exit_code == 1
    assert result.stdout.startswith("ERROR invalid_cli_arg:")


def test_cli_policy_commands_are_not_registered() -> None:
    suggest_result = runner.invoke(app, ["suggest"])
    step_result = runner.invoke(app, ["step"])

    assert suggest_result.exit_code == 2
    assert step_result.exit_code == 2


def test_cli_help_groups_debug_commands_and_removes_combat() -> None:
    top_result = runner.invoke(app, ["--help"])
    debug_result = runner.invoke(app, ["debug", "--help"])

    assert top_result.exit_code == 0
    assert debug_result.exit_code == 0
    assert "debug" in top_result.stdout
    assert "combat" not in top_result.stdout
    assert "health" not in top_result.stdout
    assert "windows" not in top_result.stdout
    assert "window-status" not in top_result.stdout
    assert "health" in debug_result.stdout
    assert "windows" in debug_result.stdout
    assert "window-status" in debug_result.stdout
    assert "click-window" in debug_result.stdout
    assert "recover-rest" in debug_result.stdout


def test_cli_without_args_prints_help_without_tty(isolated_logs) -> None:
    result = runner.invoke(app, [])

    assert result.exit_code == 0
    assert "Usage: " in result.stdout
    assert "state" in result.stdout
    assert "debug" in result.stdout
    assert not (isolated_logs / "cli").exists()


def test_cli_help_does_not_expose_pretty_or_json_format(isolated_logs) -> None:
    top_result = runner.invoke(app, ["--help"])
    state_result = runner.invoke(app, ["state", "--help"])
    act_result = runner.invoke(app, ["act", "--help"])
    debug_result = runner.invoke(app, ["debug", "health", "--help"])

    assert top_result.exit_code == 0
    assert state_result.exit_code == 0
    assert act_result.exit_code == 0
    assert debug_result.exit_code == 0
    combined = top_result.stdout + state_result.stdout + act_result.stdout + debug_result.stdout
    assert "--pretty" not in combined
    assert "--format" not in combined
    assert not (isolated_logs / "cli").exists()


def test_to_yaml_normalizes_string_subclasses() -> None:
    class ForeignString(str):
        pass

    assert _to_yaml({"owner": ForeignString("Slay the Spire 2")}) == "owner: Slay the Spire 2\n"


@respx.mock
def test_cli_debug_recover_rest_dry_run(monkeypatch) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    import sts2_bridge.macos_screenshot as macos_screenshot

    click_calls: list[dict] = []

    def fake_click_window(*args, **kwargs):
        click_calls.append({"args": args, "kwargs": kwargs})
        return {
            "clicked": False,
            "dry_run": True,
            "screen_point": {"x": 101, "y": 202},
        }

    monkeypatch.setattr(macos_screenshot, "click_window", fake_click_window)
    monkeypatch.setattr(macos_screenshot, "press_key", lambda *args, **kwargs: {"pressed": False, "dry_run": True})
    respx.get(f"{BASE_URL}/state").mock(return_value=httpx.Response(200, json=fixture("state_rest_missing_actions")))

    result = runner.invoke(app, ["debug", "recover-rest", "--base-url", BASE_URL, "--dry-run"])

    assert result.exit_code == 0
    payload = yaml.safe_load(result.stdout)
    assert payload["recovery"] == "rest_relic_refresh_click"
    assert payload["before"]["screen"] == "REST"
    assert payload["before"]["available_actions"] == []
    assert payload["before"]["has_recovery_options"] is True
    assert payload["click"]["screen_point"] == {"x": 101, "y": 202}
    assert click_calls[0]["args"] == (0.03, 0.333)
    assert click_calls[0]["kwargs"]["normalized"] is True
    assert click_calls[0]["kwargs"]["dry_run"] is True
    assert payload["escape"]["dry_run"] is True


@respx.mock
def test_cli_debug_recover_rest_allows_potion_only_rest_state(monkeypatch) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    import sts2_bridge.macos_screenshot as macos_screenshot

    monkeypatch.setattr(
        macos_screenshot,
        "click_window",
        lambda *args, **kwargs: {"clicked": False, "dry_run": True, "screen_point": {"x": 101, "y": 202}},
    )
    monkeypatch.setattr(macos_screenshot, "press_key", lambda *args, **kwargs: {"pressed": False, "dry_run": True})
    respx.get(f"{BASE_URL}/state").mock(return_value=httpx.Response(200, json=fixture("state_rest_potion_only")))

    result = runner.invoke(app, ["debug", "recover-rest", "--base-url", BASE_URL, "--dry-run"])

    assert result.exit_code == 0
    payload = yaml.safe_load(result.stdout)
    assert payload["before"]["available_actions"] == ["discard_potion"]
    assert payload["before"]["has_recovery_options"] is True


@respx.mock
def test_cli_debug_recover_rest_reports_unchanged_state(monkeypatch) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    import sts2_bridge.macos_screenshot as macos_screenshot

    monkeypatch.setattr(
        macos_screenshot,
        "click_window",
        lambda *args, **kwargs: {"clicked": True, "dry_run": False, "screen_point": {"x": 101, "y": 202}},
    )
    monkeypatch.setattr(macos_screenshot, "press_key", lambda *args, **kwargs: {"pressed": True, "dry_run": False})
    respx.get(f"{BASE_URL}/state").mock(return_value=httpx.Response(200, json=fixture("state_rest_potion_only")))

    result = runner.invoke(app, ["debug", "recover-rest", "--base-url", BASE_URL])

    assert result.exit_code == 0
    payload = yaml.safe_load(result.stdout)
    assert payload["status"] == "unchanged"
    assert payload["after"]["has_recovery_options"] is True
    assert payload["escape"]["pressed"] is True
    assert payload["suggestions"]


@respx.mock
def test_cli_debug_recover_rest_supports_target_presets(monkeypatch) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    import sts2_bridge.macos_screenshot as macos_screenshot

    click_calls: list[dict] = []

    def fake_click_window(*args, **kwargs):
        click_calls.append({"args": args, "kwargs": kwargs})
        return {"clicked": False, "dry_run": True, "screen_point": {"x": 101, "y": 202}}

    monkeypatch.setattr(macos_screenshot, "click_window", fake_click_window)
    monkeypatch.setattr(macos_screenshot, "press_key", lambda *args, **kwargs: {"pressed": False, "dry_run": True})
    respx.get(f"{BASE_URL}/state").mock(return_value=httpx.Response(200, json=fixture("state_rest_potion_only")))

    result = runner.invoke(app, ["debug", "recover-rest", "--base-url", BASE_URL, "--dry-run", "--target", "rest-card"])

    assert result.exit_code == 0
    assert click_calls[0]["args"] == (0.41, 0.43)


def test_interactive_digit_chooses_map_option() -> None:
    state = GameState.model_validate(sample("state/*_map.json")["data"])
    view = filter_state(state)

    assert _interactive_action_from_input("2", state, view) == ("choose_map_node", {"option_index": 2})


def test_interactive_digit_plays_combat_card_with_default_target() -> None:
    state = GameState.model_validate(fixture("state_combat")["data"])
    view = filter_state(state)

    assert _interactive_action_from_input("0", state, view) == ("play_card", {"card_index": 0, "target_index": 0})


def test_interactive_reward_digit_claims_reward_option() -> None:
    state = GameState.model_validate({"screen": "REWARD", "available_actions": ["claim_reward"]})

    assert _interactive_action_from_input("1", state, {}) == ("claim_reward", {"option_index": 1})


def test_interactive_digit_selects_card_selection_option() -> None:
    state = GameState.model_validate(fixture("state_card_selection")["data"])

    assert _interactive_action_from_input("1", state, {}) == ("select_deck_card", {"option_index": 1})


def test_interactive_digit_selects_rest_option() -> None:
    state = GameState.model_validate(fixture("state_rest_missing_actions")["data"])

    with pytest.raises(BridgeError):
        _interactive_action_from_input("1", state, {})


def _read_log_records(root: Path, category: str) -> list[dict]:
    files = sorted((root / category).glob("*.jsonl"))
    assert files
    return [json.loads(line) for file in files for line in file.read_text(encoding="utf-8").splitlines()]
