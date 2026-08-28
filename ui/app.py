import os

import requests
import streamlit as st

st.set_page_config(page_title="Scrappy Recipes", layout="centered")

def get_secret(key: str, default: str = "") -> str:
  """Safely retrieve secrets from st.secrets or environment variables."""
  try:
    if hasattr(st, "secrets") and key in st.secrets:
      return st.secrets[key]
  except Exception:
    pass
  return os.getenv(key, default)


APP_API_KEY = get_secret("APP_API_KEY", "local_dev_secret_key_123")
API_BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8000")

api_session = requests.Session()
api_session.headers.update({"X-API-Key": APP_API_KEY})


def show_api_error(response, action):
  """Renders an HTTPError as an st.error, calling out an auth failure specifically."""
  if response.status_code == 403:
    st.error("Authentication failed: Invalid API Key")
    return
  try:
    detail = response.json().get("detail", response.text)
  except ValueError:
    detail = response.text
  st.error(f"{action}: {detail}")


st.title("Scrappy Recipes")

# A widget's session_state key can't be reassigned after the widget has been
# instantiated in the same run, so a cross-tab "send this URL over" action
# stages the value here and applies it before the URL tab's text_input renders.
if "pending_recipe_url" in st.session_state:
    st.session_state["recipe_url_input"] = st.session_state.pop("pending_recipe_url")
    st.session_state["url_prefill_notice"] = True


def render_draft_preview(draft):
    st.divider()
    st.subheader(draft.get("title", "Untitled Recipe"))

    if draft.get("description"):
        st.write(draft["description"])

    meta_cols = st.columns(3)
    meta_cols[0].metric("Prep time (min)", draft.get("prep_time_minutes") or "-")
    meta_cols[1].metric("Cook time (min)", draft.get("cook_time_minutes") or "-")
    meta_cols[2].metric("Servings", draft.get("servings") or "-")

    st.markdown("**Ingredients**")
    for ingredient in draft.get("ingredients", []):
        unit = f" {ingredient['unit']}" if ingredient.get("unit") else ""
        st.markdown(f"- {ingredient['quantity']}{unit} {ingredient['name']}")

    st.markdown("**Instructions**")
    for i, step in enumerate(draft.get("instructions", []), start=1):
        st.markdown(f"{i}. {step}")

    if draft.get("cooking_methods"):
        st.markdown(f"**Cooking methods:** {', '.join(draft['cooking_methods'])}")
    if draft.get("tags"):
        st.markdown(f"**Tags:** {', '.join(draft['tags'])}")


def save_draft(draft, session_key, button_key):
    if st.button("Approve & Save", key=button_key):
        with st.spinner("Saving recipe..."):
            try:
                response = api_session.post(
                    f"{API_BASE_URL}/api/v1/recipes/confirm",
                    json=draft,
                    timeout=60,
                )
                response.raise_for_status()
                saved = response.json()
                st.success(f"Saved recipe #{saved['id']}: {saved['title']}")
                del st.session_state[session_key]
            except requests.exceptions.HTTPError:
                show_api_error(response, "Failed to save recipe")
            except requests.exceptions.RequestException as e:
                st.error(f"Request failed: {e}")


ingestion_tab, search_tab, meal_plan_tab, existing_menus_tab = st.tabs(
    ["Parse Recipe", "Search & Browse", "Menu Builder", "Existing Menus"]
)

with ingestion_tab:
    url_tab, text_tab, images_tab = st.tabs(["From URL", "From Text", "From Images"])

    with url_tab:
        st.subheader("Parse a recipe from a URL")

        if st.session_state.pop("url_prefill_notice", False):
            st.info("URL loaded from the Search tab's web results.")

        st.session_state.setdefault("recipe_url_input", "")
        recipe_url = st.text_input(
            "Recipe URL",
            placeholder="https://example.com/my-recipe",
            key="recipe_url_input",
        )

        if st.button("Parse URL", key="parse_url_button"):
            if not recipe_url.strip():
                st.warning("Enter a URL first.")
            else:
                with st.spinner("Fetching and parsing recipe..."):
                    try:
                        response = api_session.post(
                            f"{API_BASE_URL}/api/v1/recipes/parse-url",
                            json={"url": recipe_url.strip()},
                            timeout=60,
                        )
                        response.raise_for_status()
                        st.session_state["draft_recipe_url"] = response.json()
                    except requests.exceptions.HTTPError:
                        show_api_error(response, "Failed to parse recipe")
                    except requests.exceptions.RequestException as e:
                        st.error(f"Request failed: {e}")

        draft = st.session_state.get("draft_recipe_url")
        if draft:
            render_draft_preview(draft)
            save_draft(draft, "draft_recipe_url", "approve_save_url_button")

    with text_tab:
        st.subheader("Parse a recipe from raw text")

        recipe_text = st.text_area(
            "Recipe text",
            placeholder="Paste the full recipe text here...",
            height=250,
        )

        if st.button("Parse Text", key="parse_text_button"):
            if not recipe_text.strip():
                st.warning("Paste some recipe text first.")
            else:
                with st.spinner("Parsing recipe..."):
                    try:
                        response = api_session.post(
                            f"{API_BASE_URL}/api/v1/recipes/parse-text",
                            json={"text": recipe_text.strip()},
                            timeout=60,
                        )
                        response.raise_for_status()
                        st.session_state["draft_recipe_text"] = response.json()
                    except requests.exceptions.HTTPError:
                        show_api_error(response, "Failed to parse recipe")
                    except requests.exceptions.RequestException as e:
                        st.error(f"Request failed: {e}")

        draft = st.session_state.get("draft_recipe_text")
        if draft:
            render_draft_preview(draft)
            save_draft(draft, "draft_recipe_text", "approve_save_text_button")

    with images_tab:
        st.subheader("Parse a recipe from screenshots")
        st.caption("Select all pages of the same recipe together — they'll be parsed as one recipe.")

        recipe_images = st.file_uploader(
            "Recipe screenshots",
            type=["jpg", "jpeg", "png", "webp"],
            accept_multiple_files=True,
            key="recipe_images_uploader",
        )

        if recipe_images:
            st.image(recipe_images, width=150)

        if st.button("Parse Images", key="parse_images_button"):
            if not recipe_images:
                st.warning("Upload at least one image first.")
            else:
                with st.spinner("Parsing recipe..."):
                    try:
                        files = [
                            ("files", (image.name, image.getvalue(), image.type))
                            for image in recipe_images
                        ]
                        response = api_session.post(
                            f"{API_BASE_URL}/api/v1/recipes/parse-images",
                            files=files,
                            timeout=60,
                        )
                        response.raise_for_status()
                        st.session_state["draft_recipe_images"] = response.json()
                    except requests.exceptions.HTTPError:
                        show_api_error(response, "Failed to parse recipe")
                    except requests.exceptions.RequestException as e:
                        st.error(f"Request failed: {e}")

        draft = st.session_state.get("draft_recipe_images")
        if draft:
            render_draft_preview(draft)
            save_draft(draft, "draft_recipe_images", "approve_save_images_button")

with search_tab:
    st.subheader("Search your saved recipes")

    def match_quality_label(distance):
        if distance <= 0.3:
            return "Excellent"
        elif distance <= 0.45:
            return "Good"
        elif distance <= 0.6:
            return "Moderate"
        else:
            return "Weak"

    search_query = st.text_input(
        "What are you in the mood for?",
        placeholder="e.g. cold summer soup",
        key="local_search_query",
    )

    if st.button("Search Local Recipes", key="search_local_button"):
        if not search_query.strip():
            st.warning("Enter a search query first.")
        else:
            with st.spinner("Searching local recipes..."):
                try:
                    response = api_session.get(
                        f"{API_BASE_URL}/api/v1/recipes/search",
                        params={"q": search_query.strip(), "limit": 1},
                        timeout=30,
                    )
                    response.raise_for_status()
                    results = response.json()
                    st.session_state["local_search_result"] = results[0] if results else None
                    st.session_state.pop("web_search_results", None)
                except requests.exceptions.HTTPError:
                    show_api_error(response, "Search failed")
                except requests.exceptions.RequestException as e:
                    st.error(f"Request failed: {e}")

    if "local_search_result" in st.session_state:
        result = st.session_state["local_search_result"]

        if result is None:
            st.info("No recipes found in your local database yet.")
        else:
            quality = match_quality_label(result["distance"])
            st.success(f"Distance: {result['distance']:.2f} | Match Quality: {quality}")
            render_draft_preview(result)

            if st.button("Delete Recipe", key=f"delete_recipe_{result['id']}"):
                with st.spinner("Deleting recipe..."):
                    try:
                        del_response = api_session.delete(
                            f"{API_BASE_URL}/api/v1/recipes/{result['id']}",
                            timeout=30,
                        )
                        del_response.raise_for_status()
                        st.success(f"Deleted recipe #{result['id']}.")
                        st.session_state.pop("local_search_result", None)
                        st.rerun()
                    except requests.exceptions.HTTPError:
                        show_api_error(del_response, "Failed to delete recipe")
                    except requests.exceptions.RequestException as e:
                        st.error(f"Request failed: {e}")

        st.divider()
        st.markdown("**Not what you were looking for?**")
        if st.button("Search Web for this Query", key="search_web_button"):
            with st.spinner("Searching the web..."):
                try:
                    web_response = api_session.get(
                        f"{API_BASE_URL}/api/v1/recipes/search-web",
                        params={"query": search_query.strip()},
                        timeout=30,
                    )
                    web_response.raise_for_status()
                    st.session_state["web_search_results"] = web_response.json()
                except requests.exceptions.HTTPError:
                    show_api_error(web_response, "Web search failed")
                except requests.exceptions.RequestException as e:
                    st.error(f"Request failed: {e}")

    web_results = st.session_state.get("web_search_results")
    if web_results:
        st.markdown("**Web results**")
        for i, hit in enumerate(web_results):
            st.markdown(f"**[{hit['title']}]({hit['url']})**")
            st.caption(hit["snippet"])
            if st.button("Parse this Recipe", key=f"parse_web_result_{i}"):
                st.session_state["pending_recipe_url"] = hit["url"]
                st.session_state.pop("web_search_results", None)
                st.rerun()
            st.divider()

    st.divider()
    st.subheader("Browse All Recipes")

    BROWSE_PAGE_SIZE = 20
    st.session_state.setdefault("browse_page", 0)

    def fetch_browse_page():
        skip = st.session_state["browse_page"] * BROWSE_PAGE_SIZE
        response = api_session.get(
            f"{API_BASE_URL}/api/v1/recipes",
            params={"skip": skip, "limit": BROWSE_PAGE_SIZE},
            timeout=30,
        )
        response.raise_for_status()
        return response.json()

    try:
        library = fetch_browse_page()
    except requests.exceptions.RequestException as e:
        library = None
        st.error(f"Could not load recipe library: {e}")

    if library is not None:
        total = library["total"]
        items = library["items"]

        if total == 0:
            st.info("No recipes saved yet.")
        else:
            last_page = (total - 1) // BROWSE_PAGE_SIZE
            st.caption(f"{total} recipe{'s' if total != 1 else ''} — page {library['page']} of {last_page + 1}")

            for recipe in items:
                cook_time = recipe.get("cook_time_minutes")
                cook_time_label = f"{cook_time} min" if cook_time else "—"
                with st.container(border=True):
                    st.markdown(f"**{recipe.get('title', 'Untitled Recipe')}**")
                    st.caption(f"Cook time: {cook_time_label}")

                    with st.expander("Ingredients & Instructions"):
                        render_draft_preview(recipe)

                    if st.button("Delete Recipe", key=f"browse_delete_{recipe['id']}"):
                        with st.spinner("Deleting recipe..."):
                            try:
                                del_response = api_session.delete(
                                    f"{API_BASE_URL}/api/v1/recipes/{recipe['id']}",
                                    timeout=30,
                                )
                                del_response.raise_for_status()
                                st.success(f"Deleted recipe #{recipe['id']}.")
                                st.rerun()
                            except requests.exceptions.HTTPError:
                                show_api_error(del_response, "Failed to delete recipe")
                            except requests.exceptions.RequestException as e:
                                st.error(f"Request failed: {e}")

            nav_cols = st.columns(2)
            if nav_cols[0].button("Previous Page", disabled=st.session_state["browse_page"] <= 0):
                st.session_state["browse_page"] -= 1
                st.rerun()
            if nav_cols[1].button("Next Page", disabled=st.session_state["browse_page"] >= last_page):
                st.session_state["browse_page"] += 1
                st.rerun()

with meal_plan_tab:
    st.subheader("Weekly Menu Builder")

    MENU_SIZE = 6

    st.session_state.setdefault("menu_draft", [])
    st.session_state.setdefault("menu_finalizing", False)

    menu_draft = st.session_state["menu_draft"]
    menu_finalizing = st.session_state["menu_finalizing"]

    if len(menu_draft) < MENU_SIZE and not menu_finalizing:
        st.markdown(f"**Choose Meal {len(menu_draft) + 1} of {MENU_SIZE}**")

        find_col, finish_col = st.columns([3, 2])
        with find_col:
            slot_query = st.text_input(
                "What's this meal?",
                placeholder="e.g. quick weeknight soup",
                key="menu_slot_query",
            )
            find_clicked = st.button("Find Candidates", key="menu_find_candidates_button")
        with finish_col:
            st.write("")
            st.write("")
            if st.button(
                f"Finish Menu Early (Use Current {len(menu_draft)} Meals)",
                key="menu_finish_early_button",
                disabled=len(menu_draft) < 1,
            ):
                st.session_state["menu_finalizing"] = True
                st.rerun()

        if find_clicked:
            if not slot_query.strip():
                st.warning("Describe this meal slot first.")
            else:
                with st.spinner("Finding candidates..."):
                    try:
                        exclude_ids = ",".join(str(r["id"]) for r in menu_draft)
                        response = api_session.get(
                            f"{API_BASE_URL}/api/v1/menu/slot-candidates",
                            params={"q": slot_query.strip(), "exclude_ids": exclude_ids, "limit": 3},
                            timeout=30,
                        )
                        response.raise_for_status()
                        st.session_state["menu_slot_candidates"] = response.json()
                    except requests.exceptions.HTTPError:
                        show_api_error(response, "Failed to find candidates")
                    except requests.exceptions.RequestException as e:
                        st.error(f"Request failed: {e}")

        candidates = st.session_state.get("menu_slot_candidates")
        if candidates:
            st.markdown("**Candidates**")
            for candidate in candidates:
                recipe = candidate["recipe"]
                cook_time = recipe.get("cook_time_minutes")
                cook_time_label = f"{cook_time} min" if cook_time else "—"
                with st.container(border=True):
                    st.markdown(f"**{recipe.get('title', 'Untitled Recipe')}**")
                    st.caption(f"Cook time: {cook_time_label} | Match score: {candidate['final_score']:.2f}")
                    if st.button("+ Add to Menu", key=f"menu_add_candidate_{recipe['id']}"):
                        st.session_state["menu_draft"].append(recipe)
                        st.session_state.pop("menu_slot_candidates", None)
                        st.rerun()

        st.divider()
        st.markdown("**Or pick manually from your library**")

        MENU_BROWSE_PAGE_SIZE = 20
        st.session_state.setdefault("menu_browse_page", 0)

        def fetch_menu_browse_page():
            skip = st.session_state["menu_browse_page"] * MENU_BROWSE_PAGE_SIZE
            response = api_session.get(
                f"{API_BASE_URL}/api/v1/recipes",
                params={"skip": skip, "limit": MENU_BROWSE_PAGE_SIZE},
                timeout=30,
            )
            response.raise_for_status()
            return response.json()

        try:
            menu_library = fetch_menu_browse_page()
        except requests.exceptions.RequestException as e:
            menu_library = None
            st.error(f"Could not load recipe library: {e}")

        if menu_library is not None:
            total = menu_library["total"]
            items = menu_library["items"]
            draft_ids = {r["id"] for r in menu_draft}

            if total == 0:
                st.info("No recipes saved yet.")
            else:
                last_page = (total - 1) // MENU_BROWSE_PAGE_SIZE
                st.caption(
                    f"{total} recipe{'s' if total != 1 else ''} — page {menu_library['page']} of {last_page + 1}"
                )

                for recipe in items:
                    cook_time = recipe.get("cook_time_minutes")
                    cook_time_label = f"{cook_time} min" if cook_time else "—"
                    with st.container(border=True):
                        st.markdown(f"**{recipe.get('title', 'Untitled Recipe')}**")
                        st.caption(f"Cook time: {cook_time_label}")

                        if recipe["id"] in draft_ids:
                            st.caption("Already in this menu.")
                        elif st.button("+ Add to Menu", key=f"menu_browse_add_{recipe['id']}"):
                            st.session_state["menu_draft"].append(recipe)
                            st.rerun()

                nav_cols = st.columns(2)
                if nav_cols[0].button(
                    "Previous Page",
                    key="menu_browse_prev",
                    disabled=st.session_state["menu_browse_page"] <= 0,
                ):
                    st.session_state["menu_browse_page"] -= 1
                    st.rerun()
                if nav_cols[1].button(
                    "Next Page",
                    key="menu_browse_next",
                    disabled=st.session_state["menu_browse_page"] >= last_page,
                ):
                    st.session_state["menu_browse_page"] += 1
                    st.rerun()

    else:
        st.markdown("**Review Your Menu**")
        st.caption(f"{len(menu_draft)} meal{'s' if len(menu_draft) != 1 else ''} selected.")

        for i, recipe in enumerate(menu_draft):
            with st.container(border=True):
                title_col, remove_col = st.columns([4, 1])
                title_col.markdown(f"**{recipe.get('title', 'Untitled Recipe')}**")
                if remove_col.button("Remove", key=f"menu_remove_{recipe['id']}"):
                    st.session_state["menu_draft"].pop(i)
                    st.session_state["menu_finalizing"] = False
                    st.rerun()

        st.divider()
        if st.button("Confirm & Lock Menu", key="menu_confirm_button", type="primary"):
            with st.spinner("Saving menu..."):
                try:
                    response = api_session.post(
                        f"{API_BASE_URL}/api/v1/menu/confirm",
                        json={"recipe_ids": [r["id"] for r in menu_draft]},
                        timeout=30,
                    )
                    response.raise_for_status()
                    saved_menu = response.json()
                    st.success(f"Menu #{saved_menu['menu_number']} locked in with {len(menu_draft)} meals!")
                    st.session_state["menu_draft"] = []
                    st.session_state["menu_finalizing"] = False
                    st.session_state.pop("menu_slot_candidates", None)
                    st.rerun()
                except requests.exceptions.HTTPError:
                    show_api_error(response, "Failed to confirm menu")
                except requests.exceptions.RequestException as e:
                    st.error(f"Request failed: {e}")

with existing_menus_tab:
    st.subheader("Your Saved Menus")

    def open_shopping_list_dialog(menu_id, menu_number):
        @st.dialog(f"Shopping List - Menu #{menu_number}")
        def _dialog():
            with st.spinner("Generating shopping list..."):
                try:
                    response = api_session.get(
                        f"{API_BASE_URL}/api/v1/menus/{menu_id}/shopping-list",
                        timeout=60,
                    )
                    response.raise_for_status()
                    shopping_list = response.json()
                except requests.exceptions.HTTPError:
                    show_api_error(response, "Failed to load shopping list")
                    return
                except requests.exceptions.RequestException as e:
                    st.error(f"Request failed: {e}")
                    return

            copy_lines = [f"Shopping List - Menu #{menu_number}", ""]
            for category in shopping_list.get("categories", []):
                st.markdown(f"**{category['category']}**")
                copy_lines.append(f"{category['category']}:")
                for item in category.get("items", []):
                    unit = f" {item['unit']}" if item.get("unit") else ""
                    st.markdown(f"• {item['quantity']}{unit} {item['item']}")
                    copy_lines.append(f"- {item['quantity']}{unit} {item['item']}")
                    if item.get("sources"):
                        sources = ", ".join(item["sources"])
                        st.caption(f"(from: {sources})")
                copy_lines.append("")

            st.divider()
            st.caption("Copy for your notes app:")
            st.code("\n".join(copy_lines), language=None)

        _dialog()

    def fetch_all_menus():
        response = api_session.get(
            f"{API_BASE_URL}/api/v1/menus",
            params={"limit": 100, "skip": 0},
            timeout=30,
        )
        response.raise_for_status()
        return response.json()

    try:
        saved_menus = fetch_all_menus()
    except requests.exceptions.RequestException as e:
        saved_menus = None
        st.error(f"Could not load menus: {e}")

    if saved_menus is not None:
        if not saved_menus:
            st.info("No saved menus found. Create one in the Menu Builder tab.")
        else:
            saved_menus = sorted(saved_menus, key=lambda m: m["menu_number"], reverse=True)
            max_menu_number = saved_menus[0]["menu_number"]

            for menu in saved_menus:
                is_active = menu["menu_number"] == max_menu_number
                created_date = menu["created_at"][:10] if menu.get("created_at") else "unknown date"

                with st.container(border=True):
                    if is_active:
                        st.markdown("🟢 **Active Current Menu**")
                    st.markdown(f"**Menu #{menu['menu_number']} — Saved on {created_date}**")

                    for recipe in menu.get("recipes", []):
                        cook_time = recipe.get("cook_time_minutes")
                        cook_time_label = f"{cook_time} min" if cook_time else "—"
                        st.markdown(f"- {recipe['title']} ({cook_time_label})")

                    if st.button(
                        "View Shopping List",
                        key=f"view_shopping_list_{menu['id']}",
                        type="primary",
                    ):
                        open_shopping_list_dialog(menu["id"], menu["menu_number"])
