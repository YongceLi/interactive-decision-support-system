"""Dataclasses for persona-driven review simulations."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class PreferenceBundle:
    """Represents explicit + implicit preferences extracted from a review."""

    explicit: Dict[str, str]
    implicit: Dict[str, object]
    mentioned_like: List[str] = field(default_factory=list)
    mentioned_dislike: List[str] = field(default_factory=list)
    mentioned_setup: Optional[str] = None
    performance: str = "mid-range"
    newness: int = 5
    price_range: str = "mid-range"
    openness_to_alternative: int = 5


@dataclass
class PersonaProfile:
    """Condensed persona built from review context."""

    summary: str
    review_date: str
    source: str
    rating: float
    brand: str
    product: str
    norm_product: str
    performance: str
    newness: int
    price_range: str
    openness_to_alternative: int
    likes: List[str] = field(default_factory=list)
    dislikes: List[str] = field(default_factory=list)
    setup_notes: Optional[str] = None
    extra_context: Dict[str, str] = field(default_factory=dict)


@dataclass
class QueryBundle:
    """Collection of search queries derived from a review persona."""

    primary: str
    alternates: List[str] = field(default_factory=list)


@dataclass
class EnrichedReview:
    """Fully enriched review ready for evaluation."""

    review_id: str
    brand: str
    product: str
    norm_product: str
    review: str
    rating: float
    date: str
    source: str
    preferences: PreferenceBundle
    persona: PersonaProfile
    queries: QueryBundle

    def to_row(self) -> Dict[str, object]:
        """Serialize to a CSV-friendly dictionary."""

        return {
            "review_id": self.review_id,
            "brand": self.brand,
            "product": self.product,
            "norm_product": self.norm_product,
            "review": self.review,
            "rating": self.rating,
            "date": self.date,
            "source": self.source,
            "mentioned_like": ", ".join(self.preferences.mentioned_like),
            "mentioned_dislike": ", ".join(self.preferences.mentioned_dislike),
            "mentioned_setup": self.preferences.mentioned_setup or "",
            "performance": self.preferences.performance,
            "newness": self.preferences.newness,
            "price_range": self.preferences.price_range,
            "openness_to_alternative": self.preferences.openness_to_alternative,
            "explicit_preferences": self.preferences.explicit,
            "implicit_preferences": self.preferences.implicit,
            "persona": {
                "summary": self.persona.summary,
                "review_date": self.persona.review_date,
                "source": self.persona.source,
                "rating": self.persona.rating,
                "brand": self.persona.brand,
                "product": self.persona.product,
                "norm_product": self.persona.norm_product,
                "performance": self.persona.performance,
                "newness": self.persona.newness,
                "price_range": self.persona.price_range,
                "openness_to_alternative": self.persona.openness_to_alternative,
                "likes": self.persona.likes,
                "dislikes": self.persona.dislikes,
                "setup_notes": self.persona.setup_notes,
                "extra_context": self.persona.extra_context,
            },
            "queries": {
                "primary": self.queries.primary,
                "alternates": self.queries.alternates,
            },
        }


def load_row(row: Dict[str, str]) -> EnrichedReview:
    """Deserialize a CSV row into an :class:`EnrichedReview`."""

    explicit = row.get("explicit_preferences") or {}
    implicit = row.get("implicit_preferences") or {}
    persona_data = row.get("persona") or {}
    queries = row.get("queries") or {}

    # Rows may contain JSON-encoded strings - defer parsing to dataset helpers.
    raise NotImplementedError(
        "Use review_simulation.dataset.load_enriched_reviews to deserialize rows"
    )
