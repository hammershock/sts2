from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import httpx
from pydantic import ValidationError

from sts2_bridge.models import ActionResult, ApiEnvelope, BridgeError, GameState

DEFAULT_BASE_URL = "http://127.0.0.1:8080"


class Sts2Client:
    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        *,
        timeout: float = 10.0,
        trust_env: bool = False,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.trust_env = trust_env

    def health(self) -> dict[str, Any]:
        return self._get_data("/health")

    def state(self) -> GameState:
        data = self._get_data("/state")
        try:
            return GameState.model_validate(data)
        except ValidationError as exc:
            raise BridgeError(
                "invalid_state",
                "Mod API returned a state payload that this CLI cannot parse.",
                details={"errors": exc.errors()},
                retryable=False,
            ) from exc

    def act(self, action: str, args: Mapping[str, Any] | None = None) -> ActionResult:
        payload: dict[str, Any] = {"action": action}
        if args:
            payload.update(dict(args))
        data = self._request_data("POST", "/action", json=payload)
        if isinstance(data, dict):
            try:
                return ActionResult.model_validate(data)
            except ValidationError:
                state_data = data.get("state")
                if isinstance(state_data, dict):
                    return ActionResult(status=data.get("status"), state=GameState.model_validate(state_data))
        return ActionResult(status="completed")

    def _get_data(self, path: str) -> Any:
        return self._request_data("GET", path)

    def _request_data(self, method: str, path: str, **kwargs: Any) -> Any:
        url = f"{self.base_url}{path}"
        try:
            with httpx.Client(timeout=self.timeout, trust_env=self.trust_env) as client:
                response = client.request(method, url, **kwargs)
        except httpx.ConnectError as exc:
            raise BridgeError(
                "connection_failed",
                "Cannot connect to the STS2 Mod API. Confirm the game is running and the Mod is loaded.",
                details={"base_url": self.base_url},
                retryable=True,
            ) from exc
        except httpx.TimeoutException as exc:
            raise BridgeError(
                "timeout",
                "Timed out while waiting for the STS2 Mod API.",
                details={"base_url": self.base_url, "timeout": self.timeout},
                retryable=True,
            ) from exc
        except httpx.HTTPError as exc:
            raise BridgeError(
                "http_error",
                str(exc),
                details={"base_url": self.base_url},
                retryable=True,
            ) from exc

        try:
            payload = response.json()
        except ValueError as exc:
            raise BridgeError(
                "invalid_json",
                "Mod API returned a non-JSON response.",
                details={"status_code": response.status_code, "text": response.text[:500]},
                retryable=False,
            ) from exc

        if isinstance(payload, dict) and "ok" in payload:
            envelope = ApiEnvelope.model_validate(payload)
            if envelope.ok:
                return envelope.data
            error = envelope.error
            raise BridgeError(
                error.code if error else "api_error",
                error.message if error else "Mod API returned ok=false.",
                details=(error.details or {} if error else {"payload": payload}),
                retryable=(error.retryable if error else False),
            )

        if response.is_error:
            raise BridgeError(
                "http_status_error",
                "Mod API returned an HTTP error.",
                details={"status_code": response.status_code, "payload": payload},
                retryable=response.status_code >= 500,
            )

        return payload
