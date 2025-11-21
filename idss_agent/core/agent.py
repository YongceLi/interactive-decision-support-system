"""
Complete product search agent with SUPERVISOR architecture.

Architecture:
1. Add user message to history
2. Supervisor analyzes request (can detect multiple intents)
3. Supervisor delegates to sub-agents as needed
4. Supervisor synthesizes unified response

"""
from datetime import datetime
from typing import Optional, Callable, Dict, Any
from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from idss_agent.utils.logger import get_logger
from idss_agent.state.schema import ProductSearchState, create_initial_state, add_user_message, add_ai_message
from idss_agent.core.supervisor import run_supervisor
from idss_agent.utils.telemetry import start_span, finish_span, append_span

logger = get_logger("agent")


class ElectronicsDomainCheck(BaseModel):
    """Check if query is about electronics."""
    is_electronics_related: bool = Field(
        description="True if the query is about electronics, PC components, or consumer tech products. False if about cars, vehicles, food, clothing, or other non-electronics topics."
    )
    reasoning: str = Field(
        description="Brief explanation of why this is or isn't electronics-related"
    )


def is_electronics_query(user_input: str) -> bool:
    """
    Check if user query is about electronics/tech products.
    
    Args:
        user_input: User's message/query
        
    Returns:
        True if query is electronics-related, False otherwise
    """
    # Skip check for very short messages or greetings
    user_input_lower = user_input.strip().lower()
    if len(user_input_lower) < 3:
        return True  # Allow short messages like "hi" to pass through
    
    # Quick keyword check for obvious electronics topics (if found, definitely electronics)
    electronics_keywords = [
        "cpu", "gpu", "ram", "motherboard", "psu", "power supply", "ssd", "hdd", "storage",
        "monitor", "keyboard", "mouse", "speaker", "headphone", "webcam",
        "smartphone", "tablet", "laptop", "smartwatch", "smart home",
        "gaming", "console", "router", "switch", "modem", "wifi",
        "tv", "projector", "streaming", "pc", "computer", "electronics",
        "compatible", "compatibility", "graphics card", "processor"
    ]
    
    # Quick keyword check for obvious non-electronics topics
    non_electronics_keywords = [
        "car", "vehicle", "automobile", "truck", "suv", "sedan", "honda", "toyota", 
        "ford", "bmw", "mercedes", "tesla", "buy a car", "car dealer", "mileage",
        "food", "restaurant", "recipe", "cooking", "meal", "grocery",
        "clothing", "clothes", "shirt", "pants", "dress", "shoes", "fashion",
        "house", "apartment", "real estate", "rent", "mortgage", "property",
        "job", "employment", "career", "resume", "interview", "salary",
        "travel", "hotel", "flight", "vacation", "trip", "booking"
    ]
    
    # If electronics keywords are present, definitely electronics
    if any(keyword in user_input_lower for keyword in electronics_keywords):
        return True
    
    # If non-electronics keywords are present, use LLM to confirm
    if any(keyword in user_input_lower for keyword in non_electronics_keywords):
        # Use LLM to confirm it's not electronics-related
        llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
        structured_llm = llm.with_structured_output(ElectronicsDomainCheck)
        
        try:
            result = structured_llm.invoke([
                SystemMessage(content="""You are a domain classifier for an electronics shopping assistant.

Determine if the user's query is about electronics, PC components, or consumer tech products.

**Electronics-related topics include:**
- PC components: CPU, GPU, RAM, motherboard, PSU, storage (SSD/HDD), case, cooler
- Peripherals: monitors, keyboards, mice, speakers, headphones, webcams
- Consumer electronics: smartphones, tablets, laptops, smartwatches, smart home devices
- Gaming: gaming consoles, gaming accessories, gaming chairs
- Audio/video: TVs, projectors, audio equipment, streaming devices
- Networking: routers, switches, modems, WiFi extenders
- General tech: software, apps, tech support questions about electronics

**NOT electronics-related (should return False):**
- Cars, vehicles, automobiles, car shopping, car dealers
- Food, restaurants, recipes, cooking
- Clothing, fashion, apparel
- Real estate, housing, apartments
- Jobs, employment, careers
- Travel, hotels, flights
- General questions unrelated to shopping for electronics

Return True only if the query is clearly about electronics shopping or electronics products."""),
                HumanMessage(content=f"User query: {user_input}")
            ])
            
            logger.info(f"Electronics domain check: {result.is_electronics_related} - {result.reasoning}")
            return result.is_electronics_related
            
        except Exception as e:
            logger.warning(f"Error checking electronics domain: {e}, defaulting to True")
            return True  # Default to allowing if check fails
    
    # If no obvious keywords either way, assume it's electronics-related (greetings, general questions)
    return True


def run_agent(
    user_input: str,
    state: ProductSearchState = None,
    progress_callback: Optional[Callable[[dict], None]] = None
) -> ProductSearchState:
    """
    Run the product search agent with SUPERVISOR architecture.

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

    # Check if query is electronics-related
    if not is_electronics_query(user_input):
        logger.info(f"Non-electronics query detected: {user_input[:100]}")
        # Return early with electronics-only message
        electronics_message = (
            "I'm a specialized electronics shopping assistant, and I can only help with electronics and tech products. "
            "I can assist you with:\n\n"
            "• **PC Components**: CPUs, GPUs, RAM, motherboards, power supplies, storage drives, cases, coolers\n"
            "• **Peripherals**: Monitors, keyboards, mice, speakers, headphones, webcams\n"
            "• **Consumer Electronics**: Smartphones, tablets, laptops, smartwatches, smart home devices\n"
            "• **Gaming**: Gaming consoles, gaming accessories, gaming equipment\n"
            "• **Audio/Video**: TVs, projectors, audio equipment, streaming devices\n"
            "• **Networking**: Routers, switches, modems, WiFi equipment\n\n"
            "If you're looking for electronics, I'd be happy to help! What are you shopping for?"
        )
        state["ai_response"] = electronics_message
        state["quick_replies"] = None
        state["suggested_followups"] = []
        state["comparison_table"] = None
        state["compatibility_result"] = None
        state = add_ai_message(state, electronics_message)
        
        # Emit progress: Complete
        if progress_callback:
            progress_callback({
                "step_id": "processing",
                "description": "Response ready",
                "status": "completed"
            })
        
        return state

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

        # Update running latency statistics
        existing_stats = (
            result.get("_latency_stats")
            or state.get("_latency_stats")  # type: ignore[arg-type]
            or {}
        )
        stats_turn_count = int(existing_stats.get("turn_count", 0))
        stats_total_ms = float(existing_stats.get("total_turn_ms", 0.0))

        if isinstance(turn_duration, (int, float)):
            stats_turn_count += 1
            stats_total_ms += float(turn_duration)
            average_turn_ms = round(stats_total_ms / stats_turn_count, 2)
        else:
            average_turn_ms = existing_stats.get("average_turn_ms")

        latency_snapshot = {
            "turn_duration_ms": round(turn_duration, 2) if turn_duration is not None else None,
            "spans": spans_summary,
            "aggregates": aggregates_serialized,
        }

        latency_snapshot["running_average_ms"] = average_turn_ms
        latency_snapshot["turn_count"] = stats_turn_count

        result["_latency"] = latency_snapshot
        result["_latency_stats"] = {
            "turn_count": stats_turn_count,
            "total_turn_ms": round(stats_total_ms, 2),
            "average_turn_ms": average_turn_ms,
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
