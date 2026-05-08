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
sts2 state --layer filtered
sts2 state --layer raw
sts2 state --view decision --layer filtered
sts2 actions
sts2 act play_card 0
sts2 act play_card 0 0
sts2 act playcard --card_index 0
sts2 act 1 --card_index 0
sts2 act play_card --card_index 0 --target_index 0
sts2 wait --timeout 30
sts2 state --with-window
sts2 debug health
sts2 debug window-status
sts2 debug windows
sts2 debug click-window 0.5 0.4 --normalized --dry-run
sts2 debug recover-rest --dry-run
sts2 screenshot
sts2 screenshot --activate-fallback
```

Running `sts2` with no subcommand starts an interactive TTY mode. In non-TTY environments, such as agent command execution, it prints help instead. Interactive mode uses short keys: digits choose map/reward/card-selection options or play combat cards, `e` ends the turn, `c` collects rewards and proceeds, `r` resolves rewards, Enter refreshes or takes the only unambiguous non-card action, `?` shows help, and `q` quits.

State output has three layers:

- `view`: default human-readable text for Agent input.
- `filtered`: YAML schema-filtered state rendered as text for debugging and downstream tooling.
- `raw`: full parsed HTTP state rendered as text for parser/debug work.

`sts2 state` defaults to the text `view` layer. Use `--layer filtered` for schema-filtered text and `--layer raw` or `--raw` for the full parsed payload rendered as text. Use `--view decision`, `--view combat`, or `--view agent` to select richer filtered state before rendering.

The default combat view includes current relics, player/enemy powers, enemy intents, playable card rarity/type, resolved card rules text, piles, deck, potions, and the glossary entries currently exposed by the mod. The default map view shows current position, indexed choices, key reachable elite/rest/shop/treasure nodes, and a compact row-by-row reachable map. The default event view shows event title, event text, and indexed option titles/descriptions. The default reward view shows reward rows, card choices, alternatives, and warns when a card reward has not been opened yet. The default card-selection view shows the prompt, selection constraints, indexed candidate cards, card rarity/type/cost/rules text, and legal actions. REST screens use API-provided actions when available; if the mod temporarily reports no actions/options on a visible rest site, the view shows marked recovery options instead of legal HTTP actions.

`sts2 act` defaults to a filtered text action result: status, action args, a compact post-action state, and changed fields when a before/after state is available. Use `--raw-result` to inspect the full parsed action result rendered as text.

For reward safety, `sts2 act resolve_rewards` and `sts2 act collect_rewards_and_proceed` refuse to run while a claimable Card reward exists but card choices are not visible. Claim the Card reward first so the Agent can choose or skip the shown cards.

Action names can be written canonically or as aliases without separators, such as `play_card` or `playcard`. The first action argument can also be the numbered action from the current `Legal actions` list, for example `sts2 act 1 --card_index 0` when `[1] play_card(...)` is shown. Action parameters can be passed positionally or by keyword, such as `sts2 act play_card 0 0`, `sts2 act play_card 0 --target_index 0`, or `sts2 act play_card --card_index 0 --target_index 0`. Actions displayed with `option_index=0`, such as `choose_map_node(option_index=0)`, use that default when no explicit option is passed.

Shop and potion actions use `option_index` at the CLI boundary, matching the mod API. Positional shorthand works, for example `sts2 act buy_card 4` and `sts2 act use_potion 0`.

Filtering rules live in YAML files under `src/sts2_bridge/schemas/`, split by `state/` and `action/`. Real raw HTTP samples live under `samples/http/` and are used as regression fixtures for the filtering layer.

## Logs

Normal CLI calls write JSONL traces under project-level `logs/`, which is ignored by git:

- `logs/cli/YYYYMMDD.jsonl`: call time, command path, argv, parsed params, return code, and full CLI output.
- `logs/http/YYYYMMDD.jsonl`: HTTP method, URL, request body, headers, response status, response headers, response text, timing, and transport errors.

Help-only calls such as `sts2 --help`, `sts2 state --help`, and non-TTY no-arg `sts2` help output are intentionally not logged.

## Screenshot Fallback

`sts2 state --with-window` and `sts2 debug window-status` report whether the game process/window exists and whether Slay the Spire 2 is currently the frontmost app.

`sts2 screenshot` is a macOS-only debug fallback for visual inspection. When the game is frontmost, it uses ScreenCaptureKit single-window capture. When the game is not frontmost, it will not use rectangle capture by default because that would capture whatever is covering the game. macOS must grant Screen Recording permission to the terminal app that runs the command.

For Godot/Metal windows, macOS may refuse true background window capture. Use `--activate-fallback` as the final fallback: it briefly brings the game to the foreground for rectangle capture, then tries to restore the previous foreground app.

`sts2 debug click-window X Y` is a last-resort macOS UI fallback when the HTTP API and structured state are stuck. Coordinates are relative to the selected game window; add `--normalized` to use 0..1 fractions and `--dry-run` to inspect the resolved screen point before clicking. It activates the game before clicking and restores the previous app by default. macOS may require Accessibility permission for the terminal app.

`sts2 debug recover-rest` is a guarded version of the click fallback for observed REST desyncs. By default it clicks the proven top-left relic target, presses Escape to close the relic detail modal, and reports whether the post-click state actually recovered. If not, it prints next target suggestions. Use `--target relic`, `--target top-bar-relic`, `--target rest-card`, or explicit `--x/--y` normalized coordinates when calibrating from screenshots. When `sts2 state` detects this REST recovery state, it prints `Recovery command: sts2 debug recover-rest`.
