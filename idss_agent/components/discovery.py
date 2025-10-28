"""
Discovery agent - generates responses with listing summary and elicitation questions.
"""
import json
from typing import List, Dict, Any, Optional, Callable
from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from idss_agent.config import get_config
from idss_agent.prompt_loader import render_prompt
from idss_agent.state import VehicleSearchState, AgentResponse


def format_vehicles_for_llm(vehicles: List[Dict[str, Any]], limit: int = 3, max_chars: int = 4000) -> str:
    """Return raw JSON for the top vehicles, truncated to a safe length."""
    if not vehicles:
        return "[]"

    limited = vehicles[:limit]
    raw_json = json.dumps(limited, indent=2)

    if len(raw_json) > max_chars:
        raw_json = raw_json[: max_chars - 3] + "..."

    return raw_json


def discovery_agent(
    state: VehicleSearchState,
    progress_callback: Optional[Callable[[dict], None]] = None
) -> VehicleSearchState:
    """
    Discovery agent - generates vehicle overview and elicitation questions.

    This agent:
    1. Acknowledges user preferences
    2. Uses bullet points to recommend the first vehicle about how it matches the user's preferences
    3. Asks 1-2 strategic elicitation questions

    Args:
        state: Current vehicle search state
        progress_callback: Optional callback for progress updates

    Returns:
        Updated state with ai_response
    """

    # Emit progress: Starting response generation
    if progress_callback:
        progress_callback({
            "step_id": "generating_response",
            "description": "Presenting vehicles",
            "status": "in_progress"
        })

    filters = state['explicit_filters']
    implicit = state['implicit_preferences']
    vehicles = state['recommended_vehicles']
    already_asked = state.get('questions_asked', [])

    # Get configuration
    config = get_config()
    model_config = config.get_model_config('discovery')
    top_limit = config.limits.get('top_vehicles_to_show', 3)

    # Format vehicles for LLM
    vehicles_summary = format_vehicles_for_llm(vehicles, limit=top_limit)

    # Load system prompt from template
    discovery_system_prompt = render_prompt('discovery.j2')

    prompt = f"""
**User's Current Filters:**
{json.dumps(filters, indent=2)}

**User's Preferences:**
{json.dumps(implicit, indent=2)}

**Current Listings ({len(vehicles)} vehicles found, showing top {top_limit} as JSON):**
{vehicles_summary}

**Topics Already Asked About:** {already_asked}
(Avoid asking about these topics again)

Generate your response:
"""

    messages = [
        SystemMessage(content=discovery_system_prompt),
        HumanMessage(content=prompt),
    ]

    # Create LLM with config parameters
    llm = ChatOpenAI(
        model=model_config['name'],
        temperature=model_config['temperature'],
        max_tokens=model_config.get('max_tokens', 800)
    )
    structured_llm = llm.with_structured_output(AgentResponse)
    response: AgentResponse = structured_llm.invoke(messages)

    state['ai_response'] = response.ai_response
    state['quick_replies'] = response.quick_replies
    state['suggested_followups'] = response.suggested_followups
    state['comparison_table'] = None  # Clear comparison table in discovery mode

    # Extract and track which topics were asked about
    state = extract_questions_asked(state, response.ai_response)

    # Emit progress: Response complete
    if progress_callback:
        progress_callback({
            "step_id": "generating_response",
            "description": "Response ready",
            "status": "completed"
        })

    # Mark as complete
    if progress_callback:
        progress_callback({
            "step_id": "complete",
            "description": "Complete",
            "status": "completed"
        })

    return state


def extract_questions_asked(state: VehicleSearchState, ai_response: str) -> VehicleSearchState:
    """
    Use LLM to extract which topics were asked about in the response.

    This allows us to avoid repeating questions in future turns.

    Args:
        state: Current vehicle search state
        ai_response: The assistant's response text

    Returns:
        Updated state with questions_asked list
    """

    extraction_prompt = f"""
Given this assistant response, identify which topics were asked about in the questions.

Response:
"{ai_response}"

Possible topics:
- budget (asking about price range or budget)
- location (asking about zip code, city, or location)
- usage (asking about how they'll use the vehicle, purpose, driving patterns)
- priorities (asking what matters most, what they value)
- mileage (asking about mileage preferences)
- vehicle_type (asking about SUV, sedan, truck, body style)
- features (asking about specific features needed)
- timeline (asking when they need the vehicle)

Return ONLY a JSON array of topics that were asked about, e.g.:
["budget", "location", "usage"]

If no questions were asked, return an empty array: []
"""

    # Get configuration for extraction model
    config = get_config()
    model_config = config.get_model_config('discovery_extraction')

    llm = ChatOpenAI(
        model=model_config['name'],
        temperature=model_config['temperature'],
        max_tokens=model_config.get('max_tokens', 500)
    )
    result = llm.invoke(extraction_prompt)

    try:
        content = result.content.strip()
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()

        topics = json.loads(content)

        if isinstance(topics, list):
            current_questions = state.get('questions_asked', [])
            for topic in topics:
                if topic not in current_questions:
                    current_questions.append(topic)
            state['questions_asked'] = current_questions

    except json.JSONDecodeError as e:
        print(f"Warning: Could not parse topics from response: {e}")

    return state
