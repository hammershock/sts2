# HTTP Samples 20260508

Source: `logs/http/20260508.jsonl`.

This archive classifies every HTTP trace line by game-logic state, action, or transport category. Full per-record routing metadata lives in `index.jsonl`; grouped counts, labels, schemas, and representative response samples live in `manifest.json`.

Top-level taxonomy:

- `state/map/route_selection`: 地图路线选择。
- `state/shop/*`: 商店入口、购买、移除等选择。
- `state/event/choice`: 随机事件选择。
- `state/rest/*`: 休息处选择、继续、恢复/等待状态。
- `state/card_selection/*`: 战斗弃牌/保留、卡组升级、卡组移除、通用选牌。
- `state/reward/*`: 奖励行、选卡详情、奖励结算。
- `state/gameplay/combat/*`: 游戏内界面，出牌、结束回合、药水、无动作过渡态。
- `state/chest/*`: 宝箱打开、遗物选择和继续。
- `state/game_menu/*`: 结算/未知菜单态。
- `action/*`: `POST /action` 成功、错误、或无 HTTP 响应的传输错误。
- `health/service_ready`: `GET /health` 服务状态。

Schemas are routing schemas rather than strict model schemas: they pin the stable discriminator fields (`screen`, active section, action name, error code, and key available action) while allowing extra payload fields from the mod API.

Use `route_http.py` as a minimal reference router:

```bash
python samples/http/20260508/route_http.py logs/http/20260508.jsonl --summary
python samples/http/20260508/route_http.py logs/http/20260508.jsonl --limit 5 --explain
python samples/http/20260508/route_http.py samples/http/20260508/state/map/route_selection/0078_20260508190621_map.json
```

The script loads `manifest.json` and `schemas/`, validates each response against the routing schemas, and applies a small priority table for intentionally overlapping schemas such as combat states that are both playable and potion-aware.
