"""
General mode - Handle greetings, meta questions, off-topic conversations.

Triggered by "general" intent - greetings, thanks, system questions, unclear queries.
"""
from typing import Optional, Callable
from langchain_openai import ChatOpenAI
from langchain_core.messages import AIMessage, SystemMessage, HumanMessage
from idss_agent.config import get_config
from idss_agent.prompt_loader import render_prompt
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

    # Get configuration
    config = get_config()
    model_config = config.get_model_config('general')

    # Create LLM with config parameters
    llm = ChatOpenAI(
        model=model_config['name'],
        temperature=model_config['temperature'],
        max_tokens=model_config.get('max_tokens', 500)
    )
    structured_llm = llm.with_structured_output(AgentResponse)

    # Load system prompt from template
    system_prompt = render_prompt('general.j2')

    # Use last 3 messages for context
    recent = state["conversation_history"][-3:] if len(state["conversation_history"]) > 3 else state["conversation_history"]

    messages = [SystemMessage(content=system_prompt)]
    messages.extend(recent)

    response: AgentResponse = structured_llm.invoke(messages)
    state["ai_response"] = response.ai_response
    state["quick_replies"] = response.quick_replies
    state["suggested_followups"] = response.suggested_followups
    state["comparison_table"] = None  # Clear comparison table in general mode

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
