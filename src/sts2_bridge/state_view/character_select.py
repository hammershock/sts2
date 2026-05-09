from __future__ import annotations

from dataclasses import dataclass

from sts2_bridge.state_view.common import RenderConfig, actions, finish, header, section
from sts2_bridge.state_view.model import ViewContext, indexed_line


@dataclass(frozen=True)
class CharacterSelectConfig(RenderConfig):
    show_glossary: bool = False


def render(ctx: ViewContext, config: CharacterSelectConfig = CharacterSelectConfig()) -> str:
    agent = ctx.agent.get("character_select") if isinstance(ctx.agent.get("character_select"), dict) else {}
    raw = ctx.data.get("character_select") if isinstance(ctx.data.get("character_select"), dict) else {}
    lines = [header(ctx), _summary(agent, raw)]
    characters = _characters(agent, raw)
    if characters:
        lines += section("Characters", [_character_line(character, index) for index, character in enumerate(characters)])
    players = raw.get("players") if isinstance(raw, dict) else []
    if isinstance(players, list) and players:
        lines += section("Players", [_player_line(player, index) for index, player in enumerate(players) if isinstance(player, dict)])
    if config.show_actions:
        lines += section("Legal actions", actions(ctx))
    return finish(lines)


def _summary(agent: dict[str, object], raw: dict[str, object]) -> str:
    selected = agent.get("selected") or raw.get("selected_character_id") or "?"
    embark = agent.get("embark", raw.get("can_embark"))
    ascension = agent.get("ascension", raw.get("ascension"))
    players = raw.get("player_count")
    max_players = raw.get("max_players")
    parts = [f"Selected: {selected}", f"Embark: {str(embark).lower()}", f"Ascension: {ascension}"]
    if players is not None or max_players is not None:
        parts.append(f"Players: {players}/{max_players}")
    return " | ".join(parts)


def _characters(agent: dict[str, object], raw: dict[str, object]) -> list[object]:
    characters = agent.get("characters")
    if isinstance(characters, list) and characters:
        return characters
    raw_characters = raw.get("characters")
    return raw_characters if isinstance(raw_characters, list) else []


def _character_line(character: object, index: int) -> str:
    if not isinstance(character, dict):
        return str(character)
    tags = []
    if character.get("selected") or character.get("is_selected"):
        tags.append("selected")
    if character.get("locked") or character.get("is_locked"):
        tags.append("locked")
    if character.get("is_random"):
        tags.append("random")
    suffix = f" | {', '.join(tags)}" if tags else ""
    return f"{indexed_line(character, index)}{suffix}"


def _player_line(player: dict[str, object], index: int) -> str:
    slot = player.get("slot_index", index)
    name = player.get("character_name") or player.get("character_id") or "Player"
    ready = player.get("is_ready")
    local = "local" if player.get("is_local") else "remote"
    return f"[{slot}] {name} | {local} | ready {str(ready).lower()}"
