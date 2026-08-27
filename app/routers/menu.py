# app/routers/menu.py
"""Menu API endpoints.

`slot-candidates` is read-only, mirroring the recipe parse endpoints: it just
wraps `get_slot_candidates()` and returns scored candidates, writing nothing.
`confirm` is the only write path for menus — it creates the `menus` row and
bumps `last_menu_number` on every recipe placed in it, so future
slot-candidate lookups apply the variety penalty against this menu.
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import MenuModel, RecipeModel
from app.schemas import MenuConfirmRequest, MenuRead, RecipeRead, SlotCandidateRead
from app.services.menu_service import get_slot_candidates

router = APIRouter(prefix="/api/v1/menu", tags=["menu"])


def _parse_exclude_ids(raw: Optional[str]) -> List[int]:
    if not raw:
        return []
    try:
        return [int(part) for part in raw.split(",") if part.strip()]
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="exclude_ids must be a comma-separated list of integers, e.g. '1,2,3'.",
        )


@router.get(
    "/slot-candidates",
    response_model=List[SlotCandidateRead],
    status_code=status.HTTP_200_OK,
)
async def slot_candidates(
    q: str = Query(..., description="Natural language query for this menu slot, e.g. 'quick weeknight soup'."),
    exclude_ids: Optional[str] = Query(None, description="Comma-separated recipe ids to exclude, e.g. '1,2,3'."),
    limit: int = Query(3, ge=1, le=6),
    db: AsyncSession = Depends(get_db),
):
    """Scored recipe candidates for a single menu slot. Read-only."""
    clean_query = q.strip()
    if not clean_query:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Query cannot be empty.")

    ids = _parse_exclude_ids(exclude_ids)

    try:
        candidates = await get_slot_candidates(db, clean_query, exclude_ids=ids, limit=limit)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Could not get slot candidates: {str(e)}",
        )

    return [
        SlotCandidateRead(
            recipe=RecipeRead.model_validate(c.recipe),
            distance=c.distance,
            penalty=c.penalty,
            final_score=c.final_score,
        )
        for c in candidates
    ]


@router.post(
    "/confirm",
    response_model=MenuRead,
    status_code=status.HTTP_201_CREATED,
)
async def confirm_menu(payload: MenuConfirmRequest, db: AsyncSession = Depends(get_db)):
    """Persists a new menu and bumps `last_menu_number` on its recipes."""
    try:
        max_menu_number = await db.scalar(select(func.max(MenuModel.menu_number))) or 0
        new_menu_number = max_menu_number + 1

        menu = MenuModel(menu_number=new_menu_number, recipe_ids=payload.recipe_ids)
        db.add(menu)

        await db.execute(
            update(RecipeModel)
            .where(RecipeModel.id.in_(payload.recipe_ids))
            .values(last_menu_number=new_menu_number)
        )

        await db.commit()
        await db.refresh(menu)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Could not confirm menu: {str(e)}",
        )

    return menu
