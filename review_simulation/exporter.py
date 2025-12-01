"""Helpers for exporting persona prompts and evaluation results."""
from __future__ import annotations

import json
from typing import Dict, List

from review_simulation.persona import ProductAffinity, ReviewPersona
from review_simulation.simulation import PersonaTurn, ProductJudgement, SimulationResult


PERSONA_EXPORT_COLUMNS = [
    "Brand",
    "Product",
    "Norm_Product",
    "Review",
    "ratings",
    "Rating",
    "date",
    "like_option",
    "dislike_option",
    "liked_options",
    "disliked_options",
    "user_intention",
    "mentioned_product_brands",
    "mentioned_product_names",
    "mentioned_normalize_product_names",
    "performance_tier",
    "newness_preference_score",
    "newness_preference_notes",
    "price_range",
    "openness_to_alternatives",
    "misc_notes",
    "persona_writing_style",
    "persona_interaction_style",
    "persona_family_background",
    "persona_goal_summary",
    "persona_query",
    "persona_upper_price_limit",
]


RESULT_EXPORT_COLUMNS = PERSONA_EXPORT_COLUMNS + [
    "precision_at_k",
    "satisfied_in_top_k",
    "infra_list_diversity",
    "ndcg_at_k",
    "extracted_filters",
    "implicit_preferences",
    "summary",
    "vehicle_judgements",
    "sql_query",
    "attribute_satisfaction_at_k",
    "overall_attribute_satisfaction",
]


def serialize_affinities(affinities: List[ProductAffinity]) -> str:
    """Convert affinity dataclasses into a JSON string."""

    return json.dumps(
        [
            {
                "product_brand": affinity.product_brand,
                "product_name": affinity.product_name,
                "normalize_product_name": affinity.normalize_product_name,
                "rationale": affinity.rationale,
            }
            for affinity in affinities
        ]
    )


def serialize_vehicle_judgements(judgements: List[ProductJudgement]) -> str:
    """Convert vehicle judgements into a JSON payload."""

    return json.dumps(
        [
            {
                "index": item.index,
                "product_brand": item.product_brand,
                "product_name": item.product_name,
                "normalize_product_name": item.normalize_product_name,
                "price": item.price,
                "satisfied": item.satisfied,
                "rationale": item.rationale,
                "confidence": item.confidence,
                "attribute_results": {
                    key: {
                        "satisfied": value.satisfied,
                        "rationale": value.rationale,
                    }
                    for key, value in (item.attribute_results or {}).items()
                },
            }
            for item in judgements
        ]
    )


def persona_to_row(persona: ReviewPersona, turn: PersonaTurn) -> Dict[str, object]:
    """Produce the base export row shared by generation and evaluation steps."""

    return {
        "Brand": persona.product_brand,
        "Product": persona.product_name,
        "Norm_Product": persona.normalize_product_name,
        "Review": persona.review,
        "ratings": persona.rating,
        "Rating": persona.rating,
        "date": persona.date,
        "like_option": serialize_affinities(persona.liked),
        "dislike_option": serialize_affinities(persona.disliked),
        "liked_options": serialize_affinities(persona.liked),
        "disliked_options": serialize_affinities(persona.disliked),
        "user_intention": persona.intention,
        "mentioned_product_brands": json.dumps(persona.mentioned_product_brands),
        "mentioned_product_names": json.dumps(persona.mentioned_product_names),
        "mentioned_normalize_product_names": json.dumps(
            persona.mentioned_normalize_product_names
        ),
        "performance_tier": persona.performance_tier,
        "newness_preference_score": persona.newness_preference_score,
        "newness_preference_notes": persona.newness_preference_notes,
        "price_range": persona.price_range,
        "openness_to_alternatives": persona.alternative_openness,
        "misc_notes": persona.misc_notes,
        "persona_writing_style": turn.writing_style,
        "persona_interaction_style": turn.interaction_style,
        "persona_family_background": turn.family_background,
        "persona_goal_summary": turn.goal_summary,
        "persona_query": turn.message,
        "persona_upper_price_limit": turn.upper_price_limit,
    }


def result_to_row(result: SimulationResult) -> Dict[str, object]:
    """Produce the final export row with evaluation metrics included."""

    row = persona_to_row(result.persona, result.persona_turn)
    metrics = result.metrics

    attribute_rates = [stat.rate for stat in result.metrics.attribute_satisfaction.values() if stat.rate is not None]
    overall_attribute_satisfaction = (
        sum(attribute_rates) / len(attribute_rates) if attribute_rates else None
    )

    row.update(
        {
            "precision_at_k": metrics.precision_at_k,
            "satisfied_in_top_k": metrics.satisfied_count,
            "infra_list_diversity": metrics.infra_list_diversity,
            "ndcg_at_k": metrics.ndcg_at_k,
            "extracted_filters": json.dumps(result.recommendation_response.get("extracted_filters")),
            "implicit_preferences": json.dumps(result.recommendation_response.get("implicit_preferences")),
            "summary": result.summary,
            "vehicle_judgements": serialize_vehicle_judgements(result.vehicles),
            "sql_query": result.recommendation_response.get("sql_query", None),
            "attribute_satisfaction_at_k": json.dumps(
                {
                    key: {
                        "satisfied_count": stats.satisfied_count,
                        "total_count": stats.total_count,
                        "rate": stats.rate,
                    }
                    for key, stats in result.metrics.attribute_satisfaction.items()
                }
            ),
            "overall_attribute_satisfaction": overall_attribute_satisfaction,
        }
    )
    return row
