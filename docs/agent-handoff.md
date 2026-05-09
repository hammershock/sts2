# STS2 Agent Handoff

This file is the compact starting context for future agents working on this repo. Prefer this over past terminal logs or full raw state dumps.

## Current Purpose

`sts2-bridge` is a local CLI bridge for Slay the Spire 2 agents. It talks to the STS2-Agent mod HTTP server, routes raw `/state` and `/action` JSON responses, and renders compact human-readable Agent views.

The bridge is basically usable and now has the first harness layer: schema-assisted routing plus per-route renderers for state/action HTTP payloads. Policy, planner, and benchmark work are intentionally deferred until the routed view layer is stable.

## Local Setup

- Repo: `/Users/hammer/workspace/sts2`
- CLI: `sts2`
- Python used during setup: system/pyenv Python, not conda base
- Install after code edits:

```bash
python -m pip install -e ".[dev]"
pyenv rehash
```

- Test:

```bash
python -m pytest
```

## Game And Mod

- STS2 app dir:
  `/Users/hammer/Library/Application Support/Steam/steamapps/common/Slay the Spire 2/SlayTheSpire2.app`
- Mod files live under:
  `Contents/MacOS/mods/`
- Verified mod API:
  - service: `sts2-ai-agent`
  - mod version: `0.7.0`
  - protocol: `2026-03-11-v1`
  - game version seen: `v0.103.2`
- Default API base URL: `http://127.0.0.1:8080`
- Launch through Steam if needed:

```bash
"$HOME/Library/Application Support/Steam/Steam.AppBundle/Steam/Contents/MacOS/steam_osx" -applaunch 2868840
```

## Verified API Semantics

- Read state: `GET /state`
- Act: `POST /action`
- Action payload is flat, not nested:

```json
{"action": "play_card", "card_index": 0, "target_index": 1}
```

Important argument names discovered by real play:

- `play_card`: `card_index`, optional `target_index`
- `choose_map_node`: `option_index`
- `claim_reward`: `option_index`
- `choose_reward_card`: `option_index`
- `choose_event_option`: `option_index`
- `buy_card`, `buy_relic`, `buy_potion`: `option_index`
- `use_potion`, `discard_potion`: `option_index`, optional `target_index`
- `collect_rewards_and_proceed`: no args
- `end_turn`: no args

The preferred action syntax is `sts2 act ACTION_OR_INDEX [positional_args...] [--field value ...]`. The first argument can be a canonical action name, an alias without separators such as `playcard`, or a numbered action from the current `Legal actions` list. Positional args are mapped by action, for example `play_card 0 0` means `card_index=0,target_index=0`.

Actions displayed with a concrete default such as `option_index=0` have exactly one valid choice and can be run without an explicit option. Actions displayed as `option_index in 0, 1, 2` require an explicit option, such as `sts2 act choose_event_option 1` or `sts2 act choose_event_option --option_index 1`; omitted arguments are rejected before the HTTP POST when the state is ambiguous.

When an invalid arg name is used, the mod often returns a useful message such as `requires option_index`.

## Useful CLI Commands

Use compact views by default:

```bash
sts2
sts2 state
sts2 state --raw
sts2 wait --timeout 15
sts2 debug health
sts2 debug route-render-samples
```

No-arg `sts2` starts an interactive mode only when stdin/stdout are TTYs. In non-TTY agent execution it prints help. Interactive keys: digits choose map/reward/card-selection options or play combat cards, `e` ends the turn, `c` collects rewards and proceeds, `r` resolves rewards, Enter refreshes or takes the only unambiguous non-card action, `?` shows help, and `q` quits.

Execute actions:

```bash
sts2 act play_card 0
sts2 act play_card 0 0
sts2 act play_card 0 --target_index 0
sts2 act playcard --card_index 0
sts2 act 1 --card_index 0
sts2 act play_card --card_index 0 --target_index 0
sts2 act end_turn
sts2 act choose_map_node 0
```

Window and screenshot debugging:

```bash
sts2 debug window-status
sts2 debug windows
sts2 debug click-window 0.5 0.4 --normalized --dry-run
sts2 debug recover-rest --dry-run
sts2 screenshot
sts2 screenshot --activate-fallback
```

## Current Live Run Snapshot

As of the last manual play session:

- Run id: `LZ8Z1C91L3`
- Character: Ironclad / 铁甲战士
- Floor: 3
- Screen: `MAP`
- HP: `57/87`
- Gold: `126`
- Relic: Burning Blood / 燃烧之血
- Added cards: `预备打击` and `燃烧`
- Next map action: one available Monster node, likely:

```bash
sts2 act choose_map_node 0
```

Re-read `sts2 state` before acting, because the user may have played manually.

## Lessons From Manual Play

- Always refresh state after every action. Card indices shift after each played card.
- Do not chain card actions from stale hand data.
- `end_turn` creates a transient window where `available_actions=[]`, hand is empty, or animations are still resolving.
- Waiting only for `available_actions` is insufficient for robust automation. For combat, wait until one of these is true:
  - reward/map/event/rest/shop screen appears
  - `turn` changed and hand/playable cards are populated
  - combat ended
- Background game windows can update slowly. Poll conservatively and cap retries.
- Full raw output is very expensive. Prefer compact summaries and omit deck/map internals unless directly needed.
- Screenshot and click fallback are only debugging/recovery tools. The structured mod state should be primary.

## Implemented Route-Based View Layer

1. State output:
   - `sts2 state`: fetches `/state`, routes the raw HTTP JSON by game state, and renders a compact human-readable view.
   - `sts2 state --raw`: prints the raw parsed `/state` HTTP JSON response.
   - The view layer is only a compact rendering of raw response fields. It does not inject window state or other external observations.

2. State routes and renderers:
   - Route schemas and HTTP samples live under `samples/http/20260508/`.
   - State renderers live under `src/sts2_bridge/state_view/`.
   - The default COMBAT view includes player/enemy state, intents, playable hand, legal actions, piles when exposed, and current glossary entries.
   - The default MAP view includes current position, indexed path choices, key reachable elite/rest/shop/treasure nodes, and a compact row-by-row reachable map.
   - The default EVENT view includes title, description text, every option index, option title/description, and important flags such as locked/proceed/kill/relic preview.
   - The default SHOP view includes open inventory cards/relics/potions, true option indices, prices, affordability, sale flags, and card-removal price.
   - The default REWARD view includes reward rows, claimable flags, card choices, skip alternatives, and a warning when a claimable Card reward exists but card choices are not loaded yet.
   - The default CARD_SELECTION view includes the prompt, selection constraints, indexed candidate cards, card rarity/type/cost/rules text, and legal actions.
   - CHARACTER_SELECT, MAIN_MENU timeline, MAIN_MENU, CAPSTONE_SELECTION, and GAME_OVER have separate routes and renderers.
   - The default GAME_OVER view includes an explicit result. Player HP 0 / `is_alive=false` is treated as death even if the backend exposes a confusing victory flag.
   - REST screens render only raw/API-provided legal actions.
   - `sts2 act resolve_rewards` and `sts2 act collect_rewards_and_proceed` are guarded when a claimable Card reward exists but card choices are not loaded. Claim the Card reward first to expose choices.
   - `--raw` remains opt-in for parser/debug work.

3. Routed action results:
   - Action renderers live under `src/sts2_bridge/action_view/`.
   - Default `sts2 act` renders the routed `/action` response by action domain and outcome: completed, pending, transport error, or API error.
   - Pending action responses render embedded state when the HTTP response contains one.
   - `sts2 act` completes omitted `option_index` and `target_index` only when exactly one valid value is visible in the filtered state. If multiple values are available, it raises `ambiguous_action_args` and does not send a POST.
   - `--raw-result` preserves raw action-result inspection mode.

4. Real HTTP samples:
   - Legacy flat fixtures remain under `samples/http/health` and `samples/http/state` for older tests.
   - The routed 20260508 corpus under `samples/http/20260508/` contains representative raw envelopes, schemas, a manifest, and summaries.
   - `sts2 debug route-render-samples` regenerates ignored human-readable render samples under `debug/route_render_samples/` from `logs/http/`.

5. Runtime traces:
   - Project-level `logs/` is gitignored.
   - `logs/cli/YYYYMMDD.jsonl` records normal CLI calls, parsed params, return code, and full CLI output.
   - `logs/http/YYYYMMDD.jsonl` records raw HTTP method, URL, request body, headers, status, response headers, response text, timing, and transport errors.
   - Help-only invocations and non-TTY no-arg help output are filtered out and not logged.

6. macOS recovery tools:
   - `sts2 debug window-status` and `sts2 screenshot` return normalized YAML-safe primitives, including PyObjC string values.
   - `sts2 debug click-window X Y` clicks inside the selected STS2 window as a last-resort UI fallback. Use `--normalized` for 0..1 window-relative coordinates and `--dry-run` before real clicks. This is the recovery path for visible UI desyncs where the HTTP API rejects all actions.
   - `sts2 debug recover-rest` is a guarded REST-specific recovery. It defaults to the proven top-left relic target, presses Escape to close the relic modal, can target `relic`, `top-bar-relic`, `rest-card`, or explicit normalized `--x/--y` coordinates, and reports `status: recovered` or `status: unchanged` after re-reading state. REST recovery views print `Recovery command: sts2 debug recover-rest`.

## Next Harness Improvements

1. Expand sample coverage:
   - Add dedicated EVENT/SHOP/REST/CHEST/REWARD state samples.
   - Add more action response samples, especially reward selection and non-combat transitions.

2. Harden schema coverage:
   - Split additional screen-specific schemas when raw samples show large or unstable payloads.
   - Keep schema files as the primary contract for what reaches an Agent.

3. Explore richer card/keyword explanations:
   - Current `/state` exposes `agent_view.combat.hand[*].line`, `keywords`, and `agent_view.glossary`.
   - Full card payloads also expose `resolved_rules_text`, `rules_text`, and `dynamic_values` such as `WeakPower=1`.
   - The current HTTP surface does not expose the full UI keyword tooltip text for `虚弱`, including the 25% attack damage reduction constant.
   - Initial binary inspection found mod symbols around `BuildAgentGlossary`, `AgentKeywordDefinitions`, and glossary matching, so the right next step is probably a mod/API extension rather than Python-side guessing.
   - Investigate whether the mod/game can expose full UI tooltip text and dynamic gameplay constants such as Weak's damage reduction percentage.
   - Do not hardcode keyword mechanics in the bridge; prefer game/mod-provided values, and mark missing details as unavailable.

4. Add planner/pruner support later:
   - Enumerate legal card sequences for current turn using refreshed state after simulated or real actions.
   - Score candidate sequences by expected damage, incoming damage prevented, lethal, energy use, card draw, powers applied, and HP risk.
   - Return top-k action sequences plus a short reason, not the full tree.

5. Add prediction reconciliation later:
   - Predict next state after a planned sequence.
   - Execute one action at a time.
   - After each real state, compare key fields and either continue, repair the plan, or stop for Agent input.

6. Add benchmarks:
   - Record compact state/action traces.
   - Replay states against heuristic and Agent-assisted policies.
   - Track win-rate proxies, HP lost per floor, unnecessary Agent calls, token use, and action latency.

## Design Direction

The bridge should become an AI harness, not just a raw payload pipe. The LLM should receive concise decision packets and only be invoked for choices that are strategically meaningful. Cheap deterministic code should handle obvious combat micro-actions, reward collection, proceed buttons, and state stabilization.
