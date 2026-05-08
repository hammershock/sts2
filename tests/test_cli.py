import json
from pathlib import Path

import httpx
import respx
from typer.testing import CliRunner

from sts2_bridge.cli import app

BASE_URL = "http://test.local"
runner = CliRunner()


def fixture(name: str) -> dict:
    return json.loads(Path(f"tests/fixtures/{name}.json").read_text())


@respx.mock
def test_cli_health_outputs_json() -> None:
    respx.get(f"{BASE_URL}/health").mock(
        return_value=httpx.Response(200, json={"ok": True, "data": {"status": "ready"}})
    )

    result = runner.invoke(app, ["health", "--base-url", BASE_URL])

    assert result.exit_code == 0
    assert json.loads(result.stdout) == {"ok": True, "data": {"status": "ready"}}


@respx.mock
def test_cli_state_defaults_to_text_view() -> None:
    respx.get(f"{BASE_URL}/state").mock(return_value=httpx.Response(200, json=fixture("state_combat")))

    result = runner.invoke(app, ["state", "--base-url", BASE_URL])

    assert result.exit_code == 0
    assert result.stdout.startswith("COMBAT turn=2")
    assert "Player: HP 63/75" in result.stdout
    assert "[0] Strike | cost 1 | playable | damage 8 | target enemy[0]" in result.stdout


@respx.mock
def test_cli_state_filtered_layer_outputs_json() -> None:
    respx.get(f"{BASE_URL}/state").mock(return_value=httpx.Response(200, json=fixture("state_combat")))

    result = runner.invoke(app, ["state", "--layer", "filtered", "--base-url", BASE_URL])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["data"]["screen"] == "COMBAT"
    assert payload["data"]["combat"]["playable"][0]["card_name"] == "Strike"


@respx.mock
def test_cli_act_parses_repeated_args() -> None:
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
            "play_card",
            "--arg",
            "card_index=0",
            "--arg",
            "target_index=1",
            "--base-url",
            BASE_URL,
        ],
    )

    assert result.exit_code == 0
    assert json.loads(route.calls.last.request.content) == {"action": "play_card", "card_index": 0, "target_index": 1}
    assert json.loads(result.stdout)["data"]["state"]["available_actions"] == ["end_turn"]
    assert "changes" in json.loads(result.stdout)["data"]


def test_cli_rejects_invalid_arg_shape() -> None:
    result = runner.invoke(app, ["act", "play_card", "--arg", "card_index"])

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["error"]["code"] == "invalid_cli_arg"


def test_cli_policy_commands_are_not_registered() -> None:
    suggest_result = runner.invoke(app, ["suggest"])
    step_result = runner.invoke(app, ["step"])

    assert suggest_result.exit_code == 2
    assert step_result.exit_code == 2
