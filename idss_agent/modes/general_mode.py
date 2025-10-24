"""
General mode - Handle greetings, meta questions, off-topic conversations.

Triggered by "general" intent - greetings, thanks, system questions, unclear queries.
"""
from typing import Optional, Callable
from langchain_openai import ChatOpenAI
from langchain_core.messages import AIMessage, SystemMessage, HumanMessage
from idss_agent.state import VehicleSearchState, AgentResponse
from idss_agent.logger import get_logger

logger = get_logger("modes.general")


def run_general_mode(
    state: VehicleSearchState,
    progress_callback: Optional[Callable[[dict], None]] = None
) -> VehicleSearchState:
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
        progress_callback: Optional callback for progress updates

    Returns:
        Updated state with ai_response (no vehicles)
    """
    logger.info("General mode: Handling general conversation")

    # Emit progress: Generating response
    if progress_callback:
        progress_callback({
            "step_id": "generating_response",
            "description": "Preparing response",
            "status": "in_progress"
        })

    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.7)
    structured_llm = llm.with_structured_output(AgentResponse)

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
4. Answer questions about cars and automotive topics

Additionally generate:
- quick_replies: Short answer options (less than 5 words, less than 5 options) that the USER can click to answer if you ask a direct question. Leave null otherwise.
- suggested_followups: less than 5 short phrases representing what the USER might want to say or ask next. These are the user's potential next inputs to guide them into productive modes. Examples of what the USER might say: "Find me a vehicle", "Browse popular SUVs", "Compare sedan safety", "Show me trucks", "I want an sedan", ...
"""

    # Use last 3 messages for context
    recent = state["conversation_history"][-3:] if len(state["conversation_history"]) > 3 else state["conversation_history"]

    messages = [SystemMessage(content=system_prompt)]
    messages.extend(recent)

    response: AgentResponse = structured_llm.invoke(messages)
    state["ai_response"] = response.ai_response
    state["quick_replies"] = response.quick_replies
    state["suggested_followups"] = response.suggested_followups

    # Add AI response to conversation history
    state["conversation_history"].append(AIMessage(content=response.ai_response))

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
