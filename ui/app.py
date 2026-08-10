import os

import requests
import streamlit as st

API_BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8000")

st.set_page_config(page_title="Scrappy Recipes", layout="centered")
st.title("Scrappy Recipes")


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

        recipe_url = st.text_input("Recipe URL", placeholder="https://example.com/my-recipe")

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
    st.info("Coming soon.")

with meal_plan_tab:
    st.info("Coming soon.")
