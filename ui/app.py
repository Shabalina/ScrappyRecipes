import os

import requests
import streamlit as st

API_BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8000")

st.set_page_config(page_title="Scrappy Recipes", layout="centered")
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
                response = requests.post(
                    f"{API_BASE_URL}/api/v1/recipes/confirm",
                    json=draft,
                    timeout=60,
                )
                response.raise_for_status()
                saved = response.json()
                st.success(f"Saved recipe #{saved['id']}: {saved['title']}")
                del st.session_state[session_key]
            except requests.exceptions.HTTPError:
                detail = response.json().get("detail", response.text)
                st.error(f"Failed to save recipe: {detail}")
            except requests.exceptions.RequestException as e:
                st.error(f"Request failed: {e}")


ingestion_tab, search_tab, meal_plan_tab = st.tabs(["Ingestion", "Search", "Meal Plan"])

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
                        response = requests.post(
                            f"{API_BASE_URL}/api/v1/recipes/parse-url",
                            json={"url": recipe_url.strip()},
                            timeout=60,
                        )
                        response.raise_for_status()
                        st.session_state["draft_recipe_url"] = response.json()
                    except requests.exceptions.HTTPError:
                        detail = response.json().get("detail", response.text)
                        st.error(f"Failed to parse recipe: {detail}")
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
                        response = requests.post(
                            f"{API_BASE_URL}/api/v1/recipes/parse-text",
                            json={"text": recipe_text.strip()},
                            timeout=60,
                        )
                        response.raise_for_status()
                        st.session_state["draft_recipe_text"] = response.json()
                    except requests.exceptions.HTTPError:
                        detail = response.json().get("detail", response.text)
                        st.error(f"Failed to parse recipe: {detail}")
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
                        response = requests.post(
                            f"{API_BASE_URL}/api/v1/recipes/parse-images",
                            files=files,
                            timeout=60,
                        )
                        response.raise_for_status()
                        st.session_state["draft_recipe_images"] = response.json()
                    except requests.exceptions.HTTPError:
                        detail = response.json().get("detail", response.text)
                        st.error(f"Failed to parse recipe: {detail}")
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
                    response = requests.get(
                        f"{API_BASE_URL}/api/v1/recipes/search",
                        params={"q": search_query.strip(), "limit": 1},
                        timeout=30,
                    )
                    response.raise_for_status()
                    results = response.json()
                    st.session_state["local_search_result"] = results[0] if results else None
                    st.session_state.pop("web_search_results", None)
                except requests.exceptions.HTTPError:
                    detail = response.json().get("detail", response.text)
                    st.error(f"Search failed: {detail}")
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
                        del_response = requests.delete(
                            f"{API_BASE_URL}/api/v1/recipes/{result['id']}",
                            timeout=30,
                        )
                        del_response.raise_for_status()
                        st.success(f"Deleted recipe #{result['id']}.")
                        st.session_state.pop("local_search_result", None)
                        st.rerun()
                    except requests.exceptions.HTTPError:
                        detail = del_response.json().get("detail", del_response.text)
                        st.error(f"Failed to delete recipe: {detail}")
                    except requests.exceptions.RequestException as e:
                        st.error(f"Request failed: {e}")

        st.divider()
        st.markdown("**Not what you were looking for?**")
        if st.button("Search Web for this Query", key="search_web_button"):
            with st.spinner("Searching the web..."):
                try:
                    web_response = requests.get(
                        f"{API_BASE_URL}/api/v1/recipes/search-web",
                        params={"query": search_query.strip()},
                        timeout=30,
                    )
                    web_response.raise_for_status()
                    st.session_state["web_search_results"] = web_response.json()
                except requests.exceptions.HTTPError:
                    detail = web_response.json().get("detail", web_response.text)
                    st.error(f"Web search failed: {detail}")
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

with meal_plan_tab:
    st.info("Coming soon.")
