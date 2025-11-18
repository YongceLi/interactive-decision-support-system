"""Core enrichment helpers for electronics reviews."""

from __future__ import annotations

import hashlib
import re
from typing import Dict, List, Tuple

from .constants import (
    NEGATIVE_FEATURES,
    PERFORMANCE_CUES,
    POSITIVE_FEATURES,
    PRICE_KEYWORDS,
    SETUP_CUES,
    USAGE_PATTERNS,
)
from .models import EnrichedReview, PersonaProfile, PreferenceBundle, QueryBundle


def _normalize_text(value: str) -> str:
    return (value or "").strip()


def _hash_review(text: str, product: str) -> str:
    payload = f"{text}|{product}".encode("utf-8")
    return hashlib.sha1(payload).hexdigest()[:12]


def _collect_feature_mentions(text: str) -> Tuple[List[str], List[str]]:
    lowered = text.lower()
    likes, dislikes = [], []
    for bucket, keywords in POSITIVE_FEATURES.items():
        if any(keyword in lowered for keyword in keywords):
            likes.append(bucket)
    for bucket, keywords in NEGATIVE_FEATURES.items():
        if any(keyword in lowered for keyword in keywords):
            dislikes.append(bucket)
    return likes, dislikes


def _extract_setup(text: str) -> str | None:
    lowered = text.lower()
    for cue in SETUP_CUES:
        if cue in lowered:
            # Return sentence containing cue
            sentences = re.split(r"(?<=[.!?])\s+", text)
            for sentence in sentences:
                if cue.strip() in sentence.lower():
                    return sentence.strip()
            return text.strip()
    return None


def _infer_usage(text: str) -> Tuple[str, List[str]]:
    lowered = text.lower()
    matches = []
    for usage, keywords in USAGE_PATTERNS.items():
        if any(keyword in lowered for keyword in keywords):
            matches.append(usage)
    primary = matches[0] if matches else "general"
    return primary, matches


def _score_performance(text: str, rating: float) -> str:
    lowered = text.lower()
    for tier, keywords in PERFORMANCE_CUES.items():
        if any(keyword in lowered for keyword in keywords):
            if tier == "entry":
                return "low-end"
            if tier == "mid-range":
                return "mid-range"
            return "high-end"
    if rating >= 4.5:
        return "high-end"
    if rating >= 3:
        return "mid-range"
    return "low-end"


def _score_newness(text: str, rating: float) -> int:
    lowered = text.lower()
    if "latest" in lowered or "new" in lowered or re.search(r"20(2[0-9]|30)", lowered):
        return 8
    if "older" in lowered or "last gen" in lowered:
        return 4
    return min(10, max(1, int(round(rating * 2))))


def _score_price(text: str) -> str:
    lowered = text.lower()
    for label, keywords in PRICE_KEYWORDS.items():
        if any(keyword in lowered for keyword in keywords):
            if label == "budget":
                return "budget"
            if label == "mid-range":
                return "mid-range"
            return "premium"
    return "mid-range"


def _score_openness(text: str, rating: float) -> int:
    lowered = text.lower()
    if "never again" in lowered or "sticking with" in lowered:
        return 2
    if "open to" in lowered or "consider" in lowered:
        return 8
    base = int(round(rating * 1.5))
    return min(10, max(1, base))


def build_preferences(row: Dict[str, str]) -> PreferenceBundle:
    review_text = row.get("Review") or row.get("review") or ""
    rating = float(row.get("Rating") or row.get("rating") or 0)
    likes, dislikes = _collect_feature_mentions(review_text)
    setup = _extract_setup(review_text)
    performance = _score_performance(review_text, rating)
    newness = _score_newness(review_text, rating)
    price = _score_price(review_text)
    openness = _score_openness(review_text, rating)
    usage_primary, usage_matches = _infer_usage(review_text)

    explicit = {
        "brand": row.get("Brand") or row.get("brand") or "",
        "product": row.get("Norm_Product") or row.get("norm_product") or row.get("Product") or row.get("product") or "",
    }
    implicit = {
        "priorities": likes or [performance],
        "usage_patterns": usage_primary,
        "usage_matches": usage_matches,
        "notes": review_text[:280],
    }

    return PreferenceBundle(
        explicit=explicit,
        implicit=implicit,
        mentioned_like=likes,
        mentioned_dislike=dislikes,
        mentioned_setup=setup,
        performance=performance,
        newness=newness,
        price_range=price,
        openness_to_alternative=openness,
    )


def build_persona(row: Dict[str, str], preferences: PreferenceBundle) -> PersonaProfile:
    summary = (
        f"{row.get('Brand', row.get('brand', ''))} {row.get('Norm_Product', row.get('norm_product', ''))}"
        f" reviewer values {', '.join(preferences.mentioned_like) or preferences.performance}"
    )
    if preferences.mentioned_dislike:
        summary += f" but dislikes {', '.join(preferences.mentioned_dislike)}"

    return PersonaProfile(
        summary=summary,
        review_date=row.get("Date") or row.get("date") or "",
        source=row.get("Source") or row.get("source") or "",
        rating=float(row.get("Rating") or row.get("rating") or 0),
        brand=row.get("Brand") or row.get("brand") or "",
        product=row.get("Product") or row.get("product") or "",
        norm_product=row.get("Norm_Product") or row.get("norm_product") or "",
        performance=preferences.performance,
        newness=preferences.newness,
        price_range=preferences.price_range,
        openness_to_alternative=preferences.openness_to_alternative,
        likes=list(preferences.mentioned_like),
        dislikes=list(preferences.mentioned_dislike),
        setup_notes=preferences.mentioned_setup,
        extra_context={
            "mentioned_usage": ", ".join(preferences.implicit.get("usage_matches", [])),
        },
    )


def build_queries(row: Dict[str, str], preferences: PreferenceBundle) -> QueryBundle:
    norm_product = row.get("Norm_Product") or row.get("norm_product") or "product"
    brand = row.get("Brand") or row.get("brand") or ""
    usage = preferences.implicit.get("usage_patterns", "general")
    price_range = preferences.price_range
    performance = preferences.performance

    primary = f"Looking for a {performance} {norm_product} for {usage} with {price_range} pricing"
    alternates = [
        f"Best {norm_product} options similar to {brand} but with better {', '.join(preferences.mentioned_like) or 'performance'}",
        f"{norm_product} recommendations for {usage} that avoid {', '.join(preferences.mentioned_dislike) or 'common issues'}",
    ]
    return QueryBundle(primary=primary, alternates=alternates)


def enrich_row(row: Dict[str, str]) -> EnrichedReview:
    preferences = build_preferences(row)
    persona = build_persona(row, preferences)
    queries = build_queries(row, preferences)
    review_id = _hash_review(row.get("Review") or row.get("review") or "", row.get("Product") or row.get("product") or "")
    return EnrichedReview(
        review_id=review_id,
        brand=row.get("Brand") or row.get("brand") or "",
        product=row.get("Product") or row.get("product") or "",
        norm_product=row.get("Norm_Product") or row.get("norm_product") or "",
        review=row.get("Review") or row.get("review") or "",
        rating=float(row.get("Rating") or row.get("rating") or 0),
        date=row.get("Date") or row.get("date") or "",
        source=row.get("Source") or row.get("source") or "",
        preferences=preferences,
        persona=persona,
        queries=queries,
    )
