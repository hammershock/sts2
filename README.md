# STS2 Bridge

`sts2-bridge` is a JSON-first CLI bridge for agents that play Slay the Spire 2 through a localhost Mod API.

The first backend targets the STS2-Agent style HTTP API:

- `GET /health`
- `GET /state`
- `POST /action`

The default base URL is `http://127.0.0.1:8080`. Override it with `--base-url` or `STS2_API_BASE_URL`.

## Install

```bash
uv sync --extra dev
```

Or install into the active Python environment:

```bash
python -m pip install -e ".[dev]"
```

## CLI

```bash
sts2 health
sts2 state --pretty
sts2 state --view decision --pretty
sts2 state --view agent --pretty
sts2 actions --pretty
sts2 combat --pretty
sts2 act play_card --arg card_index=0 --arg target_index=1 --pretty
sts2 act play_card --arg card_index=0 --arg target_index=1 --raw-result --pretty
sts2 wait --timeout 30 --pretty
sts2 state --with-window --pretty
sts2 window-status --pretty
sts2 windows --pretty
sts2 screenshot --pretty
sts2 screenshot --activate-fallback --pretty
```

All commands emit JSON by default so that agents can parse them reliably.

`sts2 state` defaults to a schema-filtered view, which is intended to keep token use low. Use `--view decision` when an agent needs the compact decision packet, `--view combat` for tactical combat state, `--view agent` for the older broad compact view, and `--raw` only when debugging parser coverage.

`sts2 act` defaults to a filtered action result: status, action args, a compact post-action state, and changed fields when a before/after state is available. Use `--raw-result` to inspect the full parsed action result.

Filtering rules live in YAML files under `src/sts2_bridge/schemas/`, split by `state/` and `action/`. Real raw HTTP samples live under `samples/http/` and are used as regression fixtures for the filtering layer.

## Screenshot Fallback

`sts2 state --with-window` and `sts2 window-status` report whether the game process/window exists and whether Slay the Spire 2 is currently the frontmost app.

`sts2 screenshot` is a macOS-only debug fallback for visual inspection. When the game is frontmost, it uses ScreenCaptureKit single-window capture. When the game is not frontmost, it will not use rectangle capture by default because that would capture whatever is covering the game. macOS must grant Screen Recording permission to the terminal app that runs the command.

For Godot/Metal windows, macOS may refuse true background window capture. Use `--activate-fallback` as the final fallback: it briefly brings the game to the foreground for rectangle capture, then tries to restore the previous foreground app.
