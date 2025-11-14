"""Helpers for exporting persona prompts and evaluation results."""
from __future__ import annotations

import json
from typing import Dict, List

from review_simulation.persona import ReviewPersona, VehicleAffinity
from review_simulation.simulation import PersonaTurn, SimulationResult, VehicleJudgement


PERSONA_EXPORT_COLUMNS = [
    "Make",
    "Model",
    "Review",
    "ratings",
    "Rating",
    "date",
    "like_option",
    "dislike_option",
    "liked_options",
    "disliked_options",
    "user_intention",
    "mentioned_makes",
    "mentioned_models",
    "mentioned_years",
    "preferred_condition",
    "newness_preference_score",
    "newness_preference_notes",
    "preferred_vehicle_type",
    "preferred_fuel_type",
    "openness_to_alternatives",
    "misc_notes",
    "persona_writing_style",
    "persona_interaction_style",
    "persona_family_background",
    "persona_goal_summary",
    "persona_query",
]


RESULT_EXPORT_COLUMNS = PERSONA_EXPORT_COLUMNS + [
    "precision_at_k",
    "recall_at_k",
    "satisfied_in_top_k",
    "vehicle_judgements",
    "sql_query",
]


def serialize_affinities(affinities: List[VehicleAffinity]) -> str:
    """Convert affinity dataclasses into a JSON string."""

    return json.dumps(
        [
            {
                "make": affinity.make,
                "model": affinity.model,
                "year": affinity.year,
                "condition": affinity.condition,
                "rationale": affinity.rationale,
            }
            for affinity in affinities
        ]
    )


def serialize_vehicle_judgements(judgements: List[VehicleJudgement]) -> str:
    """Convert vehicle judgements into a JSON payload."""

    return json.dumps(
        [
            {
                "index": item.index,
                "make": item.make,
                "model": item.model,
                "year": item.year,
                "condition": item.condition,
                "location": item.location,
                "vin": item.vin,
                "satisfied": item.satisfied,
                "rationale": item.rationale,
            }
            for item in judgements
        ]
    )


def persona_to_row(persona: ReviewPersona, turn: PersonaTurn) -> Dict[str, object]:
    """Produce the base export row shared by generation and evaluation steps."""

    return {
        "Make": persona.make,
        "Model": persona.model,
        "Review": persona.review,
        "ratings": persona.rating,
        "Rating": persona.rating,
        "date": persona.date,
        "like_option": serialize_affinities(persona.liked),
        "dislike_option": serialize_affinities(persona.disliked),
        "liked_options": serialize_affinities(persona.liked),
        "disliked_options": serialize_affinities(persona.disliked),
        "user_intention": persona.intention,
        "mentioned_makes": json.dumps(persona.mentioned_makes),
        "mentioned_models": json.dumps(persona.mentioned_models),
        "mentioned_years": json.dumps(persona.mentioned_years),
        "preferred_condition": persona.preferred_condition,
        "newness_preference_score": persona.newness_preference_score,
        "newness_preference_notes": persona.newness_preference_notes,
        "preferred_vehicle_type": persona.preferred_vehicle_type,
        "preferred_fuel_type": persona.preferred_fuel_type,
        "openness_to_alternatives": persona.alternative_openness,
        "misc_notes": persona.misc_notes,
        "persona_writing_style": turn.writing_style,
        "persona_interaction_style": turn.interaction_style,
        "persona_family_background": turn.family_background,
        "persona_goal_summary": turn.goal_summary,
        "persona_query": turn.message,
    }


def result_to_row(result: SimulationResult) -> Dict[str, object]:
    """Produce the final export row with evaluation metrics included."""

    row = persona_to_row(result.persona, result.persona_turn)
    metrics = result.metrics

    row.update(
        {
            "precision_at_k": metrics.precision_at_k,
            "recall_at_k": metrics.recall_at_k,
            "satisfied_in_top_k": metrics.satisfied_count,
            "vehicle_judgements": serialize_vehicle_judgements(result.vehicles),
            "sql_query": result.recommendation_response.get("sql_query", None),
        }
    )
    return row
