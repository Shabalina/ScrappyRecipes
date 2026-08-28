# app/services/shopping_service.py
"""Aggregates a confirmed menu's recipes into a single, categorized shopping list.

Mirrors the draft -> confirm split used elsewhere in the app: the expensive
part (LLM consolidation across every recipe in the menu) runs at most once
per menu. `MenuModel.shopping_list` is the cache — once populated, every
later request for the same menu is a plain DB read, no LLM call.
"""
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import MenuModel, RecipeModel
from app.services.llm_parser import RecipeParserService


async def generate_menu_shopping_list(
    db: AsyncSession,
    menu_id: int,
    parser: Optional[RecipeParserService] = None,
) -> Optional[dict]:
    """Returns the categorized shopping list for `menu_id`.

    Returns the cached `MenuModel.shopping_list` if already generated.
    Otherwise collects every recipe in `menu.recipe_ids`, asks the LLM to
    consolidate and categorize their ingredients, persists the result, and
    returns it. Returns None if no menu with `menu_id` exists.
    """
    menu = await db.get(MenuModel, menu_id)
    if menu is None:
        return None

    if menu.shopping_list is not None:
        return menu.shopping_list

    result = await db.execute(select(RecipeModel).where(RecipeModel.id.in_(menu.recipe_ids)))
    recipes_by_id = {r.id: r for r in result.scalars().all()}
    # Recipes deleted after the menu was confirmed are silently dropped,
    # mirroring GET /api/v1/menus (see MenuHistoryRead.recipes).
    ordered_recipes = [recipes_by_id[rid] for rid in menu.recipe_ids if rid in recipes_by_id]

    parser = parser or RecipeParserService()
    shopping_list = await parser.generate_shopping_list(ordered_recipes)

    menu.shopping_list = shopping_list.model_dump()
    await db.commit()
    await db.refresh(menu)

    return menu.shopping_list
