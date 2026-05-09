from __future__ import annotations

from collections.abc import Mapping
import time
from typing import Any

import httpx
from pydantic import ValidationError

from sts2_bridge.models import ActionResult, ApiEnvelope, BridgeError, GameState
from sts2_bridge.trace import log_http_request, _now_iso

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

    def state_response(self) -> dict[str, Any]:
        payload = self._request_json("GET", "/state")
        self._raise_api_error(payload)
        if not isinstance(payload, dict):
            raise BridgeError(
                "invalid_state_response",
                "Mod API returned a non-object state payload.",
                details={"payload_type": type(payload).__name__},
                retryable=False,
            )
        return payload

    def state(self) -> GameState:
        data = _response_data(self.state_response())
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

    def action_response(self, action: str, args: Mapping[str, Any] | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {"action": action}
        if args:
            payload.update(dict(args))
        data = self._request_json("POST", "/action", json=payload)
        if not isinstance(data, dict):
            raise BridgeError(
                "invalid_action_response",
                "Mod API returned a non-object action payload.",
                details={"action": action, "payload_type": type(data).__name__},
                retryable=False,
            )
        return data

    def _get_data(self, path: str) -> Any:
        return self._request_data("GET", path)

    def _request_data(self, method: str, path: str, **kwargs: Any) -> Any:
        payload = self._request_json(method, path, **kwargs)
        self._raise_api_error(payload)
        if isinstance(payload, dict) and "ok" in payload:
            envelope = ApiEnvelope.model_validate(payload)
            if envelope.ok:
                return envelope.data
        return payload

    def _request_json(self, method: str, path: str, **kwargs: Any) -> Any:
        url = f"{self.base_url}{path}"
        started_at = _now_iso()
        started_monotonic = time.monotonic()
        response: httpx.Response | None = None
        try:
            with httpx.Client(timeout=self.timeout, trust_env=self.trust_env) as client:
                response = client.request(method, url, **kwargs)
        except httpx.ConnectError as exc:
            log_http_request(
                method=method,
                url=url,
                request_kwargs=kwargs,
                started_at=started_at,
                started_monotonic=started_monotonic,
                error=exc,
            )
            raise BridgeError(
                "connection_failed",
                "Cannot connect to the STS2 Mod API. Confirm the game is running and the Mod is loaded.",
                details={"base_url": self.base_url},
                retryable=True,
            ) from exc
        except httpx.TimeoutException as exc:
            log_http_request(
                method=method,
                url=url,
                request_kwargs=kwargs,
                started_at=started_at,
                started_monotonic=started_monotonic,
                error=exc,
            )
            raise BridgeError(
                "timeout",
                "Timed out while waiting for the STS2 Mod API.",
                details={"base_url": self.base_url, "timeout": self.timeout},
                retryable=True,
            ) from exc
        except httpx.HTTPError as exc:
            log_http_request(
                method=method,
                url=url,
                request_kwargs=kwargs,
                started_at=started_at,
                started_monotonic=started_monotonic,
                error=exc,
            )
            raise BridgeError(
                "http_error",
                str(exc),
                details={"base_url": self.base_url},
                retryable=True,
            ) from exc
        log_http_request(
            method=method,
            url=url,
            request_kwargs=kwargs,
            started_at=started_at,
            started_monotonic=started_monotonic,
            response=response,
        )

        try:
            payload = response.json()
        except ValueError as exc:
            raise BridgeError(
                "invalid_json",
                "Mod API returned a non-JSON response.",
                details={"status_code": response.status_code, "text": response.text[:500]},
                retryable=False,
            ) from exc

        if isinstance(payload, dict) and payload.get("ok") is False:
            return payload

        if response.is_error:
            raise BridgeError(
                "http_status_error",
                "Mod API returned an HTTP error.",
                details={"status_code": response.status_code, "payload": payload},
                retryable=response.status_code >= 500,
            )

        return payload

    def _raise_api_error(self, payload: Any) -> None:
        if not isinstance(payload, dict) or "ok" not in payload:
            return
        envelope = ApiEnvelope.model_validate(payload)
        if envelope.ok:
            return
        error = envelope.error
        raise BridgeError(
            error.code if error else "api_error",
            error.message if error else "Mod API returned ok=false.",
            details=(error.details or {} if error else {"payload": payload}),
            retryable=(error.retryable if error else False),
        )


def _response_data(payload: Any) -> Any:
    if isinstance(payload, dict) and isinstance(payload.get("data"), dict):
        return payload["data"]
    return payload
