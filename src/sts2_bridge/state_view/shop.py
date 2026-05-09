from __future__ import annotations

from dataclasses import dataclass

from sts2_bridge.state_view.common import RenderConfig, actions, finish, header, section
from sts2_bridge.state_view.model import ViewContext, indexed_line


@dataclass(frozen=True)
class ShopConfig(RenderConfig):
    pass


def render(ctx: ViewContext, config: ShopConfig = ShopConfig(show_glossary=False)) -> str:
    shop = ctx.agent.get("shop") if isinstance(ctx.agent.get("shop"), dict) else {}
    raw_shop = ctx.data.get("shop") if isinstance(ctx.data.get("shop"), dict) else {}
    status = "open" if raw_shop.get("is_open") else "closed"
    lines = [header(ctx), f"Shop: {status}"]
    for title, key in (("Cards", "cards"), ("Relics", "relics"), ("Potions", "potions")):
        items = shop.get(key)
        if isinstance(items, list) and items:
            lines += section(title, [indexed_line(item, index) for index, item in enumerate(items)])
    if raw_shop.get("card_removal"):
        removal = raw_shop["card_removal"]
        if isinstance(removal, dict):
            lines += section("Card removal", [f"price={removal.get('price')} available={removal.get('available')} used={removal.get('used')}"])
    if config.show_actions:
        lines += section("Legal actions", actions(ctx))
    return finish(lines)
