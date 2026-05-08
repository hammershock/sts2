# STS2 Agent Handoff

This file is the compact starting context for future agents working on this repo. Prefer this over past terminal logs or full raw state dumps.

## Current Purpose

`sts2-bridge` is a local CLI bridge for Slay the Spire 2 agents. It talks to the STS2-Agent mod HTTP server and exposes three state layers: raw HTTP-derived data, schema-filtered data, and human-readable Agent views.

The bridge is basically usable and now has the first harness layer: YAML schema-driven filtering for state/action HTTP payloads. Policy, planner, and benchmark work are intentionally deferred until the filter layer is stable.

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
- `collect_rewards_and_proceed`: no args
- `end_turn`: no args

The preferred action syntax is `sts2 act ACTION_OR_INDEX [positional_args...] [--field value ...]`. The first argument can be a canonical action name, an alias without separators such as `playcard`, or a numbered action from the current `Legal actions` list. Positional args are mapped by action, for example `play_card 0 0` means `card_index=0,target_index=0`.

Actions displayed with `option_index=0`, including `choose_map_node(option_index=0)`, default to `option_index=0` when no explicit option is passed. This makes `sts2 act 0` match the visible legal action when the only shown action is `[0] choose_map_node(option_index=0)`.

When an invalid arg name is used, the mod often returns a useful message such as `requires option_index`.

## Useful CLI Commands

Use compact views by default:

```bash
sts2
sts2 state
sts2 state --layer filtered
sts2 state --layer raw
sts2 state --view decision --layer filtered
sts2 actions
sts2 wait --timeout 15
sts2 debug health
```

No-arg `sts2` starts an interactive mode only when stdin/stdout are TTYs. In non-TTY agent execution it prints help. Interactive keys: digits choose map/reward options or play combat cards, `e` ends the turn, `c` collects rewards and proceeds, `r` resolves rewards, Enter refreshes or takes the only unambiguous non-card action, `?` shows help, and `q` quits.

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
sts2 state --with-window
sts2 debug window-status
sts2 debug windows
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
- Screenshot is only a debugging fallback. The structured mod state should be primary.

## Implemented Filter Layer

1. Three state layers:
   - `raw`: full parsed HTTP state rendered as text, exposed by `sts2 state --layer raw` or `--raw`.
   - `filtered`: YAML schema-filtered state rendered as text, exposed by `sts2 state --layer filtered`.
   - `view`: default human-readable text, exposed by `sts2 state`.

2. Schema-driven state filtering:
   - YAML schemas live under `src/sts2_bridge/schemas/state/`.
   - The default COMBAT view is concise text built from filtered schema output.
   - The default COMBAT view includes current relics, playable card rarity/type, resolved card rules text, and the current glossary exposed by the mod.
   - The default MAP view includes current position, indexed path choices, key reachable elite/rest/shop/treasure nodes, and a compact row-by-row reachable map.
   - `--view decision`, `--view combat`, and `--view agent` expose progressively richer filtered views.
   - `--raw` remains opt-in for parser/debug work.

3. Filtered action results:
   - YAML schemas live under `src/sts2_bridge/schemas/action/`.
   - Default `sts2 act` renders `status`, action args, compact post-action state, and before/after deltas as text.
   - `--raw-result` preserves full action-result inspection mode, rendered as text.

4. Real HTTP samples:
   - Raw envelopes live under `samples/http/health`, `samples/http/state`, and `samples/http/action`.
   - Current samples cover health, Neow event, map, choose map node, combat states, play card, and end turn.
   - These samples are regression inputs for filtering behavior.

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
