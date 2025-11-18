"""Streamlit dashboard for reviewing enriched personas and evaluation outputs."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Dict

import streamlit as st

from review_simulation.dataset import load_enriched_reviews


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--dataset", default="review_simulation/data/enriched_reviews.csv")
    parser.add_argument("--results", default="review_simulation/data/evaluation.csv")
    args, _ = parser.parse_known_args()
    return args


def load_results(path: Path) -> Dict[str, Dict[str, object]]:
    if not path.exists():
        return {}
    rows: Dict[str, Dict[str, object]] = {}
    with path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows[row["review_id"]] = row
    return rows


def main() -> None:
    args = parse_args()
    dataset_path = Path(args.dataset)
    results_path = Path(args.results)

    st.set_page_config(page_title="Review Simulation Browser", layout="wide")
    st.title("Electronics Review Personas")

    try:
        reviews = load_enriched_reviews(dataset_path)
    except FileNotFoundError:
        st.error(f"Dataset not found: {dataset_path}")
        return

    results = load_results(results_path)

    review_ids = [review.review_id for review in reviews]
    selected_id = st.sidebar.selectbox("Persona", review_ids)
    selected_review = next(review for review in reviews if review.review_id == selected_id)

    st.sidebar.markdown("### Query")
    st.sidebar.write(selected_review.queries.primary)
    if selected_review.queries.alternates:
        st.sidebar.markdown("**Alternates**")
        for alt in selected_review.queries.alternates:
            st.sidebar.caption(alt)

    persona = selected_review.persona
    prefs = selected_review.preferences

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Persona Snapshot")
        st.write(persona.summary)
        st.json(
            {
                "brand": persona.brand,
                "product": persona.product,
                "norm_product": persona.norm_product,
                "rating": persona.rating,
                "date": persona.review_date,
                "source": persona.source,
                "performance": persona.performance,
                "newness": persona.newness,
                "price_range": persona.price_range,
                "openness_to_alternative": persona.openness_to_alternative,
            }
        )
        st.markdown("#### Mentioned likes")
        st.write(prefs.mentioned_like or "None")
        st.markdown("#### Mentioned dislikes")
        st.write(prefs.mentioned_dislike or "None")
        if prefs.mentioned_setup:
            st.markdown("#### Setup notes")
            st.write(prefs.mentioned_setup)

    with col2:
        st.subheader("Preference Bundles")
        st.markdown("**Explicit**")
        st.json(prefs.explicit)
        st.markdown("**Implicit**")
        st.json(prefs.implicit)

        if selected_id in results:
            st.subheader("Evaluation Result")
            row = results[selected_id]
            st.write(f"Method: {row['method']} · Products found: {row['products_found']}")
            product_block = {
                "product_name": row.get("top_product_name"),
                "product_brand": row.get("top_product_brand"),
                "price": row.get("top_price"),
                "price_text": row.get("top_price_text"),
                "_vector_score": row.get("vector_score"),
            }
            st.json(product_block)
            st.caption(
                f"Alignment — brand: {row['brand_alignment']}, product: {row['product_alignment']}, price present: {row['price_presence']}"
            )
        else:
            st.info("No evaluation output available for this persona yet.")


if __name__ == "__main__":
    main()
