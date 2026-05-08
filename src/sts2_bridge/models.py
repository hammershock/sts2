from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class BridgeError(RuntimeError):
    """Error that can be rendered as a stable JSON payload."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        details: dict[str, Any] | None = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}
        self.retryable = retryable

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": False,
            "error": {
                "code": self.code,
                "message": self.message,
                "details": self.details,
                "retryable": self.retryable,
            },
        }


class ApiError(BaseModel):
    model_config = ConfigDict(extra="allow")

    code: str = "api_error"
    message: str = "API request failed."
    details: dict[str, Any] | None = None
    retryable: bool = False


class ApiEnvelope(BaseModel):
    model_config = ConfigDict(extra="allow")

    ok: bool
    request_id: str | None = None
    data: Any = None
    error: ApiError | None = None


class Power(BaseModel):
    model_config = ConfigDict(extra="allow")

    index: int | None = None
    power_id: str | None = None
    name: str | None = None
    amount: int | None = None
    is_debuff: bool | None = None


class Card(BaseModel):
    model_config = ConfigDict(extra="allow")

    index: int | None = None
    card_id: str | None = None
    name: str | None = None
    upgraded: bool | None = None
    target_type: str | None = None
    requires_target: bool | None = None
    costs_x: bool | None = None
    star_costs_x: bool | None = None
    energy_cost: int | None = None
    star_cost: int | None = None
    rules_text: str | None = None
    resolved_rules_text: str | None = None
    playable: bool | None = None
    unplayable_reason: str | None = None


class Intent(BaseModel):
    model_config = ConfigDict(extra="allow")

    type: str | None = None
    damage: int | None = None
    hits: int | None = None
    amount: int | None = None
    description: str | None = None


class Enemy(BaseModel):
    model_config = ConfigDict(extra="allow")

    index: int | None = None
    enemy_id: str | None = None
    name: str | None = None
    current_hp: int | None = None
    max_hp: int | None = None
    block: int | None = None
    is_alive: bool | None = None
    is_hittable: bool | None = None
    powers: list[Power] = Field(default_factory=list)
    intent: str | None = None
    move_id: str | None = None
    intents: list[Intent] = Field(default_factory=list)


class Player(BaseModel):
    model_config = ConfigDict(extra="allow")

    current_hp: int | None = None
    max_hp: int | None = None
    block: int | None = None
    energy: int | None = None
    stars: int | None = None
    powers: list[Power] = Field(default_factory=list)


class CombatState(BaseModel):
    model_config = ConfigDict(extra="allow")

    player: Player | None = None
    hand: list[Card] = Field(default_factory=list)
    enemies: list[Enemy] = Field(default_factory=list)
    draw_pile_count: int | None = None
    discard_pile_count: int | None = None
    exhaust_pile_count: int | None = None


class GameState(BaseModel):
    model_config = ConfigDict(extra="allow")

    state_version: int | None = None
    run_id: str | None = None
    screen: str = "UNKNOWN"
    in_combat: bool = False
    turn: int | None = None
    available_actions: list[str] = Field(default_factory=list)
    combat: CombatState | None = None
    run: dict[str, Any] | None = None
    map: dict[str, Any] | None = None
    reward: dict[str, Any] | None = None
    selection: dict[str, Any] | None = None
    chest: dict[str, Any] | None = None
    event: dict[str, Any] | None = None
    shop: dict[str, Any] | None = None
    rest: dict[str, Any] | None = None
    character_select: dict[str, Any] | None = None
    modal: dict[str, Any] | None = None
    game_over: dict[str, Any] | None = None


class ActionResult(BaseModel):
    model_config = ConfigDict(extra="allow")

    status: str | None = None
    state: GameState | None = None
