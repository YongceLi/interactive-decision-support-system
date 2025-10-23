"""
Semantic parser node for extracting vehicle search criteria from user input.
"""
import json
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from idss_agent.logger import get_logger
from idss_agent.state import VehicleSearchState, get_latest_user_message

logger = get_logger("components.semantic_parser")


# System prompt for the semantic parser
SEMANTIC_PARSER_PROMPT = """
You are a semantic parser for a vehicle search assistant. Your job is to extract structured information from the ENTIRE conversation.

**INSTRUCTION**: First, check if the LATEST user message contains NEW vehicle search criteria or filter modifications.

- **If YES (new filters)**: Extract and return COMPLETE filters representing current search intent
- **If NO (follow-up question)**: Return EMPTY filters `{"has_new_filters": false, "explicit_filters": {}, "implicit_preferences": {}}` to indicate NO CHANGE

**Examples of NO NEW FILTERS (return empty {}):**
- "Tell me more about this vehicle"
- "Can you show me photos?"
- "What's the mileage on that one?"
- "Compare #1 and #2"
- "What's the safety rating?"
- "How much is it?"
- General questions about already-shown vehicles

**Examples of NEW FILTERS (extract and return):**
- "Show me SUVs under $30k"
- "I want a red one instead"
- "Change to Honda"
- "Under 50k miles please"
- "In California"

Given the conversation history, extract:

1. **Explicit Filters**: Clear, stated preferences about vehicles (make, model, price, color, etc.)
2. **Implicit Preferences**: Inferred preferences about priorities, lifestyle, concerns, etc.

Output Format (JSON):
{
  "has_new_filters": true,  // or false if latest message is just a follow-up question
  "explicit_filters": {
    "make": "Toyota",  // or "Toyota,Honda" for multiple
    "model": "Camry",  // or "Camry,Accord" for multiple, don't include trim level.
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
- Generate COMPLETE filters based on the ENTIRE conversation, not just the latest message
- If user changes their preference, replace the old filters with the new ones
- For colors, use comma-separated strings: "white,black,silver"
- For ranges, use format "min-max": "2018-2020", "15000-25000"
- For multiple makes/models/body styles, use comma-separated: "Toyota,Honda"
- If user says "around $20000", use a reasonable range like "18000-22000"
- If user says "recent", use last 3-5 years
- If user says "low mileage", use "0-30000"
- Infer implicit preferences from context clues (e.g., "family" → family-oriented, safety priority)

Examples:

Example 1 - Initial search:
User: "I'm looking for a reliable sedan under $25k"
Output:
{
  "has_new_filters": true,
  "explicit_filters": {"body_style": "sedan", "price": "0-25000"},
  "implicit_preferences": {"priorities": ["reliability"], "budget_sensitivity": "moderate"}
}

Example 2 - Multiple options:
User: "Show me Toyota Camrys or Honda Accords from 2018-2020 in white or silver"
Output:
{
  "has_new_filters": true,
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

Example 3 - Changing preference (REPLACE, not merge):
Conversation:
  User: "Show me Honda Accords"
  Assistant: "Here are some Honda Accords..."
  User: "Actually, I want Toyotas instead"
Output:
{
  "has_new_filters": true,
  "explicit_filters": {
    "make": "Toyota"
  },
  "implicit_preferences": {
    "brand_affinity": ["Toyota"]
  }
}

Example 4 - Refining search (keep existing + add new):
Conversation:
  User: "Show me Toyota Camrys"
  Assistant: "Here are some Camrys..."
  User: "Under $25k please"
Output:
{
  "has_new_filters": true,
  "explicit_filters": {
    "make": "Toyota",
    "model": "Camry",
    "price": "0-25000"
  },
  "implicit_preferences": {
    "brand_affinity": ["Toyota"],
    "budget_sensitivity": "budget-conscious"
  }
}

Example 5 - Follow-up question (NO new filters):
Conversation:
  User: "Show me SUVs under $40k"
  Assistant: "Here are some great options! #1: 2025 Acura TLX..."
  User: "Can you tell me more about this vehicle?"
Output:
{
  "has_new_filters": false,
  "explicit_filters": {},
  "implicit_preferences": {}
}

Now parse the conversation and output ONLY valid JSON, no other text.
"""


def semantic_parser_node(state: VehicleSearchState) -> VehicleSearchState:
    """
    Semantic parser node that extracts vehicle preferences from the ENTIRE conversation.

    This node:
    1. Analyzes the COMPLETE conversation history
    2. Uses an LLM to generate COMPLETE filters representing current search intent
    3. REPLACES filters entirely (not merge) based on LLM's analysis
    4. Stores previous filters for history tracking

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

    # Build COMPLETE conversation context from ALL LangChain messages
    history_context = "\n".join([
        f"{'User' if isinstance(msg, HumanMessage) else 'Assistant'}: {msg.content}"
        for msg in state.get("conversation_history", [])  # ALL messages, not just last 5
    ])

    # Store current filters as previous (for history tracking)
    current_filters = state.get("explicit_filters", {})
    current_implicit = state.get("implicit_preferences", {})

    context_info = f"""
COMPLETE Conversation History:
{history_context}

Based on the ENTIRE conversation above, extract the user's CURRENT search intent.
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

        # Check if there are new filters
        has_new_filters = parsed_data.get("has_new_filters", True)  # Default to True for backward compatibility

        if not has_new_filters:
            # User is asking a follow-up question, not providing new filters
            logger.info("No new filters detected - user asking follow-up question, keeping existing filters")
            return state

        # REPLACE explicit filters entirely (not merge!)
        new_filters = parsed_data.get("explicit_filters", {})

        # Log the change for debugging
        if new_filters != current_filters:
            logger.info(f"Filters changed: {current_filters} → {new_filters}")
        else:
            logger.info("New filters extracted (same as current)")

        state["explicit_filters"] = new_filters  # REPLACE, not merge!

        # REPLACE implicit preferences entirely
        new_implicit = parsed_data.get("implicit_preferences", {})
        state["implicit_preferences"] = new_implicit  # REPLACE, not merge!

    except json.JSONDecodeError as e:
        # If parsing fails, log it but don't crash
        logger.warning(f"Failed to parse LLM response as JSON: {e}")
        logger.debug(f"Response content: {response.content}")

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
