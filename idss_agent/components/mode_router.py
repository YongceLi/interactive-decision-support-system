"""
Mode router node - classifies user message as discovery or analytical.
Also handles routing for recommendation updates.
"""
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage
from idss_agent.state import VehicleSearchState, get_latest_user_message


def route_conversation_mode(state: VehicleSearchState) -> str:
    """
    Determine conversation mode based on current user message.

    Modes:
    - "discovery": User exploring options, refining search, expressing preferences
    - "analytical": User asking about specific vehicle(s) or detailed comparisons

    This is used for conditional routing in the workflow graph.

    Args:
        state: Current vehicle search state

    Returns:
        "discovery" or "analytical"
    """

    user_msg = get_latest_user_message(state)

    if not user_msg:
        return "discovery"  # Default to discovery

    # Get last 2 turns (4 messages) for context
    recent_history = state.get("conversation_history", [])[-4:]

    # Format recent conversation
    context_str = ""
    if recent_history:
        context_lines = []
        for msg in recent_history:
            if isinstance(msg, HumanMessage):
                context_lines.append(f"User: {msg.content}")
            elif isinstance(msg, AIMessage):
                # Truncate long responses for context
                content = msg.content[:200] + "..." if len(msg.content) > 200 else msg.content
                context_lines.append(f"Assistant: {content}")
        context_str = "\n".join(context_lines)

    # Classification prompt
    classification_prompt = f"""
You are a classifier for a vehicle shopping assistant.

Classify this user message as either "discovery" or "analytical":

**Discovery** - User is exploring options, refining search, or expressing preferences:
- "I want an SUV"
- "Show me cheaper options"
- "What about electric vehicles?"
- "Something with better mileage"
- "I prefer Toyota or Honda"
- "Make it under $30k"

**Analytical** - User asking about specific vehicle(s) or detailed comparison:
- "Tell me more about #3"
- "Compare the first two cars"
- "What's the safety rating of the Toyota?"
- "Is #5 a good deal?"
- "How does the Honda compare to the Mazda?"
- "Show me photos of #1"
- "What are the features of this vehicle?"

Recent conversation context:
{context_str}

Latest user message: "{user_msg}"

Respond with ONLY one word: discovery or analytical
"""

    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    response = llm.invoke(classification_prompt)
    mode = response.content.strip().lower()

    # Validate response
    if mode not in ["discovery", "analytical"]:
        print(f"Warning: Invalid mode '{mode}', defaulting to discovery")
        mode = "discovery"

    return mode


def should_update_recommendations(state: VehicleSearchState) -> str:
    """
    Determine if we need to update the recommendation list.

    Only update recommendations when:
    1. No vehicles exist yet (first search or error recovery)
    2. Explicit filters have changed (new search criteria)

    Args:
        state: Current vehicle search state

    Returns:
        "update" - Need to fetch new recommendations
        "skip" - Use existing recommendations
    """
    # Always update if no vehicles yet
    if not state.get('recommended_vehicles'):
        return "update"

    # Check if filters changed
    current_filters = state.get('explicit_filters', {})
    previous_filters = state.get('previous_filters', {})

    if current_filters != previous_filters:
        return "update"

    return "skip"
