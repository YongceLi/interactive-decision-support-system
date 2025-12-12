#!/usr/bin/env python3
"""Test progressive filter relaxation with must_have filters."""
from idss_agent.processing.recommendation_method1 import recommend_method1

# Test with must_have filters
explicit_filters = {
    "make": "Toyota",
    "fuel_type": "Hybrid",
    "body_style": "SUV",
    "exterior_color": "Blue",
    "price": "20000-35000",
    "is_used": True,
    "must_have_filters": ["fuel_type", "body_style"]  # These should be kept longest!
}

implicit_preferences = {
    "priorities": ["fuel_efficiency", "reliability"],
    "lifestyle": "family",
}

print("Testing Progressive Filter Relaxation WITH Must-Have Filters")
print("=" * 60)
print(f"Starting filters: {[k for k in explicit_filters.keys() if k != 'must_have_filters']}")
print(f"Must-have filters: {explicit_filters['must_have_filters']}")
print()
print("Expected relaxation order:")
print("  1. exterior_color (lowest priority)")
print("  2. price")
print("  3. make")
print("  4. is_used")
print("  5. fuel_type (MUST-HAVE - should be kept)")
print("  6. body_style (MUST-HAVE - should be kept)")
print()

vehicles, sql_query, relaxation_metadata = recommend_method1(
    explicit_filters=explicit_filters,
    implicit_preferences=implicit_preferences,
    top_k=10,
)

print("\n" + "=" * 60)
print("RESULTS")
print("=" * 60)
print(f"Vehicles found: {len(vehicles)}")
print(f"Must-have filters: {relaxation_metadata.get('must_have_filters', [])}")
print(f"Filters applied: {relaxation_metadata.get('filters_applied', [])}")
print(f"Filters relaxed: {relaxation_metadata.get('filters_relaxed', [])}")
print()

print("Relaxation History:")
for step in relaxation_metadata.get('relaxation_history', []):
    print(f"  Iteration {step['iteration']}: {len(step['filters'])} filters → {step['results']} results")
    print(f"    Filters: {step['filters']}")

# Verify must-have filters were kept
must_have = set(relaxation_metadata.get('must_have_filters', []))
filters_applied = set(relaxation_metadata.get('filters_applied', []))
must_have_kept = must_have.intersection(filters_applied)

print()
if must_have_kept == must_have:
    print("✓ SUCCESS: All must-have filters were kept!")
else:
    print(f"✗ WARNING: Some must-have filters were relaxed!")
    print(f"   Expected to keep: {must_have}")
    print(f"   Actually kept: {must_have_kept}")
    print(f"   Relaxed: {must_have - must_have_kept}")
