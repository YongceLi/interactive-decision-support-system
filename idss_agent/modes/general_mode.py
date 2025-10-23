"""
General mode - Handle greetings, meta questions, off-topic conversations.

Triggered by "general" intent - greetings, thanks, system questions, unclear queries.
"""
from langchain_openai import ChatOpenAI
from langchain_core.messages import AIMessage
from idss_agent.state import VehicleSearchState
from idss_agent.logger import get_logger

logger = get_logger("modes.general")


def run_general_mode(state: VehicleSearchState) -> VehicleSearchState:
    """
    General mode handler - simple conversational responses.

    Handles:
    - Greetings: "Hello", "Hi"
    - Thanks: "Thanks", "Thank you"
    - Meta questions: "What can you do?", "Help"
    - Off-topic or unclear queries

    Uses simple LLM response with last 3 messages for context.

    Args:
        state: Current vehicle search state

    Returns:
        Updated state with ai_response (no vehicles)
    """
    logger.info("General mode: Handling general conversation")

    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.7)

    system_prompt = """You are a friendly vehicle shopping assistant.

The user's message is a greeting, general question, or off-topic.

Respond warmly and helpfully:
- Greetings: Welcome them and briefly explain what you can help with
- Meta questions: Describe your capabilities (finding vehicles, comparing cars, answering questions)
- Thanks/acknowledgments: Acknowledge and offer further assistance
- Off-topic: Politely redirect to vehicle-related topics

Keep your response brief (1-2 sentences), friendly, and conversational.

Your main capabilities:
1. Help users find and buy vehicles (interview process, recommendations)
2. Browse and explore vehicles casually
3. Compare vehicles and analyze safety/MPG/features data
4. Answer questions about cars and automotive topics"""

    # Use last 3 messages for context
    recent = state["conversation_history"][-3:] if len(state["conversation_history"]) > 3 else state["conversation_history"]

    messages = [{"role": "system", "content": system_prompt}]
    for msg in recent:
        messages.append({
            "role": "user" if msg.type == "human" else "assistant",
            "content": msg.content
        })

    response = llm.invoke(messages)
    state["ai_response"] = response.content

    # Add AI response to conversation history
    state["conversation_history"].append(AIMessage(content=response.content))

    return state
