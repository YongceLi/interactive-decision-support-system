"""
Complete vehicle search agent with intent-based routing.

Architecture:
1. Classify user intent on every message
2. Route to appropriate mode based on intent:
   - buying: Interview workflow (if not interviewed) or recommendation updates
   - browsing: Discovery mode (casual exploration)
   - research: Analytical mode (data-driven queries)
   - general: Simple conversational responses
"""
from datetime import datetime
from idss_agent.logger import get_logger
from idss_agent.state import VehicleSearchState, create_initial_state, add_user_message, add_ai_message
from idss_agent.components.intent_classifier import classify_intent
from idss_agent.modes import run_buying_mode, run_discovery_mode, run_analytical_mode, run_general_mode
from idss_agent.workflows.interview_workflow import run_interview_workflow

logger = get_logger("agent")


def run_agent(user_input: str, state: VehicleSearchState = None) -> VehicleSearchState:
    """
    Run the vehicle search agent with intent-based routing.

    Flow:
    1. Add user message to history
    2. Classify intent (buying/browsing/research/general)
    3. Route to appropriate mode
    4. Return updated state

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

    # ALWAYS classify intent (runs on every user message)
    logger.info("Classifying user intent...")
    intent_result = classify_intent(state["conversation_history"])

    # Log intent classification
    intent_record = {
        "intent": intent_result.intent,
        "confidence": intent_result.confidence,
        "reasoning": intent_result.reasoning,
        "timestamp": datetime.now().isoformat(),
        "message_index": len(state["conversation_history"]) - 1
    }
    state["intent_history"].append(intent_record)

    # Track previous mode for switch detection
    previous_mode = state.get("current_mode")

    # Update current intent
    state["current_intent"] = intent_result.intent

    # Route to appropriate mode based on intent
    if intent_result.intent == "buying":
        # BUYING MODE
        state["current_mode"] = "buying"

        # Check if interviewed
        if not state.get("interviewed", False):
            # NOT interviewed - run interview workflow
            logger.info("Buying mode: Running interview workflow...")
            result = run_interview_workflow(user_input, state)
        else:
            # ALREADY interviewed - update recommendations
            logger.info("Buying mode: Interview complete, updating recommendations...")
            result = run_buying_mode(state)

    elif intent_result.intent == "browsing":
        # DISCOVERY MODE (browsing)
        state["current_mode"] = "discovery"
        logger.info("Discovery mode: Browsing vehicles...")
        result = run_discovery_mode(state)

    elif intent_result.intent == "research":
        # ANALYTICAL MODE (research)
        state["current_mode"] = "analytical"
        logger.info("Analytical mode: Answering analytical question...")
        result = run_analytical_mode(state)

    else:  # general
        # GENERAL MODE
        state["current_mode"] = "general"
        logger.info("General mode: Handling general conversation...")
        result = run_general_mode(state)

    # Track mode switches
    if previous_mode and previous_mode != result["current_mode"]:
        result["mode_switch_count"] = result.get("mode_switch_count", 0) + 1
        logger.info(f"Mode switched: {previous_mode} → {result['current_mode']}")

    # Add AI response to conversation history if not already added
    # (Some modes like general_mode already add it)
    if result.get('ai_response'):
        # Check if AI message was already added (general mode adds it)
        last_msg = result["conversation_history"][-1] if result["conversation_history"] else None
        is_ai_msg = hasattr(last_msg, 'type') and last_msg.type == 'ai'
        is_same_content = last_msg.content == result['ai_response'] if last_msg else False

        if not (is_ai_msg and is_same_content):
            # Don't add if interview is ending - will be added after recommendation
            should_skip = (result.get('_interview_should_end') is True and not result.get('interviewed'))
            if not should_skip:
                result = add_ai_message(result, result['ai_response'])

    return result
