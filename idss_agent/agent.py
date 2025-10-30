"""
Complete vehicle search agent with SUPERVISOR architecture.

Architecture:
1. Add user message to history
2. Supervisor analyzes request (can detect multiple intents)
3. Supervisor delegates to sub-agents as needed
4. Supervisor synthesizes unified response

"""
from datetime import datetime
from typing import Optional, Callable
from idss_agent.logger import get_logger
from idss_agent.state import VehicleSearchState, create_initial_state, add_user_message, add_ai_message
from idss_agent.supervisor import run_supervisor

logger = get_logger("agent")


def run_agent(
    user_input: str,
    state: VehicleSearchState = None,
    progress_callback: Optional[Callable[[dict], None]] = None
) -> VehicleSearchState:
    """
    Run the vehicle search agent with SUPERVISOR architecture.

    Flow:
    1. Add user message to history
    2. Supervisor analyzes request (detects multiple intents)
    3. Supervisor delegates to sub-agents
    4. Supervisor synthesizes unified response
    5. Return updated state

    Args:
        user_input: User's message/query
        state: Optional existing state (for continuing conversations)
        progress_callback: Optional callback for progress updates (for UI streaming)

    Returns:
        Updated state after processing
    """
    # Create initial state if none provided
    if state is None:
        state = create_initial_state()

    # Add user message to conversation history
    state = add_user_message(state, user_input)

    # Emit progress: Starting processing
    if progress_callback:
        progress_callback({
            "step_id": "processing",
            "description": "Understanding your request",
            "status": "in_progress"
        })

    # Run supervisor to handle request
    logger.info("Running supervisor agent...")
    result = run_supervisor(user_input, state, progress_callback)

    # Set mode to 'supervisor' (for backward compatibility tracking)
    result["current_mode"] = "supervisor"

    # Emit progress: Complete
    if progress_callback:
        progress_callback({
            "step_id": "processing",
            "description": "Response ready",
            "status": "completed"
        })

    # Add AI response to conversation history if not already added
    if result.get('ai_response'):
        # Check if AI message was already added
        last_msg = result["conversation_history"][-1] if result["conversation_history"] else None
        is_ai_msg = hasattr(last_msg, 'type') and last_msg.type == 'ai'
        is_same_content = last_msg.content == result['ai_response'] if last_msg else False

        if not (is_ai_msg and is_same_content):
            # Don't add if interview is ending - will be added after recommendation
            should_skip = (result.get('_interview_should_end') is True and not result.get('interviewed'))
            if not should_skip:
                result = add_ai_message(result, result['ai_response'])

    return result
