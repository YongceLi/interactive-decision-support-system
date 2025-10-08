"""
Mode router node - classifies user message as discovery or analytical.
"""
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage
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

User message: "{user_msg}"

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
