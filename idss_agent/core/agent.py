"""
Complete vehicle search agent with SUPERVISOR architecture.

Architecture:
1. Add user message to history
2. Supervisor analyzes request (can detect multiple intents)
3. Supervisor delegates to sub-agents as needed
4. Supervisor synthesizes unified response

"""
from datetime import datetime
from typing import Optional, Callable, Dict, Any
from idss_agent.utils.logger import get_logger
from idss_agent.state.schema import VehicleSearchState, create_initial_state, add_user_message, add_ai_message
from idss_agent.core.supervisor import run_supervisor
from idss_agent.utils.telemetry import start_span, finish_span, append_span

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
    turn_span = start_span("turn", {"input_chars": len(user_input)})
    result = run_supervisor(user_input, state, progress_callback)
    append_span(result, finish_span(turn_span))

    # Summarize latency for logging/observability
    telemetry = result.get("_telemetry", [])
    if telemetry:
        turn_duration = None
        spans_summary = []
        aggregated: Dict[str, Dict[str, Any]] = {}

        for span in telemetry:
            name = span.get("name")
            duration = span.get("duration_ms")
            spans_summary.append({
                "name": name,
                "duration_ms": duration,
                "metadata": span.get("metadata"),
            })

            if name and isinstance(duration, (int, float)):
                agg = aggregated.setdefault(name, {"count": 0, "total_ms": 0.0})
                agg["count"] += 1
                agg["total_ms"] += duration
                if name == "turn":
                    turn_duration = duration

        aggregates_serialized = {
            name: {
                "count": stats["count"],
                "total_ms": round(stats["total_ms"], 2),
                "avg_ms": round(stats["total_ms"] / stats["count"], 2),
            }
            for name, stats in aggregated.items()
        }

        result["_latency"] = {
            "turn_duration_ms": round(turn_duration, 2) if turn_duration is not None else None,
            "spans": spans_summary,
            "aggregates": aggregates_serialized,
        }

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
