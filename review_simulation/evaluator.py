"""Single-turn evaluation harness for electronics review personas."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Callable, Dict, List

from scripts.test_recommendation_methods import (
    test_method1_pipeline,
    test_method2_pipeline,
)

from .dataset import load_enriched_reviews
from .models import EnrichedReview

MethodFn = Callable[[str], Dict[str, object]]


METHODS: Dict[str, MethodFn] = {
    "1": test_method1_pipeline,
    "2": test_method2_pipeline,
}


def _resolve_method(method: str) -> MethodFn:
    try:
        return METHODS[method]
    except KeyError as exc:
        raise ValueError(f"Unknown method '{method}'. Choose from {sorted(METHODS)}") from exc


def _summarize_product(product: Dict[str, object]) -> Dict[str, object]:
    if not product:
        return {}
    price_value = product.get("price_value") or product.get("price")
    if isinstance(price_value, str):
        try:
            price_value = float(price_value.replace("$", ""))
        except ValueError:
            price_value = None
    return {
        "product_id": product.get("id") or product.get("product", {}).get("id"),
        "product_name": product.get("product_name") or product.get("title") or product.get("product", {}).get("title"),
        "product_brand": product.get("product_brand")
        or product.get("brand")
        or product.get("product", {}).get("brand"),
        "price": price_value,
        "price_text": product.get("price_text") or product.get("price"),
        "vector_score": product.get("_vector_score"),
        "source": product.get("source") or product.get("_source"),
        "link": product.get("link"),
    }


def _score_alignment(sample: EnrichedReview, product: Dict[str, object]) -> Dict[str, object]:
    if not product:
        return {
            "brand_alignment": 0,
            "product_alignment": 0,
            "price_presence": False,
            "vector_score": None,
        }

    persona = sample.persona
    brand_match = 1 if persona.brand and product.get("product_brand", "").lower().startswith(persona.brand.lower()) else 0
    product_name = product.get("product_name") or ""
    norm_product = persona.norm_product.lower()
    product_alignment = 1 if norm_product and norm_product in product_name.lower() else 0
    price_presence = product.get("price") is not None or bool(product.get("price_text"))

    vector_score = product.get("vector_score")
    return {
        "brand_alignment": brand_match,
        "product_alignment": product_alignment,
        "price_presence": price_presence,
        "vector_score": vector_score,
    }


def evaluate_sample(sample: EnrichedReview, method_fn: MethodFn) -> Dict[str, object]:
    result = method_fn(sample.queries.primary)
    top_product = result.get("recommended_products", [None])[0] if result.get("recommended_products") else None
    summary = _summarize_product(top_product or {})
    alignment = _score_alignment(sample, summary)

    return {
        "review_id": sample.review_id,
        "query": sample.queries.primary,
        "method": result.get("method"),
        "products_found": result.get("products_found", 0),
        "top_product": summary,
        "alignment": alignment,
        "explicit_preferences": sample.preferences.explicit,
        "implicit_preferences": sample.preferences.implicit,
        "persona_summary": sample.persona.summary,
    }


def run_single_turn_evaluations(
    dataset_path: Path | str,
    output_csv: Path | str,
    method: str = "1",
) -> List[Dict[str, object]]:
    """Evaluate all queries in the dataset using the selected recommendation method."""

    method_fn = _resolve_method(method)
    samples = load_enriched_reviews(dataset_path)
    results = [evaluate_sample(sample, method_fn) for sample in samples]

    fieldnames = [
        "review_id",
        "method",
        "query",
        "products_found",
        "top_product_name",
        "top_product_brand",
        "top_price",
        "top_price_text",
        "vector_score",
        "brand_alignment",
        "product_alignment",
        "price_presence",
        "explicit_preferences",
        "implicit_preferences",
        "persona_summary",
    ]

    output_path = Path(output_csv)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for result in results:
            product = result["top_product"]
            alignment = result["alignment"]
            writer.writerow(
                {
                    "review_id": result["review_id"],
                    "method": result["method"],
                    "query": result["query"],
                    "products_found": result["products_found"],
                    "top_product_name": product.get("product_name"),
                    "top_product_brand": product.get("product_brand"),
                    "top_price": product.get("price"),
                    "top_price_text": product.get("price_text"),
                    "vector_score": product.get("vector_score"),
                    "brand_alignment": alignment["brand_alignment"],
                    "product_alignment": alignment["product_alignment"],
                    "price_presence": alignment["price_presence"],
                    "explicit_preferences": json.dumps(result["explicit_preferences"], ensure_ascii=False),
                    "implicit_preferences": json.dumps(result["implicit_preferences"], ensure_ascii=False),
                    "persona_summary": result["persona_summary"],
                }
            )

    return results
