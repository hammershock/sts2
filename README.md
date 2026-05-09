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
sts2
sts2 state
sts2 state --raw
sts2 act play_card 0
sts2 act play_card 0 0
sts2 act playcard --card_index 0
sts2 act 1 --card_index 0
sts2 act play_card --card_index 0 --target_index 0
sts2 wait --timeout 30
sts2 debug health
sts2 debug route-render-samples
sts2 debug window-status
sts2 debug windows
sts2 debug click-window 0.5 0.4 --normalized --dry-run
sts2 debug recover-rest --dry-run
sts2 screenshot
sts2 screenshot --activate-fallback
```

Running `sts2` with no subcommand starts an interactive TTY mode. In non-TTY environments, such as agent command execution, it prints help instead. Interactive mode uses short keys: digits choose map/reward/card-selection options or play combat cards, `e` ends the turn, `c` collects rewards and proceeds, `r` resolves rewards, Enter refreshes or takes the only unambiguous non-card action, `?` shows help, and `q` quits.

`sts2 state` has two output modes:

- default: route the raw `/state` HTTP JSON by game state and render a compact human-readable view.
- `--raw`: print the raw parsed `/state` HTTP JSON response.

The view layer is only a compact rendering of fields already present in the raw response. It does not add external window state or inferred game facts.

The default combat view includes player/enemy state, enemy intents, playable hand, piles when exposed, and legal actions. Map, event, rest, reward, card-selection, shop, chest, character-select, main-menu, timeline, capstone, and game-over states each route to their own renderer. Legal actions are printed as runnable `sts2 act ...` commands with the argument names and option indices visible from the current raw state.

`sts2 act` posts to `/action`, routes the returned JSON by action/domain/outcome, and renders the routed action result. Pending action responses render the embedded state when the HTTP response includes one. Use `--raw-result` to inspect the full parsed `/action` response.

For reward safety, `sts2 act resolve_rewards` and `sts2 act collect_rewards_and_proceed` refuse to run while a claimable Card reward exists but card choices are not visible. Claim the Card reward first so the Agent can choose or skip the shown cards.

Action names can be written canonically or as aliases without separators, such as `play_card` or `playcard`. The first action argument can also be the numbered action from the current `Legal actions` list, for example `sts2 act 1 --card_index 0` when `[1] play_card(...)` is shown. Action parameters can be passed positionally or by keyword, such as `sts2 act play_card 0 0`, `sts2 act play_card 0 --target_index 0`, or `sts2 act play_card --card_index 0 --target_index 0`. Actions displayed with a concrete default such as `option_index=0` have exactly one visible valid choice and can omit that argument. Actions displayed as `option_index in 0, 1, 2` require an explicit option; `sts2 act` rejects omitted option indices before sending an HTTP action when multiple choices exist.

Shop and potion actions use `option_index` at the CLI boundary, matching the mod API. Positional shorthand works, for example `sts2 act buy_card 4` and `sts2 act use_potion 0`.

Route renderers live under `src/sts2_bridge/state_view/` and `src/sts2_bridge/action_view/`. Real raw HTTP samples and JSON schemas live under `samples/http/` and are used as routing/rendering regression fixtures.

## Logs

Normal CLI calls write JSONL traces under project-level `logs/`, which is ignored by git:

- `logs/cli/YYYYMMDD.jsonl`: call time, command path, argv, parsed params, return code, and full CLI output.
- `logs/http/YYYYMMDD.jsonl`: HTTP method, URL, request body, headers, response status, response headers, response text, timing, and transport errors.

Help-only calls such as `sts2 --help`, `sts2 state --help`, and non-TTY no-arg `sts2` help output are intentionally not logged.

## Screenshot Fallback

`sts2 debug window-status` reports whether the game process/window exists and whether Slay the Spire 2 is currently the frontmost app.

`sts2 screenshot` is a macOS-only debug fallback for visual inspection. When the game is frontmost, it uses ScreenCaptureKit single-window capture. When the game is not frontmost, it will not use rectangle capture by default because that would capture whatever is covering the game. macOS must grant Screen Recording permission to the terminal app that runs the command.

For Godot/Metal windows, macOS may refuse true background window capture. Use `--activate-fallback` as the final fallback: it briefly brings the game to the foreground for rectangle capture, then tries to restore the previous foreground app.

`sts2 debug click-window X Y` is a last-resort macOS UI fallback when the HTTP API and structured state are stuck. Coordinates are relative to the selected game window; add `--normalized` to use 0..1 fractions and `--dry-run` to inspect the resolved screen point before clicking. It activates the game before clicking and restores the previous app by default. macOS may require Accessibility permission for the terminal app.

`sts2 debug recover-rest` is a guarded version of the click fallback for observed REST desyncs. By default it clicks the proven top-left relic target, presses Escape to close the relic detail modal, and reports whether the post-click state actually recovered. If not, it prints next target suggestions. Use `--target relic`, `--target top-bar-relic`, `--target rest-card`, or explicit `--x/--y` normalized coordinates when calibrating from screenshots. When `sts2 state` detects this REST recovery state, it prints `Recovery command: sts2 debug recover-rest`.
