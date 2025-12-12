"""Core logic for running review-driven single-turn simulations."""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from review_simulation.persona import ReviewPersona, VehicleAffinity
from scripts.test_recommendation_methods import (
    test_method1_pipeline,
    test_method2_pipeline,
    test_method3_pipeline,
)


@dataclass
class PersonaTurn:
    """Describes the simulated single-turn message for a persona."""

    message: str
    writing_style: str
    interaction_style: str
    family_background: str
    goal_summary: str
    upper_price_limit: Optional[float] = None


@dataclass
class AttributeJudgement:
    """Result of assessing a specific vehicle attribute."""

    satisfied: Optional[bool]
    rationale: Optional[str]


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
    price: Optional[float]
    satisfied: bool
    rationale: str
    attribute_results: Dict[str, AttributeJudgement]
    confidence: Optional[float]


@dataclass
class SimulationMetrics:
    precision_at_k: Optional[float]
    precision_at_k_confident: Optional[float]
    satisfied_count: int
    infra_list_diversity: Optional[float]
    ndcg_at_k: Optional[float]
    ndcg_at_k_confident: Optional[float]
    attribute_satisfaction: Dict[str, "AttributeSatisfaction"]


@dataclass
class AttributeSatisfaction:
    """Aggregate satisfaction data for a single attribute."""

    satisfied_count: int
    total_count: int

    @property
    def rate(self) -> Optional[float]:
        if self.total_count == 0:
            return None
        return self.satisfied_count / self.total_count


@dataclass
class SimulationResult:
    persona: ReviewPersona
    persona_turn: PersonaTurn
    vehicles: List[VehicleJudgement]
    metrics: SimulationMetrics
    recommendation_response: Dict[str, Any]
    summary: str


class PersonaDraft(BaseModel):
    writing_style: str
    interaction_style: str
    family_background: str
    goal_summary: str
    user_message: str
    upper_price_limit: Optional[float]


class AttributeAssessment(BaseModel):
    satisfied: Optional[bool] = Field(
        None, description="Whether this attribute matches the persona preferences (None if not mentioned)"
    )
    rationale: Optional[str] = Field(
        None, description="<=10 words explaining the decision or None if not evaluated"
    )


class VehicleAssessment(BaseModel):
    index: int = Field(..., description="1-based index of the vehicle in the presented list")
    satisfied: bool = Field(..., description="Whether the persona would be satisfied overall")
    rationale: str = Field(..., description="Short textual explanation")
    confidence: Optional[float] = Field(
        None,
        description="Confidence in the overall satisfaction judgement between 0 and 1",
        ge=0.0,
        le=1.0,
    )
    price: Optional[AttributeAssessment] = None
    condition: Optional[AttributeAssessment] = None
    year: Optional[AttributeAssessment] = None
    make: Optional[AttributeAssessment] = None
    model: Optional[AttributeAssessment] = None
    fuel_type: Optional[AttributeAssessment] = None
    body_type: Optional[AttributeAssessment] = None
    all_misc: Optional[AttributeAssessment] = None


class VehicleAssessmentList(BaseModel):
    assessments: List[VehicleAssessment]


class SummaryResponse(BaseModel):
    satisfied_summary: str = Field(
        ..., description="One-sentence reason the persona would be satisfied with the list"
    )
    unsatisfied_summary: str = Field(
        ..., description="One-sentence reason the persona would be unsatisfied with the list"
    )


PERSONA_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You craft single-turn user utterances for a car recommendation demo."
            "Read the reviewer's background and produce a concise, natural query."
            "Every generated query must restate the shopper's concrete preferences."
            "Identify the highest price the shopper would pay and include it.",
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
Current year is 2025 (assume this for the most newness context).

Create a JSON object with keys writing_style, interaction_style, family_background,
goal_summary, upper_price_limit, and user_message. The user_message must be the exact text the
persona will send to the assistant in a single turn. It should reflect their
writing style and refer to their family/life context when appropriate. Keep it
under 120 words and avoid lists/bullets. In details:
- writing_style: A brief description of the user's writing style.
- interaction_style: A brief description of how the user prefers to interact.
- family_background: A brief summary of the user's family/life context relevant to car buying.
- goal_summary: A concise summary of the user's goal when interacting with a car recommendation agent.
- upper_price_limit: Your best estimate of the shopper's maximum acceptable price in USD (numbers only). Use null if unknown.
- user_message: Must clearly mention the desired make/model (if any), relevant years, whether the car should be new or used, how
  new they want the search to be, body style, preferred fuel type, willingness to consider alternatives, the maximum price to pay,
  and any additional priorities highlighted above.
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
            "Only use make, model, year, condition (new/used), body style, fuel type, and price to judge."
            "All vehicle information provided is accurate. DO NOT override them with assumptions. Use it to make informed judgements."
            "Return concise rationales (10 words or fewer).",
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
Persona query: {persona_query}
Mentioned makes: {mentioned_makes}
Mentioned models: {mentioned_models}
Mentioned years: {mentioned_years}
Preferred condition: {preferred_condition}
Newness preference (1-10): {newness_preference_score} — {newness_preference_notes}
Preferred vehicle type: {preferred_vehicle_type}
Preferred fuel type: {preferred_fuel_type}
Openness to alternatives (1-10): {openness_to_alternatives}
Other priorities: {misc_notes}
Current year is 2025 (assume this for the most newness context).
Do NOT make assumptions beyond the provided information. Only use the data given to make your judgements.
Do NOT assume the modernity of the vehicle beyond the year provided (The closer the year to 2025, the newer and more modern the vehicle).
Do NOT make assumptions about the make or model beyond what is explicitly given.
Only consider the information given in the Persona Query and the vehicle details provided to evaluate satisfaction.
Use the rest of the information only as a guideline, as they might not reflect the actual preferences expressed in the Persona Query.

For each vehicle below decide if the persona would be satisfied. Judge only the
criteria explicitly mentioned in the persona_query; if a criterion was not
mentioned, return null for that criterion. Respond with JSON using this shape:
{{"assessments": [{{"index": <number>, "satisfied": <bool>, "rationale": <string>, "confidence": <float 0-1>,
"condition": {{...}}, "year": {{...}},
"make": {{...}}, "model": {{...}}, "fuel_type": {{...}}, "body_type": {{...}}, "all_misc": {{...}}}}, ...]}}.
In details, for each attribute, to determine overall satisfaction, consider:
condition: (whether the condition satisfies the users' preference in the query or not. 
If the users are fine with both new and used or do not have preferences, return True).
year: (whether the year satisfies the users' preference in the query or not. If the users are fine with alternatives, return True.).
make: (whether the make satisfies the users' preference in the query or not. If the users are fine with alternatives, return True.).
model: (whether the model satisfies the users' preference in the query or not. If the users are fine with alternatives, return True.).
fuel_type: (whether the Fuel Type satisfies the users' preference in the query or not. 
Do NOT assume fuel efficiency in here, only compare fuel_type. 
For example, if the query wants Gasoline, and the fuel_type returns Gasoline, 
Premium Unleaded, E85, or any other type of Gasoline, return True. Return None if there is no mention of fuel type in the query).
body_type: (whether the body type satisfies the users' preference in the query or not, return None if there is no mention of body type in the query. If the users are fine with alternatives, return True.).
all_misc: (whether others' preference of the users mentioned in the query satisfies the users' query or not. The preference checks are safetyness and luxury. 
. Only return value if there is an obvious mismatch with the highest confidence level, else return None. Example of obvious mismatch: user wants family SUV, but return industrial trucks.).
For satisfied: only return true/false for each attribute when persona_query mentions it; otherwise set
that attribute to null. Use the provided price judgement included with each vehicle entry instead of recalculating price fit.
Confidence should be a number between 0 and 1 indicating how confident you are in the overall satisfaction judgement.
If there are a lot of conflicts between attributes and the final satisfaction judgement, the confidence score should be lower.
Vice versa, if there are a lot of attributes that align with the final satisfaction judgement, the confidence score should be higher.
The delta of confidence should be proportional to the number of attributes that align with the final satisfaction judgement.
Vehicles:
{vehicles}
""",
        ),
    ]
)


SUMMARY_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You condense vehicle satisfaction rationales into concise summaries."
            "Return JSON with two short sentences describing why the persona is satisfied or unsatisfied."
        ),
        (
            "human",
            """
Satisfied rationales:
{satisfied_reasons}

Unsatisfied rationales:
{unsatisfied_reasons}

Respond with JSON {{"satisfied_summary": <string>, "unsatisfied_summary": <string>}}.
Each value must be a single short sentence (no more than 20 words).
If there are no reasons, respond None.
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
    build = vehicle.get("build", {}) if isinstance(vehicle, dict) else {}

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

    price = listing.get("price")
    if price is None:
        price = listing.get("list_price") or vehicle.get("price")
    try:
        price = float(price) if price is not None else None
    except (TypeError, ValueError):
        price = None
    miles = listing.get("miles")
    fuel_type = car.get("fuel") or build.get("fuel_type")
    body_type = car.get("bodyStyle") or build.get("body_type")


    return {
        "index": index,
        "make": make,
        "model": model,
        "year": year,
        "condition": condition,
        "location": location,
        "vin": vehicle.get("vin") or car.get("vin"),
        "price": price,
        "miles": miles,
        "fuel_type": fuel_type,
        "body_type": body_type,
    }


def _determine_price_judgement(
    upper_price_limit: Optional[float], vehicle_price: Optional[float]
) -> AttributeJudgement:
    """Return a deterministic price satisfaction judgement.

    If either value is missing, no judgement is made. Otherwise satisfied is
    True when the persona's extracted price ceiling is greater than or equal to
    the vehicle's price.
    """

    if upper_price_limit is None or vehicle_price is None:
        return AttributeJudgement(satisfied=None, rationale=None)

    if upper_price_limit >= vehicle_price:
        return AttributeJudgement(
            satisfied=True,
            rationale=f"Within budget: {vehicle_price} <= {upper_price_limit}",
        )

    return AttributeJudgement(
        satisfied=False,
        rationale=f"Over budget: {vehicle_price} > {upper_price_limit}",
    )


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
        upper_price_limit=draft.upper_price_limit,
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

    vehicle_entries = []
    price_judgements: Dict[int, AttributeJudgement] = {}
    for idx, vehicle in enumerate(vehicles):
        entry = _format_vehicle_entry(vehicle, idx + 1)
        price_judgement = _determine_price_judgement(
            persona_turn.upper_price_limit, entry.get("price")
        )
        entry["price_judgement"] = {
            "satisfied": price_judgement.satisfied,
            "rationale": price_judgement.rationale,
        }
        vehicle_entries.append(entry)
        price_judgements[entry["index"]] = price_judgement
    prompt = ASSESSMENT_PROMPT.format_prompt(
        goal_summary=persona_turn.goal_summary,
        writing_style=persona_turn.writing_style,
        interaction_style=persona_turn.interaction_style,
        family_background=persona_turn.family_background,
        likes=likes_text,
        dislikes=dislikes_text,
        persona_query=persona_turn.message,
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
    attribute_keys = [
        "price",
        "condition",
        "year",
        "make",
        "model",
        "fuel_type",
        "body_type",
        "all_misc",
    ]

    def _attribute_judgement(value: Optional[AttributeAssessment]) -> AttributeJudgement:
        if value is None:
            return AttributeJudgement(satisfied=None, rationale=None)
        return AttributeJudgement(
            satisfied=value.satisfied,
            rationale=value.rationale.strip() if value.rationale else None,
        )

    for entry in vehicle_entries:
        assessment = assessment_map.get(entry["index"])
        if assessment is None:
            # Default to dissatisfaction if the model omitted an entry.
            assessment = VehicleAssessment(index=entry["index"], satisfied=False, rationale="No evaluation")
        attribute_results = {
            key: _attribute_judgement(getattr(assessment, key)) for key in attribute_keys
        }
        attribute_results["price"] = price_judgements.get(
            entry["index"], AttributeJudgement(satisfied=None, rationale=None)
        )
        results.append(
            VehicleJudgement(
                index=entry["index"],
                make=entry.get("make"),
                model=entry.get("model"),
                year=entry.get("year"),
                condition=str(entry.get("condition")),
                location=str(entry.get("location")),
                vin=entry.get("vin"),
                price=entry.get("price"),
                satisfied=assessment.satisfied,
                rationale=assessment.rationale.strip(),
                attribute_results=attribute_results,
                confidence=assessment.confidence,
            )
        )
    return results


def _compute_metrics(judgements: List[VehicleJudgement], persona: ReviewPersona, k: int) -> SimulationMetrics:
    _ = persona
    if k <= 0:
        return SimulationMetrics(
            precision_at_k=None,
            precision_at_k_confident=None,
            satisfied_count=0,
            infra_list_diversity=None,
            ndcg_at_k=None,
            ndcg_at_k_confident=None,
            attribute_satisfaction={},
        )

    top_k = [j for j in judgements if j.index <= k]
    if not top_k:
        return SimulationMetrics(
            precision_at_k=None,
            precision_at_k_confident=None,
            satisfied_count=0,
            infra_list_diversity=None,
            ndcg_at_k=None,
            ndcg_at_k_confident=None,
            attribute_satisfaction={},
        )

    satisfied = [j for j in top_k if j.satisfied]
    precision = len(satisfied) / len(top_k)

    confident_top_k = [j for j in top_k if j.confidence is not None and j.confidence > 0.6]
    if confident_top_k:
        confident_satisfied = [j for j in confident_top_k if j.satisfied]
        precision_confident = len(confident_satisfied) / len(confident_top_k)
    else:
        precision_confident = None

    make_models = [
        (str(j.make).strip().lower() if j.make else "", str(j.model).strip().lower() if j.model else "")
        for j in top_k
    ]
    unique_make_models = {item for item in make_models if any(item)}
    infra_list_diversity = None
    infra_list_diversity = len(unique_make_models) / len(top_k)

    def _dcg(items: List[VehicleJudgement]) -> float:
        value = 0.0
        for idx, judgement in enumerate(items, start=1):
            rel = 1.0 if judgement.satisfied else 0.0
            if rel == 0.0:
                continue
            value += (2 ** rel - 1) / math.log2(idx + 1)
        return value

    dcg = _dcg(top_k)
    ideal_count = min(len(satisfied), len(top_k))
    ideal_items = top_k[:]
    ideal_items.sort(key=lambda item: item.satisfied, reverse=True)
    idcg = _dcg(ideal_items[:ideal_count])
    if idcg:
        ndcg = dcg / idcg
    else:
        ndcg = 0.0 if not satisfied else None

    confident_dcg = _dcg(confident_top_k)
    confident_ideal_count = min(
        len(confident_top_k), len([j for j in confident_top_k if j.satisfied])
    )
    confident_ideal_items = confident_top_k[:]
    confident_ideal_items.sort(key=lambda item: item.satisfied, reverse=True)
    confident_idcg = _dcg(confident_ideal_items[:confident_ideal_count])
    if confident_idcg:
        ndcg_confident = confident_dcg / confident_idcg
    elif confident_top_k:
        ndcg_confident = 0.0 if not confident_satisfied else None
    else:
        ndcg_confident = None

    attribute_satisfaction: Dict[str, AttributeSatisfaction] = {}
    for judgement in top_k:
        for attribute, outcome in judgement.attribute_results.items():
            if outcome.satisfied is None:
                continue
            current = attribute_satisfaction.get(attribute) or AttributeSatisfaction(
                satisfied_count=0, total_count=0
            )
            current.total_count += 1
            if outcome.satisfied:
                current.satisfied_count += 1
            attribute_satisfaction[attribute] = current

    return SimulationMetrics(
        precision_at_k=precision,
        precision_at_k_confident=precision_confident,
        satisfied_count=len(satisfied),
        infra_list_diversity=infra_list_diversity,
        ndcg_at_k=ndcg,
        ndcg_at_k_confident=ndcg_confident,
        attribute_satisfaction=attribute_satisfaction,
    )


def _summarize_judgements(
    judgements: List[VehicleJudgement], model: ChatOpenAI
) -> str:
    satisfied_reasons = [j.rationale for j in judgements if j.satisfied and j.rationale]
    unsatisfied_reasons = [j.rationale for j in judgements if not j.satisfied and j.rationale]

    if not satisfied_reasons and not unsatisfied_reasons:
        return "No rationales provided."

    structured_model = model.with_structured_output(SummaryResponse)
    satisfied_text = (
        "\n".join(f"- {reason}" for reason in satisfied_reasons) or "None"
    )
    unsatisfied_text = (
        "\n".join(f"- {reason}" for reason in unsatisfied_reasons) or "None"
    )
    prompt = SUMMARY_PROMPT.format_prompt(
        satisfied_reasons=satisfied_text,
        unsatisfied_reasons=unsatisfied_text,
    )
    response = structured_model.invoke(prompt.to_messages())

    parts: List[str] = []
    if response.satisfied_summary:
        parts.append(f"Satisfied: {response.satisfied_summary.strip()}")
    if response.unsatisfied_summary:
        parts.append(f"Unsatisfied: {response.unsatisfied_summary.strip()}")
    if not parts:
        return "Summary unavailable."
    return " | ".join(parts)


def run_simulation(
    persona: ReviewPersona,
    llm: ChatOpenAI,
    recommendation_limit: int = 20,
    metric_k: Optional[int] = None,
    recommendation_method: int = 1,
    confidence_threshold: float = 0.5,
    max_assessment_attempts: int = 3,
) -> SimulationResult:
    persona_turn = build_persona_turn(persona, llm)

    return evaluate_persona(
        persona,
        persona_turn,
        llm,
        recommendation_limit=recommendation_limit,
        metric_k=metric_k,
        recommendation_method=recommendation_method,
        confidence_threshold=confidence_threshold,
        max_assessment_attempts=max_assessment_attempts,
    )


def evaluate_persona(
    persona: ReviewPersona,
    persona_turn: PersonaTurn,
    llm: ChatOpenAI,
    recommendation_limit: int = 20,
    metric_k: Optional[int] = None,
    recommendation_method: int = 1,
    confidence_threshold: float = 0.5,
    max_assessment_attempts: int = 3,
) -> SimulationResult:

    if recommendation_method == 1:
        response = test_method1_pipeline(persona_turn.message)
    elif recommendation_method == 2:
        response = test_method2_pipeline(persona_turn.message)
    elif recommendation_method == 3:
        response = test_method3_pipeline(persona_turn.message)
    else:
        raise ValueError(
            "recommendation_method must be 1, 2, or 3; received"
            f" {recommendation_method}"
        )
    vehicles = (response.get("recommended_vehicles") or [])[:recommendation_limit]

    judgements = _assess_vehicles(persona, persona_turn, vehicles, llm)
    attempts: List[List[VehicleJudgement]] = [judgements]

    def _avg_confidence(items: List[VehicleJudgement]) -> Optional[float]:
        confidences = [j.confidence for j in items if j.confidence is not None]
        if not confidences:
            return None
        return sum(confidences) / len(confidences)

    def _select_majority(attempt_sets: List[List[VehicleJudgement]]) -> List[VehicleJudgement]:
        if not attempt_sets:
            return []

        by_index: Dict[int, List[VehicleJudgement]] = {}
        for attempt in attempt_sets:
            for judgement in attempt:
                by_index.setdefault(judgement.index, []).append(judgement)

        final: List[VehicleJudgement] = []
        for index, entries in sorted(by_index.items()):
            true_count = sum(1 for entry in entries if entry.satisfied is True)
            false_count = sum(1 for entry in entries if entry.satisfied is False)
            if true_count > false_count:
                majority_value: Optional[bool] = True
            elif false_count > true_count:
                majority_value = False
            else:
                majority_value = None

            def _confidence_score(entry: VehicleJudgement) -> float:
                return entry.confidence if entry.confidence is not None else -1.0

            candidates = (
                [entry for entry in entries if entry.satisfied == majority_value]
                if majority_value is not None
                else entries
            )
            selected = max(candidates or entries, key=_confidence_score)
            final.append(selected)

        return sorted(final, key=lambda item: item.index)

    best_confidence = _avg_confidence(judgements)
    threshold_met = best_confidence is not None and best_confidence >= confidence_threshold

    remaining_attempts = max_assessment_attempts - 1
    while not threshold_met and remaining_attempts > 0:
        new_attempt = _assess_vehicles(persona, persona_turn, vehicles, llm)
        attempts.append(new_attempt)
        attempt_confidence = _avg_confidence(new_attempt)
        if attempt_confidence is not None and attempt_confidence >= confidence_threshold:
            judgements = new_attempt
            threshold_met = True
            best_confidence = attempt_confidence
            break
        if best_confidence is None or (
            attempt_confidence is not None and attempt_confidence > best_confidence
        ):
            judgements = new_attempt
            best_confidence = attempt_confidence
        remaining_attempts -= 1

    if not threshold_met:
        judgements = _select_majority(attempts)

    metrics = _compute_metrics(judgements, persona, metric_k or recommendation_limit)
    summary = _summarize_judgements(judgements, llm)

    return SimulationResult(
        persona=persona,
        persona_turn=persona_turn,
        vehicles=judgements,
        metrics=metrics,
        recommendation_response=response,
        summary=summary,
    )
