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


@respx.mock
def test_cli_state_defaults_to_text_view() -> None:
    respx.get(f"{BASE_URL}/state").mock(return_value=httpx.Response(200, json=fixture("state_combat")))

    result = runner.invoke(app, ["state", "--base-url", BASE_URL])

    assert result.exit_code == 0
    assert result.stdout.startswith("COMBAT turn=2")
    assert "Player: HP 63/75, Block 4, Energy 3, Stars 1" in result.stdout
    assert "Player powers: Strength 2" in result.stdout
    assert "Incoming attack damage: 6" in result.stdout
    assert "[0] Ring of the Snake: At the start of each combat, draw 2 additional cards." in result.stdout
    assert "[0] Cultist: HP 24/48, Block 0, Intents attack 6, Powers none" in result.stdout
    assert "[0] Strike | Basic Attack | cost 1 | playable | target enemy[0] | Deal 8 damage." in result.stdout
    assert "Piles:" in result.stdout
    assert "Draw: 5 card(s)" in result.stdout
    assert "Deck: Strike, Defend" in result.stdout
    assert "- Block: Block prevents attack damage." in result.stdout
    assert "[0] play_card(card_index, target_index=0)" in result.stdout
    assert "[1] end_turn" in result.stdout


@respx.mock
def test_cli_state_filtered_layer_outputs_text() -> None:
    respx.get(f"{BASE_URL}/state").mock(return_value=httpx.Response(200, json=fixture("state_combat")))

    result = runner.invoke(app, ["state", "--layer", "filtered", "--base-url", BASE_URL])

    assert result.exit_code == 0
    assert not result.stdout.lstrip().startswith("{")
    payload = yaml.safe_load(result.stdout)
    assert payload["screen"] == "COMBAT"
    assert payload["combat"]["playable"][0]["card_name"] == "Strike"
    assert payload["combat"]["playable"][0]["rarity"] == "Basic"
    assert payload["combat"]["playable"][0]["card_type"] == "Attack"
    assert payload["combat"]["playable"][0]["resolved_rules_text"] == "Deal 8 damage."
    assert payload["relics"][0]["name"] == "Ring of the Snake"
    assert payload["glossary"]["Block"] == "Block prevents attack damage."


@respx.mock
def test_cli_state_renders_compact_map_view() -> None:
    respx.get(f"{BASE_URL}/state").mock(return_value=httpx.Response(200, json=sample("state/*_map.json")))

    result = runner.invoke(app, ["state", "--base-url", BASE_URL])

    assert result.exit_code == 0
    assert result.stdout.startswith("MAP floor=1 gold=99")
    assert "Current: r0c3" in result.stdout
    assert "[0] M r1c0" in result.stdout
    assert "Reachable map:" in result.stdout
    assert "r8: c1E, c3E, c4M, c5M, c6E" in result.stdout
    assert "Legal actions:\n[0] choose_map_node(option_index=0)" in result.stdout
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
    assert "[0] 轰鸣海螺 | 在精英战的战斗开始时，额外抽2张牌。 | relic preview" in result.stdout
    assert "[1] 金色珍珠 | 拾起时，获得150金币。 | relic preview" in result.stdout
    assert "[2] 沉重石板 | 从3张稀有牌中选择1张加入你的牌组。将1张受伤加入你的牌组。 | relic preview" in result.stdout
    assert "Legal actions:\n[0] choose_event_option(option_index=0)" in result.stdout


@respx.mock
def test_cli_state_renders_open_shop_inventory() -> None:
    respx.get(f"{BASE_URL}/state").mock(return_value=httpx.Response(200, json=fixture("state_shop_open")))

    result = runner.invoke(app, ["state", "--base-url", BASE_URL])

    assert result.exit_code == 0
    assert result.stdout.startswith("SHOP floor=22 gold=194")
    assert "Shop: open" in result.stdout
    assert "Card removal: 75g affordable" in result.stdout
    assert "[0] 翻越撑击 | Common Attack | cost 1 | 52g affordable | 奇巧。 对所有敌人造成6点伤害。 | character" in result.stdout
    assert "[1] 开心小花 | Rare Power | cost 0 | 158g affordable" in result.stdout
    assert "0g sale unaffordable" not in result.stdout
    assert "[0] 怀表 | Rare | 304g unaffordable" in result.stdout
    assert "[0] 火焰药水 | Common | CombatOnly | 48g affordable" in result.stdout
    assert "Legal actions:\n[0] close_shop_inventory\n[1] buy_card(option_index=0)" in result.stdout


@respx.mock
def test_cli_state_renders_card_selection_options() -> None:
    respx.get(f"{BASE_URL}/state").mock(return_value=httpx.Response(200, json=fixture("state_card_selection")))

    result = runner.invoke(app, ["state", "--base-url", BASE_URL])

    assert result.exit_code == 0
    assert result.stdout.startswith("CARD_SELECTION turn=3 floor=5 gold=88")
    assert "Prompt: 选择1张牌保留。" in result.stdout
    assert "Selection: combat_hand_select | select 1-1 | selected 0 | requires confirm" in result.stdout
    assert "[0] Strike | Basic Attack | cost 1 | Deal 6 damage." in result.stdout
    assert "[1] Defend | Basic Skill | cost 1 | Gain 5 Block. | keywords Block" in result.stdout
    assert "Legal actions:\n[0] select_deck_card(option_index=0)\n[1] confirm_selection" in result.stdout


@respx.mock
def test_cli_state_renders_rest_fallback_options() -> None:
    respx.get(f"{BASE_URL}/state").mock(return_value=httpx.Response(200, json=fixture("state_rest_missing_actions")))

    result = runner.invoke(app, ["state", "--base-url", BASE_URL])

    assert result.exit_code == 0
    assert result.stdout.startswith("REST floor=11 gold=147")
    assert "Recovery options:" in result.stdout
    assert "[0] Rest | Heal at the rest site. | recovery: API did not expose executable rest actions" in result.stdout
    assert "[1] Smith | Upgrade one card. | recovery: API did not expose executable rest actions" in result.stdout
    assert "Recovery command: sts2 debug recover-rest" in result.stdout
    assert "Legal actions:" not in result.stdout


@respx.mock
def test_cli_wait_returns_rest_recovery_state_when_api_omits_actions() -> None:
    respx.get(f"{BASE_URL}/state").mock(return_value=httpx.Response(200, json=fixture("state_rest_missing_actions")))

    result = runner.invoke(app, ["wait", "--base-url", BASE_URL, "--timeout", "0.01"])

    assert result.exit_code == 0
    assert "Recovery options:" in result.stdout
    assert "Legal actions:" not in result.stdout


@respx.mock
def test_cli_state_does_not_render_rest_fallback_options_after_choice() -> None:
    respx.get(f"{BASE_URL}/state").mock(return_value=httpx.Response(200, json=fixture("state_rest_proceed")))

    result = runner.invoke(app, ["state", "--base-url", BASE_URL])

    assert result.exit_code == 0
    assert "Options:" not in result.stdout
    assert result.stdout.rstrip().endswith("Legal actions:\n[0] proceed")


@respx.mock
def test_cli_state_renders_rest_recovery_when_only_potion_action_exists() -> None:
    respx.get(f"{BASE_URL}/state").mock(return_value=httpx.Response(200, json=fixture("state_rest_potion_only")))

    result = runner.invoke(app, ["state", "--base-url", BASE_URL])

    assert result.exit_code == 0
    assert "Recovery options:" in result.stdout
    assert "Legal actions:\n[0] discard_potion(option_index=0)" in result.stdout


@respx.mock
def test_cli_state_renders_reward_rows_and_unloaded_card_note() -> None:
    respx.get(f"{BASE_URL}/state").mock(return_value=httpx.Response(200, json=fixture("state_reward_rows")))

    result = runner.invoke(app, ["state", "--base-url", BASE_URL])

    assert result.exit_code == 0
    assert result.stdout.startswith("REWARD floor=14 gold=22")
    assert "Reward: pending_card_choice=false, can_proceed=true" in result.stdout
    assert "[0] Gold: 17金币 | claimable" in result.stdout
    assert "[1] Card: 将一张牌添加到你的牌组。 | claimable" in result.stdout
    assert "Card choices: not loaded" in result.stdout
    assert "claim the Card reward first" in result.stdout
    assert "[0] resolve_rewards(may skip unresolved card reward)" in result.stdout
    assert "[2] claim_reward(option_index=0)" in result.stdout


@respx.mock
def test_cli_state_renders_reward_card_choices() -> None:
    respx.get(f"{BASE_URL}/state").mock(return_value=httpx.Response(200, json=fixture("state_reward_cards")))

    result = runner.invoke(app, ["state", "--base-url", BASE_URL])

    assert result.exit_code == 0
    assert "Reward: pending_card_choice=true, can_proceed=false" in result.stdout
    assert "Card choices:" in result.stdout
    assert "[0] 精准 | Uncommon Power | cost 1 | 小刀额外造成4点伤害。" in result.stdout
    assert "[1] 投掷匕首 | Common Attack | cost 1 | 造成9点伤害。 抽1张牌。 丢弃一张牌。" in result.stdout
    assert "Alternatives:\n[0] 跳过" in result.stdout
    assert "[0] choose_reward_card(option_index=0)" in result.stdout
    assert "[1] skip_reward_cards" in result.stdout


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
    assert "Changes:" in result.stdout
    assert "[0] end_turn" in result.stdout


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
def test_cli_act_reports_rest_recovery_after_rest_desync() -> None:
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
    assert "REST recovery:" in result.stdout
    assert "Next: sts2 debug recover-rest" in result.stdout


@respx.mock
def test_cli_act_refreshes_state_instead_of_using_stale_action_state() -> None:
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
    assert "[1] Blade Dance" in result.stdout
    assert "[2] Blade Dance" not in result.stdout


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

    assert result.exit_code == 0
    assert result.stdout == "Legal actions:\n[0] choose_map_node(option_index=0)\n"


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

    assert result.exit_code == 0
    assert "[0] buy_card(option_index=0)" in result.stdout
    assert "[1] buy_potion(option_index=0)" in result.stdout
    assert "[2] use_potion(option_index=0, optional target_index)" in result.stdout


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
