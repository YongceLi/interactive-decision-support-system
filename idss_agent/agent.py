"""
Complete vehicle search agent with supervisor architecture.

Two workflows:
1. Interview workflow - asks questions to understand needs
2. Supervisor workflow - orchestrates tools to help after interview
"""
from idss_agent.logger import get_logger
from idss_agent.state import VehicleSearchState, create_initial_state, add_user_message, add_ai_message
from idss_agent.workflows import run_interview_workflow, run_supervisor_workflow

logger = get_logger("agent")


def run_agent(user_input: str, state: VehicleSearchState = None) -> VehicleSearchState:
    """
    Run the vehicle search agent with user input.

    Routes to either:
    - Interview workflow (if not interviewed yet)
    - Supervisor workflow (if interview complete)

    Args:
        user_input: User's message/query
        state: Optional existing state (for continuing conversations)

    Returns:
        Updated state after processing
    """
    # Create initial state if none provided
    if state is None:
        state = create_initial_state()

    # Add user message to conversation history
    state = add_user_message(state, user_input)

    # Route to appropriate workflow
    if not state.get("interviewed", False):
        # INTERVIEW WORKFLOW
        logger.info("Running interview workflow...")
        result = run_interview_workflow(user_input, state)
    else:
        # SUPERVISOR WORKFLOW
        logger.info("Running supervisor workflow...")
        result = run_supervisor_workflow(user_input, state)

    # Add AI response to conversation history
    if result.get('ai_response'):
        # Don't add if interview is ending (should_end=True) - will be added after recommendation
        # Add in all other cases: interview continuing, interview ended with recommendation, or supervisor
        should_skip = (result.get('_interview_should_end') is True)
        if not should_skip:
            result = add_ai_message(result, result['ai_response'])

    return result
