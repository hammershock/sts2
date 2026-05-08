import json
from pathlib import Path

import httpx
import pytest
import respx

from sts2_bridge.client import Sts2Client
from sts2_bridge.models import BridgeError

BASE_URL = "http://test.local"


def fixture(name: str) -> dict:
    return json.loads(Path(f"tests/fixtures/{name}.json").read_text())


@respx.mock
def test_health_returns_envelope_data() -> None:
    respx.get(f"{BASE_URL}/health").mock(return_value=httpx.Response(200, json=fixture("health")))

    data = Sts2Client(BASE_URL).health()

    assert data["status"] == "ready"


@respx.mock
def test_state_parses_combat_payload() -> None:
    respx.get(f"{BASE_URL}/state").mock(return_value=httpx.Response(200, json=fixture("state_combat")))

    state = Sts2Client(BASE_URL).state()

    assert state.screen == "COMBAT"
    assert state.combat is not None
    assert state.combat.hand[0].name == "Strike"


@respx.mock
def test_act_posts_generic_action_payload(isolated_logs) -> None:
    route = respx.post(f"{BASE_URL}/action").mock(
        return_value=httpx.Response(200, json={"ok": True, "data": {"status": "completed"}})
    )

    result = Sts2Client(BASE_URL).act("play_card", {"card_index": 0, "target_index": 1})

    assert result.status == "completed"
    assert route.calls.last is not None
    assert json.loads(route.calls.last.request.content) == {"action": "play_card", "card_index": 0, "target_index": 1}
    records = _read_log_records(isolated_logs, "http")
    assert records[-1]["request"]["method"] == "POST"
    assert records[-1]["request"]["url"] == f"{BASE_URL}/action"
    assert records[-1]["request"]["body"] == {"action": "play_card", "card_index": 0, "target_index": 1}
    assert records[-1]["response"]["status_code"] == 200
    assert '"status":"completed"' in records[-1]["response"]["text"].replace(" ", "")


@respx.mock
def test_api_error_raises_bridge_error() -> None:
    respx.get(f"{BASE_URL}/state").mock(
        return_value=httpx.Response(
            503,
            json={
                "ok": False,
                "error": {
                    "code": "state_unavailable",
                    "message": "transitioning",
                    "details": {"screen": "UNKNOWN"},
                    "retryable": True,
                },
            },
        )
    )

    with pytest.raises(BridgeError) as exc_info:
        Sts2Client(BASE_URL).state()

    assert exc_info.value.code == "state_unavailable"
    assert exc_info.value.retryable is True


def _read_log_records(root: Path, category: str) -> list[dict]:
    files = sorted((root / category).glob("*.jsonl"))
    assert files
    return [json.loads(line) for file in files for line in file.read_text(encoding="utf-8").splitlines()]
