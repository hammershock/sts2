# STS2 Bridge

`sts2-bridge` is a layered CLI bridge for agents that play Slay the Spire 2 through a localhost Mod API.

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
sts2 state
sts2 state --layer filtered --pretty
sts2 state --layer raw --pretty
sts2 state --view decision --layer filtered --pretty
sts2 actions --pretty
sts2 combat --pretty
sts2 act play_card 0
sts2 act play_card 0 0
sts2 act playcard --card_index 0
sts2 act 1 --card_index 0
sts2 act play_card --card_index 0 --target_index 0
sts2 wait --timeout 30 --pretty
sts2 state --with-window --pretty
sts2 window-status --pretty
sts2 windows --pretty
sts2 screenshot --pretty
sts2 screenshot --activate-fallback --pretty
```

State output has three layers:

- `view`: default human-readable text for Agent input.
- `filtered`: YAML schema-filtered JSON for debugging and downstream tooling.
- `raw`: full parsed HTTP state for parser/debug work.

`sts2 state` defaults to the text `view` layer. Use `--layer filtered` for schema-filtered JSON and `--layer raw` or `--raw` for the full parsed payload. Use `--view decision`, `--view combat`, or `--view agent` to select richer filtered state before rendering or JSON output. Use `--format json` if a caller wants the selected view layer wrapped as JSON.

`sts2 act` defaults to a filtered action result: status, action args, a compact post-action state, and changed fields when a before/after state is available. Use `--raw-result` to inspect the full parsed action result.

Action names can be written canonically or as aliases without separators, such as `play_card` or `playcard`. The first action argument can also be the numbered action from the current `Legal actions` list, for example `sts2 act 1 --card_index 0` when `[1] play_card(...)` is shown. Action parameters can be passed positionally or by keyword, such as `sts2 act play_card 0 0`, `sts2 act play_card 0 --target_index 0`, or `sts2 act play_card --card_index 0 --target_index 0`.

Filtering rules live in YAML files under `src/sts2_bridge/schemas/`, split by `state/` and `action/`. Real raw HTTP samples live under `samples/http/` and are used as regression fixtures for the filtering layer.

## Screenshot Fallback

`sts2 state --with-window` and `sts2 window-status` report whether the game process/window exists and whether Slay the Spire 2 is currently the frontmost app.

`sts2 screenshot` is a macOS-only debug fallback for visual inspection. When the game is frontmost, it uses ScreenCaptureKit single-window capture. When the game is not frontmost, it will not use rectangle capture by default because that would capture whatever is covering the game. macOS must grant Screen Recording permission to the terminal app that runs the command.

For Godot/Metal windows, macOS may refuse true background window capture. Use `--activate-fallback` as the final fallback: it briefly brings the game to the foreground for rectangle capture, then tries to restore the previous foreground app.
