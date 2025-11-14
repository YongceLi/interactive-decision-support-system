"""
Proactive response generator for user actions like favoriting vehicles.

This module generates contextual, intelligent responses when users interact with the UI
in ways that signal interest (like favoriting a vehicle).
"""
import json
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage
from idss_agent.state.schema import ProductSearchState
from idss_agent.utils.config import get_config
from idss_agent.utils.prompts import render_prompt
from idss_agent.utils.logger import get_logger

logger = get_logger("components.proactive_responses")


class ProactiveResponse(BaseModel):
    """Response generated when user favorites a vehicle."""
    ai_response: str = Field(description="Proactive question about the favorited vehicle")
    quick_replies: Optional[List[str]] = Field(
        description="Quick actions for analytical deep dive (2-4 options, 5 words max each)"
    )


def generate_favorite_response(
    vehicle: Dict[str, Any],
    state: ProductSearchState
) -> ProactiveResponse:
    """
    Generate contextual proactive response when user favorites a vehicle.

    Uses LLM with structured output to generate an intelligent, contextual question
    based on the vehicle attributes and user's priorities/concerns.

    Args:
        vehicle: Full vehicle object that was favorited
        state: Current agent state with user preferences

    Returns:
        ProactiveResponse with contextual question and quick replies for analytical deep dive
    """

    # Get configuration
    config = get_config()
    model_config = config.get_model_config('general')  # Use general model for proactive responses

    # Extract user preferences
    priorities = state.get('implicit_preferences', {}).get('priorities', [])
    concerns = state.get('implicit_preferences', {}).get('concerns', [])

    # Format priorities and concerns for prompt
    priorities_str = ", ".join(priorities) if priorities else "None specified yet"
    concerns_str = ", ".join(concerns) if concerns else "None specified yet"

    # Format vehicle details (keep it concise)
    vehicle_details = {
        "make": vehicle.get('make', 'Unknown'),
        "model": vehicle.get('model', 'Unknown'),
        "year": vehicle.get('year', ''),
        "price": vehicle.get('price', 'N/A'),
        "mileage": vehicle.get('miles', 'N/A'),
        "condition": vehicle.get('condition', 'N/A')
    }
    vehicle_details_str = json.dumps(vehicle_details, indent=2)

    # Load prompt template
    template_prompt = render_prompt('proactive_favorite.j2')

    # Build full prompt with context
    prompt = f"""{template_prompt}

**User's Priorities:** {priorities_str}
**User's Concerns:** {concerns_str}

**Favorited Vehicle:**
{vehicle_details_str}

Generate the proactive response now.
"""

    # Create LLM with structured output
    llm = ChatOpenAI(
        model=model_config['name'],
        temperature=model_config['temperature'],
        max_tokens=model_config.get('max_tokens', 500)
    )
    structured_llm = llm.with_structured_output(ProactiveResponse)

    try:
        # Generate response
        response: ProactiveResponse = structured_llm.invoke([HumanMessage(content=prompt)])
        logger.info(f"Generated proactive response for {vehicle.get('year')} {vehicle.get('make')} {vehicle.get('model')}")
        return response

    except Exception as e:
        logger.error(f"Failed to generate proactive response: {e}")

        # Fallback: simple default response
        vehicle_name = f"{vehicle.get('year', '')} {vehicle.get('make', '')} {vehicle.get('model', 'this vehicle')}".strip()
        return ProactiveResponse(
            ai_response=f"I see you're interested in the {vehicle_name}! What would you like to know more about?",
            quick_replies=["Show photos", "Safety ratings", "Full specs", "Compare similar"]
        )
