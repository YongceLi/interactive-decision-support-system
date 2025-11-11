"""Console rendering helpers for the review simulation mode."""
from __future__ import annotations

from typing import Iterable, Optional

from rich.console import Console
from rich.table import Table

from review_simulation.simulation import SimulationResult


def _format_metric(value: Optional[float]) -> str:
    if value is None:
        return "—"
    return f"{value:.2f}"


def render_results(results: Iterable[SimulationResult], metric_k: int) -> None:
    console = Console()
    for idx, result in enumerate(results, start=1):
        persona = result.persona
        turn = result.persona_turn
        console.rule(f"Persona {idx}: {persona.make} {persona.model}")
        console.print(f"[bold]Writing style:[/bold] {turn.writing_style}")
        console.print(f"[bold]Interaction style:[/bold] {turn.interaction_style}")
        console.print(f"[bold]Family background:[/bold] {turn.family_background}")
        console.print(f"[bold]Goal summary:[/bold] {turn.goal_summary}")
        console.print(
            "[bold]Preferences:[/bold] "
            f"Makes {', '.join(persona.mentioned_makes) if persona.mentioned_makes else 'unspecified'} | "
            f"Models {', '.join(persona.mentioned_models) if persona.mentioned_models else 'unspecified'} | "
            f"Years {', '.join(str(year) for year in persona.mentioned_years) if persona.mentioned_years else 'unspecified'} | "
            f"Condition {persona.preferred_condition or 'unspecified'} | "
            f"Newness {persona.newness_preference_score or 'unknown'} ({persona.newness_preference_notes or 'no context'}) | "
            f"Type {persona.preferred_vehicle_type or 'unspecified'} | "
            f"Fuel {persona.preferred_fuel_type or 'unspecified'} | "
            f"Openness {persona.alternative_openness or 'unknown'} | "
            f"Notes {persona.misc_notes or 'none'}"
        )
        console.print()
        console.print(f"[bold]User turn:[/bold] {turn.message}")
        console.print()

        table = Table(show_lines=False)
        table.add_column("#", justify="right")
        table.add_column("Make")
        table.add_column("Model")
        table.add_column("Year", justify="right")
        table.add_column("Condition")
        table.add_column("Location")
        table.add_column("Satisfied")
        table.add_column("Rationale", overflow="fold")

        for vehicle in result.vehicles:
            satisfaction = "✅" if vehicle.satisfied else "❌"
            table.add_row(
                str(vehicle.index),
                vehicle.make or "?",
                vehicle.model or "?",
                str(vehicle.year or "-"),
                str(vehicle.condition or "-"),
                str(vehicle.location or "-"),
                satisfaction,
                vehicle.rationale or "",
            )
        console.print(table)
        console.print(
            f"Precision@{metric_k}: {_format_metric(result.metrics.precision_at_k)} | "
            f"Recall@{metric_k}: {_format_metric(result.metrics.recall_at_k)} | "
            f"Satisfied in top {metric_k}: {result.metrics.satisfied_count}"
        )
        console.print()

    console.rule("Simulation complete")
