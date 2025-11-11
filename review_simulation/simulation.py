"""Core logic for running review-driven single-turn simulations."""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from review_simulation.persona import ReviewPersona, VehicleAffinity
from scripts.test_recommendation_methods import (
    test_method1_pipeline,
    test_method2_pipeline,
)


@dataclass
class PersonaTurn:
    """Describes the simulated single-turn message for a persona."""

    message: str
    writing_style: str
    interaction_style: str
    family_background: str
    goal_summary: str


@dataclass
class VehicleJudgement:
    """Result of assessing a recommended vehicle."""

    index: int
    make: str
    model: str
    year: Optional[int]
    condition: str
    location: str
    vin: Optional[str]
    satisfied: bool
    rationale: str


@dataclass
class SimulationMetrics:
    precision_at_k: Optional[float]
    recall_at_k: Optional[float]
    satisfied_count: int


@dataclass
class SimulationResult:
    persona: ReviewPersona
    persona_turn: PersonaTurn
    vehicles: List[VehicleJudgement]
    metrics: SimulationMetrics
    recommendation_response: Dict[str, Any]


class PersonaDraft(BaseModel):
    writing_style: str
    interaction_style: str
    family_background: str
    goal_summary: str
    user_message: str


class VehicleAssessment(BaseModel):
    index: int = Field(..., description="1-based index of the vehicle in the presented list")
    satisfied: bool = Field(..., description="Whether the persona would be satisfied")
    rationale: str = Field(..., description="Short textual explanation")


class VehicleAssessmentList(BaseModel):
    assessments: List[VehicleAssessment]


PERSONA_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You craft single-turn user utterances for a car recommendation demo."
            "Read the reviewer's background and produce a concise, natural query."
            "Every generated query must restate the shopper's concrete preferences.",
        ),
        (
            "human",
            """
Review summary:
Make/Model owned or discussed: {make} {model}
Rating given: {rating}
Review excerpt: "{review}"
Likes: {likes}
Dislikes: {dislikes}
Stated intention: {intention}
Mentioned makes: {mentioned_makes}
Mentioned models: {mentioned_models}
Mentioned years: {mentioned_years}
Preferred condition: {preferred_condition}
Newness preference (1-10): {newness_preference_score} — {newness_preference_notes}
Preferred vehicle type: {preferred_vehicle_type}
Preferred fuel type: {preferred_fuel_type}
Openness to alternatives (1-10): {openness_to_alternatives}
Other priorities: {misc_notes}

Create a JSON object with keys writing_style, interaction_style, family_background,
goal_summary, and user_message. The user_message must be the exact text the
persona will send to the assistant in a single turn. It should reflect their
writing style and refer to their family/life context when appropriate. Keep it
under 120 words and avoid lists/bullets. In details:
- writing_style: A brief description of the user's writing style.
- interaction_style: A brief description of how the user prefers to interact.
- family_background: A brief summary of the user's family/life context relevant to car buying.
- goal_summary: A concise summary of the user's goal when interacting with a car recommendation agent.
- user_message: Must clearly mention the desired make/model (if any), relevant years, whether the car should be new or used, how
  new they want the search to be, body style, preferred fuel type, willingness to consider alternatives, and any additional
  priorities highlighted above.
""",
        ),
    ]
)


ASSESSMENT_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You evaluate car recommendations for a simulated shopper."
            "Decide if each vehicle matches the persona's expressed likes/dislikes."
            "Only use make, model, year, condition (new/used), body style, fuel type, and dealer location to judge."
            "Respect their newness preference scale and openness to alternatives when deciding satisfaction.",
        ),
        (
            "human",
            """
Persona goal: {goal_summary}
Writing style cues: {writing_style}
Interaction style: {interaction_style}
Family background: {family_background}
Likes: {likes}
Dislikes: {dislikes}
Mentioned makes: {mentioned_makes}
Mentioned models: {mentioned_models}
Mentioned years: {mentioned_years}
Preferred condition: {preferred_condition}
Newness preference (1-10): {newness_preference_score} — {newness_preference_notes}
Preferred vehicle type: {preferred_vehicle_type}
Preferred fuel type: {preferred_fuel_type}
Openness to alternatives (1-10): {openness_to_alternatives}
Other priorities: {misc_notes}

For each vehicle below decide if the persona would be satisfied. Respond with
JSON: {{"assessments": [{{"index": <number>, "satisfied": <bool>, "rationale": <string>}}, ...]}}.
Vehicles:
{vehicles}
""",
        ),
    ]
)


def _affinities_to_text(items: List[VehicleAffinity]) -> str:
    if not items:
        return "None"
    parts = []
    for item in items:
        attributes = []
        if item.make:
            attributes.append(item.make)
        if item.model:
            attributes.append(item.model)
        if item.year:
            attributes.append(str(item.year))
        if item.condition:
            attributes.append(item.condition)
        summary = " ".join(attributes) if attributes else "unspecified vehicle"
        if item.rationale:
            summary += f" ({item.rationale})"
        parts.append(summary)
    return "; ".join(parts)


def _list_to_text(values: List[str]) -> str:
    if not values:
        return "None"
    return ", ".join(values)


def _format_vehicle_entry(vehicle: dict, index: int) -> Dict[str, Optional[str]]:
    car = vehicle.get("vehicle", {}) if isinstance(vehicle, dict) else {}
    listing = vehicle.get("retailListing", {}) if isinstance(vehicle, dict) else {}

    make = car.get("make")
    model = car.get("model")
    year = car.get("year")
    if year is not None:
        try:
            year = int(year)
        except (TypeError, ValueError):
            year = None

    used_flag = listing.get("used")
    if used_flag is None:
        used_flag = vehicle.get("inventory_type") == "used"
    condition = "used" if used_flag else "new"

    city = listing.get("city") or vehicle.get("dealer_city")
    state = listing.get("state") or vehicle.get("dealer_state")
    location = ", ".join([part for part in [city, state] if part]) or "Unknown"

    return {
        "index": index,
        "make": make,
        "model": model,
        "year": year,
        "condition": condition,
        "location": location,
        "vin": vehicle.get("vin") or car.get("vin"),
    }


def build_persona_turn(persona: ReviewPersona, model: ChatOpenAI) -> PersonaTurn:
    structured_model = model.with_structured_output(PersonaDraft)
    likes_text = _affinities_to_text(persona.liked)
    dislikes_text = _affinities_to_text(persona.disliked)
    rating_text = persona.rating_value if persona.rating_value is not None else "unknown"

    prompt = PERSONA_PROMPT.format_prompt(
        make=persona.make,
        model=persona.model,
        rating=rating_text,
        review=persona.review,
        likes=likes_text,
        dislikes=dislikes_text,
        intention=persona.intention or "",
        mentioned_makes=_list_to_text(persona.mentioned_makes),
        mentioned_models=_list_to_text(persona.mentioned_models),
        mentioned_years=_list_to_text([str(year) for year in persona.mentioned_years]),
        preferred_condition=persona.preferred_condition or "unspecified",
        newness_preference_score=persona.newness_preference_score or "unknown",
        newness_preference_notes=persona.newness_preference_notes or "",
        preferred_vehicle_type=persona.preferred_vehicle_type or "unspecified",
        preferred_fuel_type=persona.preferred_fuel_type or "unspecified",
        openness_to_alternatives=persona.alternative_openness or "unknown",
        misc_notes=persona.misc_notes or "None stated",
    )
    draft = structured_model.invoke(prompt.to_messages())
    return PersonaTurn(
        message=draft.user_message.strip(),
        writing_style=draft.writing_style.strip(),
        interaction_style=draft.interaction_style.strip(),
        family_background=draft.family_background.strip(),
        goal_summary=draft.goal_summary.strip(),
    )


def _assess_vehicles(
    persona: ReviewPersona,
    persona_turn: PersonaTurn,
    vehicles: List[dict],
    model: ChatOpenAI,
) -> List[VehicleJudgement]:
    structured_model = model.with_structured_output(VehicleAssessmentList)
    likes_text = _affinities_to_text(persona.liked)
    dislikes_text = _affinities_to_text(persona.disliked)

    vehicle_entries = [_format_vehicle_entry(vehicle, idx + 1) for idx, vehicle in enumerate(vehicles)]
    prompt = ASSESSMENT_PROMPT.format_prompt(
        goal_summary=persona_turn.goal_summary,
        writing_style=persona_turn.writing_style,
        interaction_style=persona_turn.interaction_style,
        family_background=persona_turn.family_background,
        likes=likes_text,
        dislikes=dislikes_text,
        mentioned_makes=_list_to_text(persona.mentioned_makes),
        mentioned_models=_list_to_text(persona.mentioned_models),
        mentioned_years=_list_to_text([str(year) for year in persona.mentioned_years]),
        preferred_condition=persona.preferred_condition or "unspecified",
        newness_preference_score=persona.newness_preference_score or "unknown",
        newness_preference_notes=persona.newness_preference_notes or "",
        preferred_vehicle_type=persona.preferred_vehicle_type or "unspecified",
        preferred_fuel_type=persona.preferred_fuel_type or "unspecified",
        openness_to_alternatives=persona.alternative_openness or "unknown",
        misc_notes=persona.misc_notes or "None stated",
        vehicles=json.dumps(vehicle_entries, indent=2),
    )
    response = structured_model.invoke(prompt.to_messages())

    assessment_map = {item.index: item for item in response.assessments}

    results: List[VehicleJudgement] = []
    for entry in vehicle_entries:
        assessment = assessment_map.get(entry["index"])
        if assessment is None:
            # Default to dissatisfaction if the model omitted an entry.
            assessment = VehicleAssessment(index=entry["index"], satisfied=False, rationale="No evaluation")
        results.append(
            VehicleJudgement(
                index=entry["index"],
                make=entry.get("make"),
                model=entry.get("model"),
                year=entry.get("year"),
                condition=str(entry.get("condition")),
                location=str(entry.get("location")),
                vin=entry.get("vin"),
                satisfied=assessment.satisfied,
                rationale=assessment.rationale.strip(),
            )
        )
    return results


def _compute_metrics(judgements: List[VehicleJudgement], persona: ReviewPersona, k: int) -> SimulationMetrics:
    if k <= 0:
        return SimulationMetrics(precision_at_k=None, recall_at_k=None, satisfied_count=0)

    top_k = [j for j in judgements if j.index <= k]
    satisfied = [j for j in top_k if j.satisfied]
    precision = len(satisfied) / k if k else None

    positive_targets = [item for item in persona.liked if item.make or item.model or item.year]
    if positive_targets:
        recall = len(satisfied) / len(positive_targets)
    else:
        recall = None

    return SimulationMetrics(
        precision_at_k=precision,
        recall_at_k=recall,
        satisfied_count=len(satisfied),
    )


def run_simulation(
    persona: ReviewPersona,
    llm: ChatOpenAI,
    recommendation_limit: int = 20,
    metric_k: Optional[int] = None,
    recommendation_method: int = 1,
) -> SimulationResult:
    persona_turn = build_persona_turn(persona, llm)

    return evaluate_persona(
        persona,
        persona_turn,
        llm,
        recommendation_limit=recommendation_limit,
        metric_k=metric_k,
        recommendation_method=recommendation_method,
    )


def evaluate_persona(
    persona: ReviewPersona,
    persona_turn: PersonaTurn,
    llm: ChatOpenAI,
    recommendation_limit: int = 20,
    metric_k: Optional[int] = None,
    recommendation_method: int = 1,
) -> SimulationResult:

    if recommendation_method == 1:
        response = test_method1_pipeline(persona_turn.message)
    elif recommendation_method == 2:
        response = test_method2_pipeline(persona_turn.message)
    else:
        raise ValueError(
            "recommendation_method must be 1 or 2; received"
            f" {recommendation_method}"
        )
    vehicles = (response.get("recommended_vehicles") or [])[:recommendation_limit]

    judgements = _assess_vehicles(persona, persona_turn, vehicles, llm)
    metrics = _compute_metrics(judgements, persona, metric_k or recommendation_limit)

    return SimulationResult(
        persona=persona,
        persona_turn=persona_turn,
        vehicles=judgements,
        metrics=metrics,
        recommendation_response=response,
    )
