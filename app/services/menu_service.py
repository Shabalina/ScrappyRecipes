# app/services/menu_service.py
"""Candidate scoring for filling a single slot in a generated meal menu.

Ranks recipes by semantic similarity to a slot query, then demotes recipes
that were used in a recent menu so the same dishes don't reappear every
rotation. Nothing here writes to the `menus` table yet — this is read-only
candidate selection, mirroring the read-only parse endpoints elsewhere in the
app.
"""
from dataclasses import dataclass
from typing import List, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import MenuModel, RecipeModel
from app.services.embedding_service import generate_embedding

# Max penalty applied to a recipe cooked in the immediately preceding menu.
VARIETY_PENALTY_ALPHA = 0.25

# How much wider than `limit` the initial vector-search pool is, so recipes
# demoted by the freshness penalty still have headroom to be out-ranked by
# ones further down the raw similarity order.
CANDIDATE_POOL_MULTIPLIER = 5


@dataclass
class SlotCandidate:
    """A recipe scored for a single menu slot."""
    recipe: RecipeModel
    distance: float
    penalty: float
    final_score: float
    match_score: float


async def get_slot_candidates(
    db: AsyncSession,
    query: str,
    exclude_ids: Optional[List[int]] = None,
    limit: int = 3,
) -> List[SlotCandidate]:
    """
    Finds the best recipe candidates for a menu slot matching `query`.

    Combines pgvector cosine distance with a "variety" penalty that demotes
    recipes cooked within a recent freshness window, so a rotation doesn't
    keep resurfacing the same dishes. Recipes with ids in `exclude_ids`
    (e.g. already placed in another slot of this menu) are dropped entirely
    rather than penalized.
    """
    exclude_ids = exclude_ids or []

    # 1. Vector-search the closest recipes to the query, excluding any ids
    #    already claimed elsewhere in this menu.
    query_vector = await generate_embedding(query)
    distance = RecipeModel.embedding.cosine_distance(query_vector).label("distance")

    stmt = select(RecipeModel, distance).where(RecipeModel.embedding.is_not(None))
    if exclude_ids:
        stmt = stmt.where(RecipeModel.id.notin_(exclude_ids))
    stmt = stmt.order_by(distance).limit(max(limit * CANDIDATE_POOL_MULTIPLIER, limit))

    result = await db.execute(stmt)
    rows = result.all()

    # 2. Freshness half-life window: larger libraries can afford recipes to
    #    stay in "cooldown" longer before they're eligible to resurface.
    total_recipes = await db.scalar(select(func.count()).select_from(RecipeModel)) or 0
    max_menu_number = await db.scalar(select(func.max(MenuModel.menu_number))) or 0
    upcoming_menu_number = max_menu_number + 1
    # window = max(1, total_recipes // 12)
    window = max(1, int(round((total_recipes / 6) / 2)))

    # 3. Score: cosine distance plus a linear-decay penalty for recipes used
    #    within the last `window` menus. Never-used and long-expired recipes
    #    (elapsed > window) get no penalty.
    candidates = []
    for recipe, recipe_distance in rows:
        penalty = 0.0
        if recipe.last_menu_number is not None:
            # elapsed = max_menu_number - recipe.last_menu_number
            elapsed = upcoming_menu_number - recipe.last_menu_number
            if 1 <= elapsed <= window:
                penalty = VARIETY_PENALTY_ALPHA * (window - elapsed + 1) / window

        final_score = recipe_distance + penalty
        candidates.append(
            SlotCandidate(
                recipe=recipe,
                distance=recipe_distance,
                penalty=penalty,
                final_score=final_score,
                # Ranking stays on final_score (ascending); this is purely a
                # higher-is-better presentation of the same number for display.
                match_score=1 - final_score,
            )
        )

    candidates.sort(key=lambda c: c.final_score)
    return candidates[:limit]
