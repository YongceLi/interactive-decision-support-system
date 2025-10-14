"""
Semantic parser node for extracting vehicle search criteria from user input.
"""
import json
from typing import Dict, Any
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from idss_agent.state import VehicleSearchState, add_user_message, get_latest_user_message


# System prompt for the semantic parser
SEMANTIC_PARSER_PROMPT = """
You are a semantic parser for a vehicle search assistant. Your job is to extract structured information from user messages.

Given a user's input and the conversation history, extract:

1. **Explicit Filters**: Clear, stated preferences about vehicles (make, model, price, color, etc.)
2. **Implicit Preferences**: Inferred preferences about priorities, lifestyle, concerns, etc.

Output Format (JSON):
{
  "explicit_filters": {
    "make": "Toyota",  // or "Toyota,Honda" for multiple
    "model": "Camry",  // or "Camry,Accord" for multiple
    "year": "2018-2020",  // single year "2020" or range "2018-2020"
    "price": "15000-25000",  // range format
    "miles": "0-50000",  // mileage range
    "body_style": "sedan",  // or "sedan,suv"
    "transmission": "automatic",
    "exterior_color": "white,black",  // comma-separated
    "interior_color": "black",
    "doors": 4,  // integer
    "seating_capacity": 5,  // integer
    "state": "CA",
    "zip": "94102",
    "distance": 50,  // radius in miles
    "features": ["sunroof", "leather seats"]  // list of strings
  },
  "implicit_preferences": {
    "priorities": ["reliability", "fuel_efficiency"],  // what matters to user
    "lifestyle": "family-oriented",  // inferred from context
    "budget_sensitivity": "moderate",  // budget-conscious/moderate/luxury-focused
    "brand_affinity": ["Toyota", "Honda"],  // brands they seem to prefer
    "concerns": ["maintenance costs", "resale value"],
    "usage_patterns": "daily commuter",
    "notes": "User mentioned they have kids, likely needs good safety ratings"
  }
}

Rules:
- Only include filters that are mentioned or can be clearly inferred
- For colors, use comma-separated strings: "white,black,silver"
- For ranges, use format "min-max": "2018-2020", "15000-25000"
- For multiple makes/models/body styles, use comma-separated: "Toyota,Honda"
- If user says "around $20000", use a reasonable range like "18000-22000"
- If user says "recent", use last 3-5 years
- If user says "low mileage", use "0-30000"
- Update existing filters, don't replace them unless user explicitly changes preference
- Infer implicit preferences from context clues (e.g., "family" → family-oriented, safety priority)

Examples:

User: "I'm looking for a reliable sedan under $25k"
{
  "explicit_filters": {"body_style": "sedan", "price": "0-25000"},
  "implicit_preferences": {"priorities": ["reliability"], "budget_sensitivity": "moderate"}
}

User: "Show me Toyota Camrys or Honda Accords from 2018-2020 in white or silver"
{
  "explicit_filters": {
    "make": "Toyota,Honda",
    "model": "Camry,Accord",
    "year": "2018-2020",
    "exterior_color": "white,silver"
  },
  "implicit_preferences": {
    "brand_affinity": ["Toyota", "Honda"],
    "priorities": ["reliability"]
  }
}

User: "I need a family SUV with 3 rows, good safety features, around $30-35k"
{
  "explicit_filters": {
    "body_style": "suv",
    "seating_capacity": 7,
    "price": "30000-35000",
    "features": ["third row seating", "safety features"]
  },
  "implicit_preferences": {
    "lifestyle": "family-oriented",
    "priorities": ["safety", "space"],
    "notes": "Needs 3-row seating for family"
  }
}

Now parse the user's message and output ONLY valid JSON, no other text.
"""


def semantic_parser_node(state: VehicleSearchState) -> VehicleSearchState:
    """
    Semantic parser node that extracts vehicle preferences from user input.

    This node:
    1. Gets the latest user message from conversation history
    2. Considers conversation history for context
    3. Uses an LLM to extract explicit filters and implicit preferences
    4. Updates the state with extracted information

    Args:
        state: Current vehicle search state

    Returns:
        Updated state with parsed filters and preferences
    """
    # Get the latest user message from conversation history
    user_input = get_latest_user_message(state)

    if not user_input:
        return state

    llm = ChatOpenAI(model="gpt-4o", temperature=0)

    # Build conversation context from LangChain messages
    history_context = "\n".join([
        f"{'user' if isinstance(msg, HumanMessage) else 'assistant'}: {msg.content}"
        for msg in state.get("conversation_history", [])[-5:]  # Last 5 messages for context
    ])

    # Current state context
    current_filters = state.get("explicit_filters", {})
    current_implicit = state.get("implicit_preferences", {})

    context_info = f"""
Current Explicit Filters: {json.dumps(current_filters, indent=2)}
Current Implicit Preferences: {json.dumps(current_implicit, indent=2)}

Recent Conversation:
{history_context}

New User Input: {user_input}
"""

    # Call LLM to parse
    messages = [
        SystemMessage(content=SEMANTIC_PARSER_PROMPT),
        HumanMessage(content=context_info)
    ]

    response = llm.invoke(messages)

    try:
        # Strip markdown code blocks if present
        content = response.content.strip()
        if content.startswith("```json"):
            content = content[7:]  # Remove ```json
        if content.startswith("```"):
            content = content[3:]  # Remove ```
        if content.endswith("```"):
            content = content[:-3]  # Remove trailing ```
        content = content.strip()

        parsed_data = json.loads(content)

        # Update explicit filters (merge with existing)
        new_filters = parsed_data.get("explicit_filters", {})
        updated_filters = {**current_filters, **new_filters}
        state["explicit_filters"] = updated_filters

        # Update implicit preferences (merge with existing)
        new_implicit = parsed_data.get("implicit_preferences", {})

        # For lists in implicit preferences, extend rather than replace
        updated_implicit = current_implicit.copy()
        for key, value in new_implicit.items():
            if key in updated_implicit and isinstance(value, list) and isinstance(updated_implicit[key], list):
                # Merge lists, remove duplicates
                updated_implicit[key] = list(set(updated_implicit[key] + value))
            else:
                updated_implicit[key] = value

        state["implicit_preferences"] = updated_implicit

    except json.JSONDecodeError as e:
        # If parsing fails, log it but don't crash
        print(f"Warning: Failed to parse LLM response as JSON: {e}")
        print(f"Response content: {response.content}")

    return state


def format_state_summary(state: VehicleSearchState) -> str:
    """
    Format the current state into a readable summary.

    Args:
        state: Current vehicle search state

    Returns:
        Human-readable string summary of the state
    """
    filters = state.get("explicit_filters", {})
    implicit = state.get("implicit_preferences", {})

    summary_parts = []

    # Format explicit filters
    if filters:
        summary_parts.append("**Search Criteria:**")
        for key, value in filters.items():
            if value:
                summary_parts.append(f"  - {key.replace('_', ' ').title()}: {value}")

    # Format implicit preferences
    if implicit:
        summary_parts.append("\n**Inferred Preferences:**")
        for key, value in implicit.items():
            if value:
                if isinstance(value, list):
                    summary_parts.append(f"  - {key.replace('_', ' ').title()}: {', '.join(value)}")
                else:
                    summary_parts.append(f"  - {key.replace('_', ' ').title()}: {value}")

    return "\n".join(summary_parts) if summary_parts else "No preferences captured yet."
