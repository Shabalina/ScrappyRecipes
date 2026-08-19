"""Tests for app/services/menu_service.py — menu slot candidate scoring.

Mirrors the mocking style in tests/test_persistence.py: `db.execute` and
`db.scalar` are AsyncMocks (see `mock_db_session` in conftest.py), and
`generate_embedding` is stubbed so nothing touches the network.
"""
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models import RecipeModel
from app.services import menu_service


def make_recipe(recipe_id, last_menu_number=None):
    return RecipeModel(
        id=recipe_id,
        title=f"Recipe {recipe_id}",
        ingredients=[],
        instructions=[],
        last_menu_number=last_menu_number,
    )


@pytest.fixture(autouse=True)
def stub_embedding(monkeypatch):
    """Every test in this module skips the real OpenAI embedding call."""
    monkeypatch.setattr(
        menu_service, "generate_embedding", AsyncMock(return_value=[0.1] * 1536)
    )


def set_search_rows(mock_db_session, rows):
    """rows: list of (RecipeModel, distance) tuples returned by the vector search."""
    mock_db_session.execute = AsyncMock(
        return_value=MagicMock(all=MagicMock(return_value=rows))
    )


def set_menu_stats(mock_db_session, total_recipes, max_menu_number):
    """db.scalar is called twice, in order: total recipe count, then max menu_number."""
    mock_db_session.scalar = AsyncMock(side_effect=[total_recipes, max_menu_number])


class TestExclusion:
    async def test_exclude_ids_are_passed_into_the_query(self, mock_db_session):
        """Excluded ids must show up in the WHERE ... NOT IN clause sent to the DB.

        The DB double can't actually filter rows for us, so this test inspects
        the compiled statement handed to `db.execute` rather than the (fake)
        result rows.
        """
        set_search_rows(mock_db_session, [])
        set_menu_stats(mock_db_session, total_recipes=12, max_menu_number=0)

        await menu_service.get_slot_candidates(
            mock_db_session, "quick weeknight soup", exclude_ids=[5, 9], limit=3
        )

        stmt = mock_db_session.execute.call_args.args[0]
        compiled_params = stmt.compile().params
        assert [5, 9] in compiled_params.values()

    async def test_no_exclusion_when_list_is_empty(self, mock_db_session):
        """An empty/omitted exclude_ids must not add a NOT IN clause at all."""
        set_search_rows(mock_db_session, [])
        set_menu_stats(mock_db_session, total_recipes=12, max_menu_number=0)

        await menu_service.get_slot_candidates(mock_db_session, "soup", limit=3)

        stmt = mock_db_session.execute.call_args.args[0]
        assert "NOT IN" not in str(stmt)


class TestVarietyPenalty:
    async def test_recently_used_recipe_is_demoted_below_a_fresher_one(
        self, mock_db_session
    ):
        """A closer semantic match that was cooked last menu should lose to a
        farther match that hasn't been used, once the freshness penalty applies.
        """
        recently_used = make_recipe(1, last_menu_number=9)  # elapsed = 10 - 9 = 1
        never_used = make_recipe(2, last_menu_number=None)

        set_search_rows(
            mock_db_session,
            [(recently_used, 0.10), (never_used, 0.20)],
        )
        # total_recipes=24 -> window = max(1, 24 // 12) = 2
        set_menu_stats(mock_db_session, total_recipes=24, max_menu_number=10)

        candidates = await menu_service.get_slot_candidates(
            mock_db_session, "pasta", limit=2
        )

        by_id = {c.recipe.id: c for c in candidates}
        # penalty = 0.25 * (window - elapsed + 1) / window = 0.25 * (2 - 1 + 1) / 2 = 0.25
        assert by_id[1].penalty == pytest.approx(0.25)
        assert by_id[1].final_score == pytest.approx(0.35)
        assert by_id[2].penalty == 0.0
        assert by_id[2].final_score == pytest.approx(0.20)

        # Demotion actually changes the ranking: the never-used recipe wins
        # despite its worse raw distance.
        assert [c.recipe.id for c in candidates] == [2, 1]

    async def test_penalty_decays_linearly_toward_the_window_edge(
        self, mock_db_session
    ):
        """A recipe used further back (but still inside the window) gets a
        smaller penalty than one used most recently."""
        used_last_menu = make_recipe(1, last_menu_number=9)   # elapsed = 1
        used_two_menus_ago = make_recipe(2, last_menu_number=8)  # elapsed = 2

        set_search_rows(
            mock_db_session,
            [(used_last_menu, 0.10), (used_two_menus_ago, 0.10)],
        )
        # total_recipes=24 -> window = 2
        set_menu_stats(mock_db_session, total_recipes=24, max_menu_number=10)

        candidates = await menu_service.get_slot_candidates(
            mock_db_session, "pasta", limit=2
        )
        by_id = {c.recipe.id: c for c in candidates}

        assert by_id[1].penalty == pytest.approx(0.25)   # (2-1+1)/2 * 0.25
        assert by_id[2].penalty == pytest.approx(0.125)  # (2-2+1)/2 * 0.25
        assert by_id[2].penalty < by_id[1].penalty


class TestExpiredPenalty:
    async def test_elapsed_beyond_window_gets_no_penalty(self, mock_db_session):
        """Once a recipe falls outside the freshness window it's fully
        eligible again — no penalty, final_score == raw distance."""
        long_expired = make_recipe(1, last_menu_number=1)  # elapsed = 10 - 1 = 9

        set_search_rows(mock_db_session, [(long_expired, 0.15)])
        # total_recipes=24 -> window = 2, elapsed=9 >> window
        set_menu_stats(mock_db_session, total_recipes=24, max_menu_number=10)

        candidates = await menu_service.get_slot_candidates(
            mock_db_session, "pasta", limit=1
        )

        assert candidates[0].penalty == 0.0
        assert candidates[0].final_score == pytest.approx(0.15)

    async def test_never_used_recipe_gets_no_penalty(self, mock_db_session):
        never_used = make_recipe(1, last_menu_number=None)

        set_search_rows(mock_db_session, [(never_used, 0.42)])
        set_menu_stats(mock_db_session, total_recipes=24, max_menu_number=10)

        candidates = await menu_service.get_slot_candidates(
            mock_db_session, "pasta", limit=1
        )

        assert candidates[0].penalty == 0.0
        assert candidates[0].final_score == pytest.approx(0.42)

    async def test_no_menus_yet_defaults_max_menu_number_to_zero(
        self, mock_db_session
    ):
        """With no menus generated yet, M defaults to 0, so E = 0 - last_menu_number
        is never in [1, W] for any real recipe -> no penalty ever applies."""
        recipe = make_recipe(1, last_menu_number=None)

        set_search_rows(mock_db_session, [(recipe, 0.30)])
        set_menu_stats(mock_db_session, total_recipes=12, max_menu_number=None)

        candidates = await menu_service.get_slot_candidates(
            mock_db_session, "pasta", limit=1
        )

        assert candidates[0].penalty == 0.0


class TestOrderingAndLimit:
    async def test_results_are_sorted_by_final_score_and_truncated_to_limit(
        self, mock_db_session
    ):
        recipes = [make_recipe(i) for i in (1, 2, 3, 4)]
        rows = list(zip(recipes, [0.40, 0.10, 0.30, 0.20]))

        set_search_rows(mock_db_session, rows)
        set_menu_stats(mock_db_session, total_recipes=12, max_menu_number=0)

        candidates = await menu_service.get_slot_candidates(
            mock_db_session, "pasta", limit=2
        )

        assert [c.recipe.id for c in candidates] == [2, 4]
        assert len(candidates) == 2
