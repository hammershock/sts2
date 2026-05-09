# HTTP 20260508 分类摘要

- 来源：`logs/http/20260508.jsonl`
- 总记录数：3112
- 分类数：54
- 有 JSON 返回的记录均分配了 routing schema；2 条 `/action` 超时没有 response JSON，归入 `transport_error`。

## 服务状态

- `health/service_ready`：health/service_ready；1 条；schema: `samples/http/20260508/schemas/health/service_ready.schema.json`；sample: `samples/http/20260508/health/service_ready/0695_20260508194719_health.json`

## 状态查询 GET /state

- `state/card_selection/combat_discard`：卡牌选择 / 战斗弃牌；110 条；schema: `samples/http/20260508/schemas/state/card_selection/combat_discard.schema.json`；sample: `samples/http/20260508/state/card_selection/combat_discard/0113_20260508190932_card_selection.json`
- `state/card_selection/combat_retain`：卡牌选择 / 战斗保留手牌；80 条；schema: `samples/http/20260508/schemas/state/card_selection/combat_retain.schema.json`；sample: `samples/http/20260508/state/card_selection/combat_retain/0204_20260508192538_card_selection.json`
- `state/card_selection/deck_remove`：卡组移除选择；2 条；schema: `samples/http/20260508/schemas/state/card_selection/deck_remove.schema.json`；sample: `samples/http/20260508/state/card_selection/deck_remove/2315_20260508224148_card_selection.json`
- `state/card_selection/deck_upgrade`：卡组升级选择；12 条；schema: `samples/http/20260508/schemas/state/card_selection/deck_upgrade.schema.json`；sample: `samples/http/20260508/state/card_selection/deck_upgrade/0317_20260508193051_card_selection.json`
- `state/card_selection/generic_card_choice`：卡牌选择 / 通用选牌；1 条；schema: `samples/http/20260508/schemas/state/card_selection/generic_card_choice.schema.json`；sample: `samples/http/20260508/state/card_selection/generic_card_choice/1012_20260508203731_card_selection.json`
- `state/chest/open`：宝箱 / 开箱；7 条；schema: `samples/http/20260508/schemas/state/chest/open.schema.json`；sample: `samples/http/20260508/state/chest/open/0562_20260508194454_chest.json`
- `state/chest/proceed`：宝箱 / 继续；4 条；schema: `samples/http/20260508/schemas/state/chest/proceed.schema.json`；sample: `samples/http/20260508/state/chest/proceed/1472_20260508213459_chest.json`
- `state/chest/relic_choice`：宝箱 / 遗物选择；8 条；schema: `samples/http/20260508/schemas/state/chest/relic_choice.schema.json`；sample: `samples/http/20260508/state/chest/relic_choice/0566_20260508194521_chest.json`
- `state/event/choice`：随机事件选择；48 条；schema: `samples/http/20260508/schemas/state/event/choice.schema.json`；sample: `samples/http/20260508/state/event/choice/0328_20260508193121_event.json`
- `state/game_menu/game_over`：游戏菜单 / 结算；2 条；schema: `samples/http/20260508/schemas/state/game_menu/game_over.schema.json`；sample: `samples/http/20260508/state/game_menu/game_over/3111_20260508235528_game_over.json`
- `state/game_menu/unknown`：游戏菜单 / 未知或空状态；5 条；schema: `samples/http/20260508/schemas/state/game_menu/unknown.schema.json`；sample: `samples/http/20260508/state/game_menu/unknown/0999_20260508203406_unknown.json`
- `state/gameplay/combat/actionable`：游戏内界面 / 战斗出牌与结束回合；801 条；schema: `samples/http/20260508/schemas/state/gameplay/combat/actionable.schema.json`；sample: `samples/http/20260508/state/gameplay/combat/actionable/0001_20260508190215_combat.json`
- `state/gameplay/combat/end_turn_only`：游戏内界面 / 战斗只能结束回合；112 条；schema: `samples/http/20260508/schemas/state/gameplay/combat/end_turn_only.schema.json`；sample: `samples/http/20260508/state/gameplay/combat/end_turn_only/0006_20260508190241_combat.json`
- `state/gameplay/combat/no_actions_transition`：游戏内界面 / 战斗无可用动作过渡态；258 条；schema: `samples/http/20260508/schemas/state/gameplay/combat/no_actions_transition.schema.json`；sample: `samples/http/20260508/state/gameplay/combat/no_actions_transition/0030_20260508190427_combat.json`
- `state/gameplay/combat/potion_and_combat`：游戏内界面 / 战斗含药水动作；173 条；schema: `samples/http/20260508/schemas/state/gameplay/combat/potion_and_combat.schema.json`；sample: `samples/http/20260508/state/gameplay/combat/potion_and_combat/0081_20260508190642_combat.json`
- `state/gameplay/combat/potion_only`：游戏内界面 / 战斗药水或过渡态；7 条；schema: `samples/http/20260508/schemas/state/gameplay/combat/potion_only.schema.json`；sample: `samples/http/20260508/state/gameplay/combat/potion_only/0091_20260508190723_combat.json`
- `state/map/route_selection`：地图路线选择；93 条；schema: `samples/http/20260508/schemas/state/map/route_selection.schema.json`；sample: `samples/http/20260508/state/map/route_selection/0078_20260508190621_map.json`
- `state/rest/options`：休息处选择 / 休息或锻造；25 条；schema: `samples/http/20260508/schemas/state/rest/options.schema.json`；sample: `samples/http/20260508/state/rest/options/0312_20260508193022_rest.json`
- `state/rest/potion_only`：休息处选择 / 仅药水动作；33 条；schema: `samples/http/20260508/schemas/state/rest/potion_only.schema.json`；sample: `samples/http/20260508/state/rest/potion_only/0970_20260508202745_rest.json`
- `state/rest/proceed`：休息处选择 / 休息后继续；36 条；schema: `samples/http/20260508/schemas/state/rest/proceed.schema.json`；sample: `samples/http/20260508/state/rest/proceed/0320_20260508193101_rest.json`
- `state/rest/recovery_or_wait`：休息处选择 / 无动作或恢复等待；161 条；schema: `samples/http/20260508/schemas/state/rest/recovery_or_wait.schema.json`；sample: `samples/http/20260508/state/rest/recovery_or_wait/0576_20260508194550_rest.json`
- `state/reward/card_choice`：奖励选择 / 选卡详情；26 条；schema: `samples/http/20260508/schemas/state/reward/card_choice.schema.json`；sample: `samples/http/20260508/state/reward/card_choice/0134_20260508191056_card_selection.json`
- `state/reward/collect_or_resolve`：奖励选择 / 收集或结算；23 条；schema: `samples/http/20260508/schemas/state/reward/collect_or_resolve.schema.json`；sample: `samples/http/20260508/state/reward/collect_or_resolve/0138_20260508191116_reward.json`
- `state/reward/rows`：奖励选择 / 奖励行；85 条；schema: `samples/http/20260508/schemas/state/reward/rows.schema.json`；sample: `samples/http/20260508/state/reward/rows/0074_20260508190611_reward.json`
- `state/shop/closed`：商店选择 / 店外入口；23 条；schema: `samples/http/20260508/schemas/state/shop/closed.schema.json`；sample: `samples/http/20260508/state/shop/closed/0146_20260508191326_shop.json`
- `state/shop/inventory`：商店选择 / 店内购买与移除；37 条；schema: `samples/http/20260508/schemas/state/shop/inventory.schema.json`；sample: `samples/http/20260508/state/shop/inventory/0150_20260508191342_shop.json`

## 动作请求 POST /action

- `action/card_selection/confirm_selection/success`：动作 / 确认选择成功；4 条；schema: `samples/http/20260508/schemas/action/card_selection/confirm_selection/success.schema.json`；sample: `samples/http/20260508/action/card_selection/confirm_selection/success/0282_20260508192918_confirm_selection.json`
- `action/card_selection/select_deck_card/success`：动作 / 卡牌选择成功；113 条；schema: `samples/http/20260508/schemas/action/card_selection/select_deck_card/success.schema.json`；sample: `samples/http/20260508/action/card_selection/select_deck_card/success/0114_20260508190932_select_deck_card.json`
- `action/chest/choose_treasure_relic/error/invalid_request`：错误 / 宝箱遗物缺少参数；1 条；schema: `samples/http/20260508/schemas/action/chest/choose_treasure_relic/error/invalid_request.schema.json`；sample: `samples/http/20260508/action/chest/choose_treasure_relic/error/invalid_request/1468_20260508213441_choose_treasure_relic.json`
- `action/chest/choose_treasure_relic/success`：动作 / 宝箱遗物选择成功；2 条；schema: `samples/http/20260508/schemas/action/chest/choose_treasure_relic/success.schema.json`；sample: `samples/http/20260508/action/chest/choose_treasure_relic/success/1471_20260508213459_choose_treasure_relic.json`
- `action/chest/open_chest/success`：动作 / 打开宝箱成功；3 条；schema: `samples/http/20260508/schemas/action/chest/open_chest/success.schema.json`；sample: `samples/http/20260508/action/chest/open_chest/success/0565_20260508194510_open_chest.json`
- `action/event/choose_event_option/success`：动作 / 随机事件选择成功；18 条；schema: `samples/http/20260508/schemas/action/event/choose_event_option/success.schema.json`；sample: `samples/http/20260508/action/event/choose_event_option/success/0333_20260508193206_choose_event_option.json`
- `action/event/choose_event_option/transport_error`：错误 / 事件选择无 HTTP 响应；2 条；schema: `无（无 response JSON）`；sample: `无（无 response JSON 或仅索引）`
- `action/gameplay/combat/end_turn/success`：动作 / 战斗结束回合成功；95 条；schema: `samples/http/20260508/schemas/action/gameplay/combat/end_turn/success.schema.json`；sample: `samples/http/20260508/action/gameplay/combat/end_turn/success/0007_20260508190241_end_turn.json`
- `action/gameplay/combat/play_card/error/invalid_target`：错误 / 出牌目标或手牌索引错误；3 条；schema: `samples/http/20260508/schemas/action/gameplay/combat/play_card/error/invalid_target.schema.json`；sample: `samples/http/20260508/action/gameplay/combat/play_card/error/invalid_target/1239_20260508210754_play_card.json, samples/http/20260508/action/gameplay/combat/play_card/error/invalid_target/1354_20260508212256_play_card.json, samples/http/20260508/action/gameplay/combat/play_card/error/invalid_target/2544_20260508230420_play_card.json`
- `action/gameplay/combat/play_card/success`：动作 / 战斗出牌成功；517 条；schema: `samples/http/20260508/schemas/action/gameplay/combat/play_card/success.schema.json`；sample: `samples/http/20260508/action/gameplay/combat/play_card/success/0003_20260508190224_play_card.json`
- `action/gameplay/combat/use_potion/error/invalid_request`：错误 / 药水参数错误；1 条；schema: `samples/http/20260508/schemas/action/gameplay/combat/use_potion/error/invalid_request.schema.json`；sample: `samples/http/20260508/action/gameplay/combat/use_potion/error/invalid_request/0175_20260508191534_use_potion.json`
- `action/gameplay/combat/use_potion/error/invalid_target`：错误 / 药水缺少目标；1 条；schema: `samples/http/20260508/schemas/action/gameplay/combat/use_potion/error/invalid_target.schema.json`；sample: `samples/http/20260508/action/gameplay/combat/use_potion/error/invalid_target/1030_20260508203940_use_potion.json`
- `action/gameplay/combat/use_potion/success`：动作 / 战斗使用药水成功；9 条；schema: `samples/http/20260508/schemas/action/gameplay/combat/use_potion/success.schema.json`；sample: `samples/http/20260508/action/gameplay/combat/use_potion/success/0177_20260508191543_use_potion.json`
- `action/map/choose_map_node/success`：动作 / 地图路线选择成功；45 条；schema: `samples/http/20260508/schemas/action/map/choose_map_node/success.schema.json`；sample: `samples/http/20260508/action/map/choose_map_node/success/0080_20260508190637_choose_map_node.json`
- `action/navigation/proceed/success`：动作 / 继续前进成功；19 条；schema: `samples/http/20260508/schemas/action/navigation/proceed/success.schema.json`；sample: `samples/http/20260508/action/navigation/proceed/success/0166_20260508191454_proceed.json`
- `action/rest/choose_rest_option/error/invalid_action`：错误 / 休息动作不可用；1 条；schema: `samples/http/20260508/schemas/action/rest/choose_rest_option/error/invalid_action.schema.json`；sample: `samples/http/20260508/action/rest/choose_rest_option/error/invalid_action/0774_20260508200554_choose_rest_option.json`
- `action/rest/choose_rest_option/success`：动作 / 休息处选择成功；11 条；schema: `samples/http/20260508/schemas/action/rest/choose_rest_option/success.schema.json`；sample: `samples/http/20260508/action/rest/choose_rest_option/success/0316_20260508193051_choose_rest_option.json`
- `action/reward/choose_reward_card/success`：动作 / 奖励选卡成功；15 条；schema: `samples/http/20260508/schemas/action/reward/choose_reward_card/success.schema.json`；sample: `samples/http/20260508/action/reward/choose_reward_card/success/0137_20260508191116_choose_reward_card.json`
- `action/reward/claim_reward/success`：动作 / 领取奖励项成功；38 条；schema: `samples/http/20260508/schemas/action/reward/claim_reward/success.schema.json`；sample: `samples/http/20260508/action/reward/claim_reward/success/0130_20260508191046_claim_reward.json`
- `action/reward/collect_and_proceed/success`：动作 / 收集奖励并继续成功；16 条；schema: `samples/http/20260508/schemas/action/reward/collect_and_proceed/success.schema.json`；sample: `samples/http/20260508/action/reward/collect_and_proceed/success/0140_20260508191125_collect_rewards_and_proceed.json`
- `action/reward/resolve_rewards/success`：动作 / 结算奖励成功；3 条；schema: `samples/http/20260508/schemas/action/reward/resolve_rewards/success.schema.json`；sample: `samples/http/20260508/action/reward/resolve_rewards/success/0077_20260508190620_resolve_rewards.json`
- `action/shop/buy_card/error/invalid_request`：错误 / 购买卡牌参数错误；1 条；schema: `samples/http/20260508/schemas/action/shop/buy_card/error/invalid_request.schema.json`；sample: `samples/http/20260508/action/shop/buy_card/error/invalid_request/0153_20260508191405_buy_card.json`
- `action/shop/buy_card/success`：动作 / 购买卡牌成功；9 条；schema: `samples/http/20260508/schemas/action/shop/buy_card/success.schema.json`；sample: `samples/http/20260508/action/shop/buy_card/success/0155_20260508191415_buy_card.json`
- `action/shop/buy_relic/success`：动作 / 购买遗物成功；1 条；schema: `samples/http/20260508/schemas/action/shop/buy_relic/success.schema.json`；sample: `samples/http/20260508/action/shop/buy_relic/success/1416_20260508212958_buy_relic.json`
- `action/shop/close_inventory/success`：动作 / 关闭商店库存成功；5 条；schema: `samples/http/20260508/schemas/action/shop/close_inventory/success.schema.json`；sample: `samples/http/20260508/action/shop/close_inventory/success/0162_20260508191445_close_shop_inventory.json`
- `action/shop/open_inventory/success`：动作 / 打开商店库存成功；5 条；schema: `samples/http/20260508/schemas/action/shop/open_inventory/success.schema.json`；sample: `samples/http/20260508/action/shop/open_inventory/success/0149_20260508191342_open_shop_inventory.json`
- `action/shop/remove_card/success`：动作 / 商店移除卡牌成功；1 条；schema: `samples/http/20260508/schemas/action/shop/remove_card/success.schema.json`；sample: `samples/http/20260508/action/shop/remove_card/success/2314_20260508224148_remove_card_at_shop.json`
