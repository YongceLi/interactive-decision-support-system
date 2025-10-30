"""
Supervisor agent - orchestrates multiple sub-agents to handle compound requests.

Architecture:
1. Analyze request → detect multiple needs
2. Delegate to sub-agents (they return structured data)
3. Synthesize unified response

Handles scenarios like:
- "I want a black one, what's the maintenance cost?" (search + analytical)
- "Compare Honda Accord vs Toyota Camry" (analytical comparison)
- "Show me vehicles under $30k" (search only)
"""
from typing import Optional, Callable, Dict, Any, List
from idss_agent.state import VehicleSearchState
from idss_agent.request_analyzer import analyze_request, RequestAnalysis
from idss_agent.components.semantic_parser import semantic_parser_node
from idss_agent.components.recommendation import update_recommendation_list
from idss_agent.components.analytical import analytical_agent
from idss_agent.components.discovery import discovery_agent
from idss_agent.workflows.interview_workflow import run_interview_workflow
from idss_agent.modes.general_mode import run_general_mode
from idss_agent.llm_synthesizer import llm_synthesize_multi_mode, format_vehicle_summary_simple
from idss_agent.logger import get_logger

logger = get_logger("supervisor")


class SubAgentResults(Dict[str, Any]):
    """Container for sub-agent results."""
    pass


def run_analytical_sub_agent(
    questions: List[str],
    state: VehicleSearchState,
    progress_callback: Optional[Callable[[dict], None]] = None
) -> Dict[str, Any]:
    """
    Run analytical sub-agent silently (returns data, doesn't set ai_response).

    Args:
        questions: List of analytical questions to answer
        state: Current state
        progress_callback: Optional progress callback

    Returns:
        Dict with analytical answers and comparison table if applicable
    """
    logger.info(f"Analytical sub-agent: answering {len(questions)} question(s)")

    # Use existing analytical agent but capture its output
    state_copy = state.copy()
    state_copy = analytical_agent(state_copy, progress_callback)

    return {
        'answer': state_copy.get('ai_response', ''),
        'comparison_table': state_copy.get('comparison_table'),
        'suggested_followups': state_copy.get('suggested_followups', [])
    }


def run_search_sub_agent(
    state: VehicleSearchState,
    progress_callback: Optional[Callable[[dict], None]] = None
) -> Dict[str, Any]:
    """
    Run search sub-agent silently (returns vehicles, doesn't set ai_response).

    Args:
        state: Current state
        progress_callback: Optional progress callback

    Returns:
        Dict with vehicles and filters
    """
    logger.info("Search sub-agent: updating vehicle recommendations")

    # Update recommendations using existing function
    state_copy = state.copy()
    state_copy = update_recommendation_list(state_copy, progress_callback)

    return {
        'vehicles': state_copy.get('recommended_vehicles', []),
        'filters': state_copy.get('explicit_filters', {}),
        'suggestion_reasoning': state_copy.get('suggestion_reasoning')
    }


def run_interview_sub_agent(
    user_input: str,
    state: VehicleSearchState,
    progress_callback: Optional[Callable[[dict], None]] = None
) -> Dict[str, Any]:
    """
    Run interview sub-agent (returns interview response).

    This delegates to the full interview workflow since it needs to manage its own flow.

    Args:
        user_input: User message
        state: Current state
        progress_callback: Optional progress callback

    Returns:
        Dict with interview response and state updates
    """
    logger.info("Interview sub-agent: running interview workflow")

    # Interview workflow manages its own state and response
    # We'll let it run normally and return the result
    result_state = run_interview_workflow(user_input, state, progress_callback)

    return {
        'response': result_state.get('ai_response', ''),
        'interviewed': result_state.get('interviewed', False),
        'quick_replies': result_state.get('quick_replies'),
        'suggested_followups': result_state.get('suggested_followups', []),
        'updated_state': result_state
    }


def format_vehicle_summary(vehicles: List[Dict[str, Any]], max_count: int = 3) -> str:
    """
    Format top vehicles into a concise summary.

    Args:
        vehicles: List of vehicle dicts
        max_count: Maximum number to show

    Returns:
        Formatted string with vehicle summaries
    """
    if not vehicles:
        return "No vehicles found matching your criteria."

    summary_lines = []
    for i, vehicle in enumerate(vehicles[:max_count], 1):
        v = vehicle.get('vehicle', {})
        r = vehicle.get('retailListing', {})
        price = r.get('price', 0)
        miles = r.get('miles', 0)

        summary_lines.append(
            f"{i}. **{v.get('year')} {v.get('make')} {v.get('model')}** - "
            f"${price:,} ({miles:,} miles)"
        )

    total = len(vehicles)
    if total > max_count:
        summary_lines.append(f"\n...and {total - max_count} more vehicles available")

    return "\n".join(summary_lines)


def synthesize_response(
    analysis: RequestAnalysis,
    sub_agent_results: SubAgentResults,
    state: VehicleSearchState,
    user_input: str,
    progress_callback: Optional[Callable[[dict], None]] = None
) -> Dict[str, Any]:
    """
    Synthesize unified response from sub-agent results.

    Uses LLM synthesis for multi-mode, direct response for single mode.

    Args:
        analysis: Request analysis
        sub_agent_results: Results from sub-agents
        state: Current state
        user_input: Original user input
        progress_callback: Optional progress callback

    Returns:
        Dict with 'response', 'quick_replies', 'suggested_followups'
    """
    # Count active modes
    has_interview = 'interview' in sub_agent_results
    has_analytical = 'analytical' in sub_agent_results
    has_search = 'search' in sub_agent_results
    has_general = 'general' in sub_agent_results

    active_modes = sum([has_interview, has_analytical, has_search])

    # SINGLE MODE - Direct response (no synthesis needed)
    if active_modes == 1:
        logger.info("Single mode active - using direct response")

        # Interview only
        if has_interview:
            interview = sub_agent_results['interview']
            return {
                'response': interview['response'],
                'quick_replies': interview.get('quick_replies'),
                'suggested_followups': interview.get('suggested_followups', [])
            }

        # Analytical only
        if has_analytical:
            analytical = sub_agent_results['analytical']
            return {
                'response': analytical['answer'],
                'quick_replies': None,
                'suggested_followups': analytical.get('suggested_followups', [])
            }

        # Search only - use discovery agent for meaningful commentary
        if has_search:
            search = sub_agent_results['search']

            # Update state with search results
            state['recommended_vehicles'] = search.get('vehicles', [])
            if search.get('suggestion_reasoning'):
                state['suggestion_reasoning'] = search['suggestion_reasoning']

            # Use discovery agent to present vehicles conversationally
            # (highlights vehicle strengths instead of repeating price/mileage)
            state_copy = state.copy()
            state_copy = discovery_agent(state_copy, progress_callback)

            return {
                'response': state_copy['ai_response'],
                'quick_replies': state_copy.get('quick_replies'),
                'suggested_followups': state_copy.get('suggested_followups', [])
            }

        # General only
        if has_general:
            return {
                'response': sub_agent_results['general']['response'],
                'quick_replies': None,
                'suggested_followups': []
            }

    # MULTIPLE MODES - Use LLM synthesis for smooth blending
    if active_modes >= 2:
        logger.info(f"Multiple modes active ({active_modes}) - using LLM synthesis")

        # Build context for LLM
        context_parts = []
        if state.get('explicit_filters'):
            context_parts.append(f"Filters: {state['explicit_filters']}")
        if state.get('implicit_preferences'):
            prefs = state['implicit_preferences']
            if prefs.get('priorities'):
                context_parts.append(f"Priorities: {prefs['priorities']}")

        context = ", ".join(context_parts) if context_parts else ""

        # Use LLM to synthesize smooth response
        synthesized = llm_synthesize_multi_mode(
            sub_agent_results=sub_agent_results,
            user_input=user_input,
            context=context
        )

        return {
            'response': synthesized.ai_response,
            'quick_replies': synthesized.quick_replies,
            'suggested_followups': synthesized.suggested_followups
        }

    # Fallback (no modes active)
    return {
        'response': "I'm here to help you find the perfect vehicle. What are you looking for?",
        'quick_replies': None,
        'suggested_followups': [
            "I want to buy a car",
            "Show me vehicles",
            "What's a good car for..."
        ]
    }


def run_supervisor(
    user_input: str,
    state: VehicleSearchState,
    progress_callback: Optional[Callable[[dict], None]] = None
) -> VehicleSearchState:
    """
    Supervisor agent - orchestrates sub-agents to handle compound requests.

    Flow:
    1. Analyze request → detect needs
    2. Parse filters (if applicable)
    3. Delegate to sub-agents
    4. Synthesize unified response
    5. Update state

    Args:
        user_input: User's message
        state: Current conversation state
        progress_callback: Optional progress callback

    Returns:
        Updated state with unified response
    """
    logger.info("Supervisor: Analyzing request...")

    # Clear comparison table at start of each request (will be set again if current request generates one)
    state['comparison_table'] = None

    # 1. Analyze request to detect multiple intents
    analysis = analyze_request(user_input, state)

    # 2. Parse filters from user input (always do this)
    state = semantic_parser_node(state, progress_callback)

    # 3. Collect results from sub-agents
    sub_agent_results = SubAgentResults()

    # Priority 1: General conversation (if that's all it is)
    if analysis.is_general_conversation and not analysis.needs_search and not analysis.needs_analytical and not analysis.needs_interview:
        general_state = run_general_mode(state, progress_callback)
        return general_state

    # Priority 2: Handle interview + analytical/search (can be multiple)
    # NEW: Don't return early if interview + other needs detected
    filters_changed = state['explicit_filters'] != state.get('previous_filters', {})
    has_vehicles = len(state.get('recommended_vehicles', [])) > 0

    # Run analytical sub-agent if user asked explicit questions
    if analysis.needs_analytical and analysis.analytical_questions:
        logger.info("Running analytical sub-agent (user asked explicit questions)")
        analytical_result = run_analytical_sub_agent(
            analysis.analytical_questions,
            state,
            progress_callback
        )
        sub_agent_results['analytical'] = analytical_result

        # Update state with comparison table if applicable
        if analytical_result.get('comparison_table'):
            state['comparison_table'] = analytical_result['comparison_table']

    # Run search sub-agent if needed (but NOT if interview is needed - let interview handle search)
    # Interview workflow will conduct its own search after gathering preferences
    if not analysis.needs_interview:
        if analysis.needs_search or filters_changed or (analysis.has_filter_update and not has_vehicles):
            if filters_changed or not has_vehicles:
                logger.info("Running search sub-agent")
                search_result = run_search_sub_agent(state, progress_callback)
                sub_agent_results['search'] = search_result

                # Update state with new vehicles
                state['recommended_vehicles'] = search_result['vehicles']
                state['previous_filters'] = state['explicit_filters'].copy()
                if search_result.get('suggestion_reasoning'):
                    state['suggestion_reasoning'] = search_result['suggestion_reasoning']

    # Run interview sub-agent if needed (but DON'T return early)
    if analysis.needs_interview and not state.get('interviewed', False):
        logger.info("Running interview sub-agent")
        interview_result = run_interview_sub_agent(user_input, state, progress_callback)
        sub_agent_results['interview'] = interview_result

        # If ONLY interview (no analytical/search), return interview state directly
        if not sub_agent_results.get('analytical') and not sub_agent_results.get('search'):
            logger.info("Interview only - returning interview state directly")
            result_state = interview_result['updated_state']
            return result_state

        # Otherwise, continue to synthesis (interview + analytical/search)
        # Update state from interview
        state = interview_result['updated_state']

    # 4. Synthesize unified response (handles single or multi-mode)
    synthesis_result = synthesize_response(analysis, sub_agent_results, state, user_input, progress_callback)

    state['ai_response'] = synthesis_result['response']
    state['quick_replies'] = synthesis_result.get('quick_replies')
    state['suggested_followups'] = synthesis_result.get('suggested_followups', [])

    logger.info(f"Supervisor: Response synthesized ({len(synthesis_result['response'])} chars)")

    return state
