"""
Supervisor Agent - orchestrates tools and generates responses.

The supervisor decides which tool(s) to call based on user intent,
then generates a natural language response.
"""
import json
from typing import Dict, Any, Optional, List
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from idss_agent.state import VehicleSearchState, get_latest_user_message


# Supervisor decision prompt
SUPERVISOR_DECISION_PROMPT = """
You are a vehicle shopping assistant supervisor. Your job is to decide what action to take based on the user's message.

Current context:
- Vehicles available: {has_vehicles}
- Vehicle count: {vehicle_count}
- Filters: {filters_summary}
- User's message: "{user_message}"

You must always route the user's request to exactly ONE of these tools:
- **discovery_tool**
  - Use when the user wants to browse, see options, or get an overview of listings.
  - Examples: "show me cars", "what do you have", "give me some recommendations", location adjustments, filter tweaks, general browsing requests.
- **analytical_tool**
  - Use when the user asks detailed questions about a specific vehicle, comparisons, specs, or needs deep data lookup.
  - Examples: "tell me about #1", "compare #1 and #3", "what's the safety rating", "does it have heated seats?"

Do not choose "none" or any other option. If the message is chit-chat or outside these instructions, prefer discovery_tool.

Decide what to do:
{{
  "tool": "discovery_tool" | "analytical_tool",
  "reasoning": "Brief explanation of why",
  "params": {{
    "question": "for analytical_tool only - the specific question to answer"
  }}
}}

Output ONLY valid JSON.
"""


# Supervisor response generation prompt
SUPERVISOR_RESPONSE_PROMPT = """
You are a friendly vehicle shopping assistant. Generate a natural, helpful response to the user.

Conversation history:
{conversation_history}

User's message:
"{user_message}"

Tool called: {tool_used}

Tool result:
{tool_result}

Current context:
- Filters: {filters}
- Preferences: {preferences}

Generate a helpful, conversational response. If the tool provided information, present it naturally.
If no tool was used, respond directly to the user.

Output ONLY the response text (no JSON, no formatting).
"""


def summarize_state(state: VehicleSearchState) -> Dict[str, Any]:
    """
    Create a lightweight summary of state for supervisor decisions.

    Args:
        state: Full state

    Returns:
        Summarized state dict
    """
    filters = state.get("explicit_filters", {})
    vehicles = state.get("recommended_vehicles", [])

    # Create human-readable filter summary
    filter_parts = []
    if filters.get("make"):
        filter_parts.append(filters["make"])
    if filters.get("model"):
        filter_parts.append(filters["model"])
    if filters.get("body_style"):
        filter_parts.append(filters["body_style"])
    if filters.get("price"):
        filter_parts.append(f"${filters['price']}")
    if filters.get("state"):
        filter_parts.append(f"in {filters['state']}")

    filters_summary = ", ".join(filter_parts) if filter_parts else "no specific filters"

    return {
        "has_vehicles": len(vehicles) > 0,
        "vehicle_count": len(vehicles),
        "filters_summary": filters_summary
    }


def supervisor_decide_action(state: VehicleSearchState, user_input: str) -> Dict[str, Any]:
    """
    Supervisor decides what action to take (which tool to call).

    This is a lightweight decision step using summarized state.

    Args:
        state: Current state
        user_input: User's message

    Returns:
        Decision dict with tool and params
    """
    llm = ChatOpenAI(model="gpt-4o", temperature=0)

    summary = summarize_state(state)

    prompt = SUPERVISOR_DECISION_PROMPT.format(
        has_vehicles=summary["has_vehicles"],
        vehicle_count=summary["vehicle_count"],
        filters_summary=summary["filters_summary"],
        user_message=user_input
    )

    response = llm.invoke([
        SystemMessage(content=prompt),
        HumanMessage(content="Decide what to do.")
    ])

    try:
        content = response.content.strip()
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()

        decision = json.loads(content)
        return decision

    except json.JSONDecodeError as e:
        print(f"Warning: Failed to parse supervisor decision: {e}")
        # Fallback: default to discovery_tool if parsing fails
        return {"tool": "discovery_tool", "reasoning": "Fallback", "params": {}}


def supervisor_generate_response(
    state: VehicleSearchState,
    user_input: str,
    tool_used: str,
    tool_result: Optional[str] = None
) -> str:
    """Fallback response when no delegated tool was used."""
    llm = ChatOpenAI(model="gpt-4o", temperature=0.7)

    history = state.get("conversation_history", [])[-8:]
    history_context = "\n".join([
        f"{'User' if msg.__class__.__name__ == 'HumanMessage' else 'Assistant'}: {msg.content}"
        for msg in history
    ])

    prompt = SUPERVISOR_RESPONSE_PROMPT.format(
        conversation_history=history_context,
        user_message=user_input,
        tool_used=tool_used,
        tool_result=tool_result or "No tool result",
        filters=json.dumps(state.get("explicit_filters", {}), indent=2),
        preferences=json.dumps(state.get("implicit_preferences", {}), indent=2)
    )

    response = llm.invoke([
        SystemMessage(content=prompt),
        HumanMessage(content="Generate response.")
    ])

    return response.content.strip()
