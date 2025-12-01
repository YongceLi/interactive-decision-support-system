"""Core logic for running review-driven single-turn simulations."""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from review_simulation.persona import ProductAffinity, ReviewPersona
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
    upper_price_limit: Optional[float] = None


@dataclass
class AttributeJudgement:
    """Result of assessing a specific vehicle attribute."""

    satisfied: Optional[bool]
    rationale: Optional[str]


@dataclass
class ProductJudgement:
    """Result of assessing a recommended product."""

    index: int
    product_brand: Optional[str]
    product_name: Optional[str]
    normalize_product_name: Optional[str]
    price: Optional[float]
    satisfied: bool
    rationale: str
    attribute_results: Dict[str, AttributeJudgement]
    confidence: Optional[float]


@dataclass
class SimulationMetrics:
    precision_at_k: Optional[float]
    satisfied_count: int
    infra_list_diversity: Optional[float]
    ndcg_at_k: Optional[float]
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
    vehicles: List[ProductJudgement]
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


class ProductAssessment(BaseModel):
    index: int = Field(..., description="1-based index of the product in the presented list")
    satisfied: bool = Field(..., description="Whether the persona would be satisfied overall")
    rationale: str = Field(..., description="Short textual explanation")
    confidence: Optional[float] = Field(
        None,
        description="Confidence in the overall satisfaction judgement between 0 and 1",
        ge=0.0,
        le=1.0,
    )
    price: Optional[AttributeAssessment] = None
    product_brand: Optional[AttributeAssessment] = None
    product_name: Optional[AttributeAssessment] = None
    normalize_product_name: Optional[AttributeAssessment] = None
    performance_tier: Optional[AttributeAssessment] = None
    all_misc: Optional[AttributeAssessment] = None


class ProductAssessmentList(BaseModel):
    assessments: List[ProductAssessment]


class SummaryResponse(BaseModel):
    satisfied_summary: str = Field(
        ..., description="One-sentence reason the persona would be satisfied with the list"
    )
    unsatisfied_summary: str = Field(
        ..., description="One-sentence reason the persona would be unsatisfied with the list"
    )


class NormalizedProductName(BaseModel):
    normalize_product_name: Optional[str] = Field(
        None,
        description="The normalized family or series name (e.g., 'RTX 5060 Ti').",
    )


NORMALIZE_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You extract concise normalized GPU or PC component family names from product titles.",
            "Return only the family/series identifier (e.g., 'RTX 5060 Ti', 'Quadro K2200').",
            "If unsure, return null.",
        ),
        (
            "human",
            """
Product title: {product_title}

Respond with JSON {"normalize_product_name": <string|null>}.
Ensure the value is brief (<=6 words) and omits sellers or bundle notes.
""",
        ),
    ]
)


PERSONA_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You craft single-turn user utterances for a GPU recommendation demo."
            "Read the reviewer's background and produce a concise, natural query."
            "Every generated query must restate the shopper's concrete preferences."
            "Identify the highest price the shopper would pay and include it.",
        ),
        (
            "human",
            """
Review summary:
Brand/Product owned or discussed: {product_brand} {product_name}
Rating given: {rating}
Review excerpt: "{review}"
Likes: {likes}
Dislikes: {dislikes}
Stated intention: {intention}
Mentioned product brands: {mentioned_product_brands}
Mentioned product names: {mentioned_product_names}
Mentioned normalized products: {mentioned_normalize_product_names}
Performance expectation: {performance_tier}
Newness preference (1-10): {newness_preference_score} — {newness_preference_notes}
Price range: {price_range}
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
- user_message: Must clearly mention the desired product_brand/product_name (if any), normalized product family, how new they want the search to be,
  performance expectations (high-end, mid-range, or low-end), desired price range/budget, willingness to consider alternatives,
  and any additional priorities highlighted above (e.g., acoustics, thermals, workload).
""",
        ),
    ]
)


ASSESSMENT_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You evaluate GPU recommendations for a simulated shopper."
            "Decide if each product matches the persona's expressed likes/dislikes."
            "Only use product_brand, product_name, normalized product family, performance tier (if provided), and price to judge."
            "Respect their newness preference scale, budget ceiling, and openness to alternatives when deciding satisfaction."
            "All product information provided is accurate. DO NOT override it with assumptions. Use it to make informed judgements."
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
Mentioned product brands: {mentioned_product_brands}
Mentioned product names: {mentioned_product_names}
Mentioned normalized products: {mentioned_normalize_product_names}
Performance expectation: {performance_tier}
Newness preference (1-10): {newness_preference_score} — {newness_preference_notes}
Price range: {price_range}
Openness to alternatives (1-10): {openness_to_alternatives}
Other priorities: {misc_notes}
Upper price limit (USD): {upper_price_limit}
Current year is 2025 (assume this for the most newness context).
Do NOT make assumptions beyond the provided information. Only use the data given to make your judgements.

For each product below decide if the persona would be satisfied. Judge only the
criteria explicitly mentioned in the persona_query; if a criterion was not
mentioned, return null for that criterion. Respond with JSON using this shape:
{{"assessments": [{{"index": <number>, "satisfied": <bool>, "rationale": <string>, "confidence": <float 0-1>,
"price": {{"satisfied": <bool|null>, "rationale": <string|null>}}, "product_brand": {{...}}, "product_name": {{...}},
"normalize_product_name": {{...}}, "performance_tier": {{...}}, "all_misc": {{...}}}}, ...]}}.
In details, for each attribute, to determine overall satisfaction, consider:
price: (whether the price satisfies the users' budget or price range in the query).
product_brand: (whether the brand satisfies the users' preference in the query. If the users are fine with alternatives, return True.).
product_name: (whether the specific product satisfies the users' preference in the query. If the users are fine with alternatives, return True.).
normalize_product_name: (whether the normalized family matches what they asked for. If open to alternatives, return True.).
performance_tier: (whether the product performance tier matches what they want: high-end, mid-range, or low-end. Return None if not mentioned.)
all_misc: (whether all other preferences mentioned in the query are satisfied. Examples: thermals, acoustics, workload.)
For satisfied: only return true/false for each attribute when persona_query mentions it; otherwise set
that attribute to null. Make price decisions using the provided upper price
limit and the product's price.
Confidence should be a number between 0 and 1 indicating how confident you are in the overall satisfaction judgement.
If there are a lot of conflicts between attributes and the final satisfaction judgement, the confidence score should be lower.
Vice versa, if there are a lot of attributes that align with the final satisfaction judgement, the confidence score should be higher.
The delta of confidence should be proportional to the number of attributes that align with the final satisfaction judgement.
Products:
{vehicles}
""",
        ),
    ]
)


SUMMARY_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You condense product satisfaction rationales into concise summaries."
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


def _affinities_to_text(items: List[ProductAffinity]) -> str:
    if not items:
        return "None"
    parts = []
    for item in items:
        attributes = []
        if item.product_brand:
            attributes.append(item.product_brand)
        if item.product_name:
            attributes.append(item.product_name)
        if item.normalize_product_name:
            attributes.append(item.normalize_product_name)
        summary = " ".join(attributes) if attributes else "unspecified product"
        if item.rationale:
            summary += f" ({item.rationale})"
        parts.append(summary)
    return "; ".join(parts)


def _list_to_text(values: List[str]) -> str:
    if not values:
        return "None"
    return ", ".join(values)


def _infer_normalize_product_name(
    product_title: Optional[str], model: ChatOpenAI
) -> Optional[str]:
    if not product_title:
        return None
    try:
        structured_model = model.with_structured_output(NormalizedProductName)
        response = structured_model.invoke(
            NORMALIZE_PROMPT.format_prompt(product_title=product_title).to_messages()
        )
        value = response.normalize_product_name
        if value is None:
            return None
        return value.strip()
    except Exception:
        return None


def _format_vehicle_entry(
    vehicle: dict, index: int, model: ChatOpenAI
) -> Dict[str, Optional[str]]:
    product_brand = (
        vehicle.get("product_brand")
        or vehicle.get("brand")
        or vehicle.get("product", {}).get("brand")
    )
    product_name = (
        vehicle.get("product_name")
        or vehicle.get("title")
        or vehicle.get("product", {}).get("title")
    )
    normalize_product_name = (
        vehicle.get("normalize_product_name")
        or vehicle.get("normalized_product_name")
        or vehicle.get("product", {}).get("normalized_product_name")
    )
    if not normalize_product_name:
        normalize_product_name = _infer_normalize_product_name(product_name, model)

    price = (
        vehicle.get("price_value")
        or vehicle.get("price")
        or vehicle.get("offer", {}).get("price")
    )
    try:
        price = float(price) if price is not None else None
    except (TypeError, ValueError):
        price = None

    return {
        "index": index,
        "product_brand": product_brand,
        "product_name": product_name,
        "normalize_product_name": normalize_product_name,
        "price": price,
    }


def build_persona_turn(persona: ReviewPersona, model: ChatOpenAI) -> PersonaTurn:
    structured_model = model.with_structured_output(PersonaDraft)
    likes_text = _affinities_to_text(persona.liked)
    dislikes_text = _affinities_to_text(persona.disliked)
    rating_text = persona.rating_value if persona.rating_value is not None else "unknown"

    prompt = PERSONA_PROMPT.format_prompt(
        product_brand=persona.product_brand,
        product_name=persona.product_name,
        rating=rating_text,
        review=persona.review,
        likes=likes_text,
        dislikes=dislikes_text,
        intention=persona.intention or "",
        mentioned_product_brands=_list_to_text(persona.mentioned_product_brands),
        mentioned_product_names=_list_to_text(persona.mentioned_product_names),
        mentioned_normalize_product_names=_list_to_text(
            persona.mentioned_normalize_product_names
        ),
        performance_tier=persona.performance_tier or "unspecified",
        newness_preference_score=persona.newness_preference_score or "unknown",
        newness_preference_notes=persona.newness_preference_notes or "",
        price_range=persona.price_range or "unspecified",
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
) -> List[ProductJudgement]:
    structured_model = model.with_structured_output(ProductAssessmentList)
    likes_text = _affinities_to_text(persona.liked)
    dislikes_text = _affinities_to_text(persona.disliked)

    vehicle_entries = [
        _format_vehicle_entry(vehicle, idx + 1, model)
        for idx, vehicle in enumerate(vehicles)
    ]
    prompt = ASSESSMENT_PROMPT.format_prompt(
        goal_summary=persona_turn.goal_summary,
        writing_style=persona_turn.writing_style,
        interaction_style=persona_turn.interaction_style,
        family_background=persona_turn.family_background,
        likes=likes_text,
        dislikes=dislikes_text,
        persona_query=persona_turn.message,
        mentioned_product_brands=_list_to_text(persona.mentioned_product_brands),
        mentioned_product_names=_list_to_text(persona.mentioned_product_names),
        mentioned_normalize_product_names=_list_to_text(
            persona.mentioned_normalize_product_names
        ),
        performance_tier=persona.performance_tier or "unspecified",
        newness_preference_score=persona.newness_preference_score or "unknown",
        newness_preference_notes=persona.newness_preference_notes or "",
        price_range=persona.price_range or "unspecified",
        openness_to_alternatives=persona.alternative_openness or "unknown",
        misc_notes=persona.misc_notes or "None stated",
        upper_price_limit=persona_turn.upper_price_limit or "unspecified",
        vehicles=json.dumps(vehicle_entries, indent=2),
    )
    response = structured_model.invoke(prompt.to_messages())

    assessment_map = {item.index: item for item in response.assessments}

    results: List[ProductJudgement] = []
    attribute_keys = ["price", "product_brand", "product_name", "normalize_product_name", "performance_tier", "all_misc"]

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
            assessment = ProductAssessment(index=entry["index"], satisfied=False, rationale="No evaluation")
        attribute_results = {
            key: _attribute_judgement(getattr(assessment, key)) for key in attribute_keys
        }
        results.append(
            ProductJudgement(
                index=entry["index"],
                product_brand=entry.get("product_brand"),
                product_name=entry.get("product_name"),
                normalize_product_name=entry.get("normalize_product_name"),
                price=entry.get("price"),
                satisfied=assessment.satisfied,
                rationale=assessment.rationale.strip(),
                attribute_results=attribute_results,
                confidence=assessment.confidence,
            )
        )
    return results


def _compute_metrics(judgements: List[ProductJudgement], persona: ReviewPersona, k: int) -> SimulationMetrics:
    _ = persona
    if k <= 0:
        return SimulationMetrics(
            precision_at_k=None,
            satisfied_count=0,
            infra_list_diversity=None,
            ndcg_at_k=None,
            attribute_satisfaction={},
        )

    top_k = [j for j in judgements if j.index <= k]
    if not top_k:
        return SimulationMetrics(
            precision_at_k=None,
            satisfied_count=0,
            infra_list_diversity=None,
            ndcg_at_k=None,
            attribute_satisfaction={},
        )

    satisfied = [j for j in top_k if j.satisfied]
    precision = len(satisfied) / len(top_k)

    brand_products = [
        (
            str(j.product_brand).strip().lower() if j.product_brand else "",
            str(j.product_name).strip().lower() if j.product_name else "",
        )
        for j in top_k
    ]
    unique_brand_products = {item for item in brand_products if any(item)}
    infra_list_diversity = None
    infra_list_diversity = len(unique_brand_products) / len(top_k)

    def _dcg(items: List[ProductJudgement]) -> float:
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
        satisfied_count=len(satisfied),
        infra_list_diversity=infra_list_diversity,
        ndcg_at_k=ndcg,
        attribute_satisfaction=attribute_satisfaction,
    )


def _summarize_judgements(
    judgements: List[ProductJudgement], model: ChatOpenAI
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
    else:
        raise ValueError(
            "recommendation_method must be 1 or 2; received"
            f" {recommendation_method}"
        )
    vehicles = (
        response.get("recommended_products")
        or response.get("recommended_vehicles")
        or []
    )[:recommendation_limit]

    judgements = _assess_vehicles(persona, persona_turn, vehicles, llm)
    attempts: List[List[ProductJudgement]] = [judgements]

    def _avg_confidence(items: List[ProductJudgement]) -> Optional[float]:
        confidences = [j.confidence for j in items if j.confidence is not None]
        if not confidences:
            return None
        return sum(confidences) / len(confidences)

    def _select_majority(attempt_sets: List[List[ProductJudgement]]) -> List[ProductJudgement]:
        if not attempt_sets:
            return []

        by_index: Dict[int, List[ProductJudgement]] = {}
        for attempt in attempt_sets:
            for judgement in attempt:
                by_index.setdefault(judgement.index, []).append(judgement)

        final: List[ProductJudgement] = []
        for index, entries in sorted(by_index.items()):
            true_count = sum(1 for entry in entries if entry.satisfied is True)
            false_count = sum(1 for entry in entries if entry.satisfied is False)
            if true_count > false_count:
                majority_value: Optional[bool] = True
            elif false_count > true_count:
                majority_value = False
            else:
                majority_value = None

            def _confidence_score(entry: ProductJudgement) -> float:
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
