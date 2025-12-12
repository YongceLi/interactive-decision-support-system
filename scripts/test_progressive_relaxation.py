#!/usr/bin/env python3
"""Test progressive filter relaxation."""
from idss_agent.processing.recommendation_method1 import recommend_method1

# Test with multiple filters
explicit_filters = {
    "make": "Toyota",
    "fuel_type": "Hybrid",
    "body_style": "SUV",
    "exterior_color": "Blue",
    "price": "20000-35000",
    "is_used": True,
}

implicit_preferences = {
    "priorities": ["fuel_efficiency", "reliability"],
    "lifestyle": "family",
}

print("Testing Progressive Filter Relaxation")
print("=" * 60)
print(f"Starting filters: {list(explicit_filters.keys())}")
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
print(f"Filters applied: {relaxation_metadata.get('filters_applied', [])}")
print(f"Filters relaxed: {relaxation_metadata.get('filters_relaxed', [])}")
print()

print("Relaxation History:")
for step in relaxation_metadata.get('relaxation_history', []):
    print(f"  Iteration {step['iteration']}: {len(step['filters'])} filters → {step['results']} results")
    print(f"    Filters: {step['filters']}")

if vehicles:
    print(f"\nTop 3 vehicles:")
    for i, v in enumerate(vehicles[:3], 1):
        car = v.get("vehicle", {})
        print(f"  {i}. {car.get('year')} {car.get('make')} {car.get('model')} - ${car.get('price')}")
