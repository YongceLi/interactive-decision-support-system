"""
Supervisor agent - orchestrates multiple sub-agents to handle compound requests.

Refactored architecture:
1. SupervisorOrchestrator - main coordination class
2. SubAgentRunner - encapsulates sub-agent execution
3. ResponseSynthesizer - handles response synthesis logic
4. Clear data structures with proper typing
"""
from typing import Optional, Callable, Dict, Any, List, Tuple
from dataclasses import dataclass, field
from enum import Enum
from concurrent.futures import ThreadPoolExecutor

from idss_agent.state.schema import ProductSearchState
from idss_agent.core.request_analyzer import analyze_request, RequestAnalysis
from idss_agent.processing.semantic_parser import semantic_parser_node
from idss_agent.processing.recommendation import update_recommendation_list
from idss_agent.agents.analytical import analytical_agent
from idss_agent.agents.discovery import discovery_agent
from idss_agent.agents.general import run_general_mode
from idss_agent.workflows.interview import run_interview_workflow
from idss_agent.processing.llm_synthesizer import llm_synthesize_multi_mode
from idss_agent.utils.logger import get_logger
from idss_agent.utils.telemetry import start_span, finish_span, append_span


class AgentMode(str, Enum):
    """Enumeration of available agent modes."""
    INTERVIEW = "interview"
    ANALYTICAL = "analytical"
    SEARCH = "search"
    GENERAL = "general"


@dataclass
class SubAgentResult:
    """Structured result from a sub-agent."""
    mode: AgentMode
    response: Optional[str] = None
    vehicles: Optional[List[Dict]] = None  # Contains products (field name kept for compatibility with SubAgentResult structure)
    comparison_table: Optional[Dict] = None
    filters: Optional[Dict] = None
    quick_replies: Optional[List[str]] = None
    suggested_followups: List[str] = field(default_factory=list)
    updated_state: Optional[ProductSearchState] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class SubAgentRunner:
    """Handles execution of individual sub-agents."""

    def __init__(self, progress_callback: Optional[Callable[[dict], None]] = None):
        self.progress_callback = progress_callback
        self.logger = get_logger("sub_agent_runner")

    def run_analytical(
        self,
        questions: List[str],
        state: ProductSearchState
    ) -> SubAgentResult:
        """
        Run analytical sub-agent.

        Args:
            questions: List of analytical questions to answer
            state: Current state

        Returns:
            SubAgentResult with analytical answers
        """
        self.logger.info(f"Running analytical agent for {len(questions)} question(s)")

        state_copy = state.copy()
        state_copy = analytical_agent(state_copy, self.progress_callback)

        return SubAgentResult(
            mode=AgentMode.ANALYTICAL,
            response=state_copy.get('ai_response'),
            comparison_table=state_copy.get('comparison_table'),
            suggested_followups=state_copy.get('suggested_followups', [])
        )

    def run_search(self, state: ProductSearchState) -> SubAgentResult:
        """
        Run search sub-agent.

        Args:
            state: Current state

        Returns:
            SubAgentResult with product search results
        """
        self.logger.info("Running search agent")

        state_copy = state.copy()
        state_copy = update_recommendation_list(state_copy, self.progress_callback)

        return SubAgentResult(
            mode=AgentMode.SEARCH,
            vehicles=state_copy.get('recommended_products', []),
            filters=state_copy.get('explicit_filters', {}),
            metadata={'suggestion_reasoning': state_copy.get('suggestion_reasoning')}
        )

    def run_interview(
        self,
        user_input: str,
        state: ProductSearchState
    ) -> SubAgentResult:
        """
        Run interview workflow.

        Args:
            user_input: User message
            state: Current state

        Returns:
            SubAgentResult with interview response and updated state
        """
        self.logger.info("Running interview workflow")

        result_state = run_interview_workflow(user_input, state, self.progress_callback)

        return SubAgentResult(
            mode=AgentMode.INTERVIEW,
            response=result_state.get('ai_response'),
            quick_replies=result_state.get('quick_replies'),
            suggested_followups=result_state.get('suggested_followups', []),
            updated_state=result_state,
            metadata={'interviewed': result_state.get('interviewed', False)}
        )

    def run_general(self, state: ProductSearchState) -> SubAgentResult:
        """
        Run general conversation mode.

        Args:
            state: Current state

        Returns:
            SubAgentResult with general conversation response
        """
        self.logger.info("Running general conversation")

        state_copy = run_general_mode(state, self.progress_callback)

        return SubAgentResult(
            mode=AgentMode.GENERAL,
            response=state_copy.get('ai_response'),
            suggested_followups=state_copy.get('suggested_followups', [])
        )


class ResponseSynthesizer:
    """Handles synthesis of multi-mode responses."""

    def __init__(self, progress_callback: Optional[Callable[[dict], None]] = None):
        self.progress_callback = progress_callback
        self.logger = get_logger("response_synthesizer")

    def synthesize(
        self,
        results: List[SubAgentResult],
        analysis: RequestAnalysis,
        state: ProductSearchState,
        user_input: str
    ) -> Dict[str, Any]:
        """
        Synthesize unified response from sub-agent results.

        Args:
            results: List of sub-agent results
            analysis: Request analysis
            state: Current state
            user_input: Original user input

        Returns:
            Dict with 'response', 'quick_replies', 'suggested_followups'
        """
        if len(results) == 0:
            return self._fallback_response()

        if len(results) == 1:
            return self._handle_single_mode(results[0], state)

        return self._handle_multi_mode(results, user_input, state)

    def _handle_single_mode(
        self,
        result: SubAgentResult,
        state: ProductSearchState
    ) -> Dict[str, Any]:
        """
        Handle single mode response.

        Args:
            result: Single sub-agent result
            state: Current state

        Returns:
            Dict with response data
        """
        self.logger.info(f"Single mode: {result.mode}")

        if result.mode == AgentMode.INTERVIEW:
            return {
                'response': result.response,
                'quick_replies': result.quick_replies,
                'suggested_followups': result.suggested_followups
            }

        if result.mode == AgentMode.ANALYTICAL:
            return {
                'response': result.response,
                'quick_replies': None,
                'suggested_followups': result.suggested_followups
            }

        if result.mode == AgentMode.SEARCH:
            # Use discovery agent for conversational presentation
            discovery_state = self._present_search_results(result, state)
            return {
                'response': discovery_state['ai_response'],
                'quick_replies': discovery_state.get('quick_replies'),
                'suggested_followups': discovery_state.get('suggested_followups', [])
            }

        if result.mode == AgentMode.GENERAL:
            return {
                'response': result.response,
                'quick_replies': None,
                'suggested_followups': result.suggested_followups
            }

    def _handle_multi_mode(
        self,
        results: List[SubAgentResult],
        user_input: str,
        state: ProductSearchState
    ) -> Dict[str, Any]:
        """
        Handle multi-mode response with LLM synthesis.

        Args:
            results: Multiple sub-agent results
            user_input: Original user input
            state: Current state

        Returns:
            Dict with synthesized response
        """
        self.logger.info(f"Multi-mode: {[r.mode.value for r in results]}")

        # Convert results to legacy format for LLM synthesizer
        sub_agent_results = {
            result.mode.value: self._result_to_dict(result)
            for result in results
        }

        # Build context
        context = self._build_context(state)

        # Synthesize
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

    def _present_search_results(
        self,
        result: SubAgentResult,
        state: ProductSearchState
    ) -> ProductSearchState:
        """
        Present search results using discovery agent.

        Args:
            result: Search sub-agent result
            state: Current state

        Returns:
            Updated state with discovery agent response
        """
        state_copy = state.copy()
        # Update recommended_products
        if result.vehicles:
            state_copy['recommended_products'] = result.vehicles

        if result.metadata.get('suggestion_reasoning'):
            state_copy['suggestion_reasoning'] = result.metadata['suggestion_reasoning']

        return discovery_agent(state_copy, self.progress_callback)

    def _build_context(self, state: ProductSearchState) -> str:
        """
        Build context string for synthesis.

        Args:
            state: Current state

        Returns:
            Context string
        """
        parts = []

        if state.get('explicit_filters'):
            parts.append(f"Filters: {state['explicit_filters']}")

        if state.get('implicit_preferences', {}).get('priorities'):
            parts.append(f"Priorities: {state['implicit_preferences']['priorities']}")

        return ", ".join(parts) if parts else ""

    def _result_to_dict(self, result: SubAgentResult) -> Dict[str, Any]:
        """
        Convert SubAgentResult to dict for legacy compatibility.

        Args:
            result: Sub-agent result to convert

        Returns:
            Dictionary representation
        """
        return {
            'response': result.response,
            'answer': result.response,  # For analytical mode
            'vehicles': result.vehicles,
            'comparison_table': result.comparison_table,
            'filters': result.filters,
            'quick_replies': result.quick_replies,
            'suggested_followups': result.suggested_followups,
            'updated_state': result.updated_state,
            **result.metadata
        }

    def _fallback_response(self) -> Dict[str, Any]:
        """
        Fallback when no modes are active.

        Returns:
            Default response
        """
        return {
            'response': "I'm here to help you find the right product. What are you shopping for today?",
            'quick_replies': None,
            'suggested_followups': [
                "Help me choose a CPU",
                "Show me products",
                "What's a good option for..."
            ]
        }


class SupervisorOrchestrator:
    """Main supervisor orchestrator."""

    def __init__(self, progress_callback: Optional[Callable[[dict], None]] = None):
        self.progress_callback = progress_callback
        self.runner = SubAgentRunner(progress_callback)
        self.synthesizer = ResponseSynthesizer(progress_callback)
        self.logger = get_logger("supervisor")

    def process_request(
        self,
        user_input: str,
        state: ProductSearchState
    ) -> ProductSearchState:
        """
        Main entry point - orchestrates request processing.

        Flow:
        1. Analyze request → detect intents
        2. Parse filters
        3. Determine which sub-agents to run
        4. Execute sub-agents
        5. Synthesize response
        6. Update state

        Args:
            user_input: User's message
            state: Current conversation state

        Returns:
            Updated state with unified response
        """
        self.logger.info("Processing request...")

        request_span = start_span("supervisor.process_request")

        # Clear comparison table at start of each request
        state['comparison_table'] = None

        # Step 1 & 2: Run analyzer and semantic parser in parallel to reduce latency
        analysis, state = self._run_parallel_intent_and_parsing(user_input, state)

        # Step 3: Determine execution plan
        execution_plan = self._create_execution_plan(analysis, state)

        # Step 4: Execute sub-agents
        results = self._execute_sub_agents(execution_plan, user_input, state)

        # Step 5: Handle special cases (pure general, pure interview)
        special_result = self._handle_special_cases(results, state)
        if special_result:
            return special_result

        # Step 6: Update state with sub-agent results
        state = self._update_state_from_results(results, state)

        # Step 7: Synthesize response
        synthesis = self.synthesizer.synthesize(results, analysis, state, user_input)

        # Step 8: Apply synthesis to state
        state['ai_response'] = synthesis['response']
        state['quick_replies'] = synthesis.get('quick_replies')
        state['suggested_followups'] = synthesis.get('suggested_followups', [])

        self.logger.info(f"Response generated ({len(synthesis['response'])} chars)")

        append_span(state, finish_span(request_span))
        return state

    def _run_parallel_intent_and_parsing(
        self,
        user_input: str,
        state: ProductSearchState
    ) -> Tuple[RequestAnalysis, ProductSearchState]:
        """
        Run intent analysis and semantic parsing concurrently.

        Args:
            user_input: Latest user utterance
            state: Current conversation state

        Returns:
            Tuple containing request analysis and updated state
        """
        state_for_parser = state.copy()
        parallel_span = start_span("supervisor.intent_and_parsing")

        def _wrapped_analyze() -> Tuple[RequestAnalysis, Dict[str, Any]]:
            span = start_span("intent_analysis")
            result = analyze_request(user_input, state)
            return result, finish_span(span)

        def _wrapped_parse() -> Tuple[ProductSearchState, Dict[str, Any]]:
            span = start_span("semantic_parser")
            parsed = semantic_parser_node(state_for_parser, self.progress_callback)
            return parsed, finish_span(span)

        with ThreadPoolExecutor(max_workers=2) as executor:
            analysis_future = executor.submit(_wrapped_analyze)
            parser_future = executor.submit(_wrapped_parse)

            analysis, analysis_span = analysis_future.result()
            parsed_state, parser_span = parser_future.result()

        append_span(parsed_state, analysis_span)
        append_span(parsed_state, parser_span)
        append_span(parsed_state, finish_span(parallel_span))

        parsed_state['_semantic_parsing_done'] = True
        return analysis, parsed_state

    def _create_execution_plan(
        self,
        analysis: RequestAnalysis,
        state: ProductSearchState
    ) -> Dict[AgentMode, Dict[str, Any]]:
        """
        Determine which sub-agents should run and with what parameters.

        Args:
            analysis: Request analysis with detected intents
            state: Current state

        Returns:
            Dict mapping AgentMode to execution parameters
        """
        plan = {}

        # Pure general conversation - handle immediately
        if self._is_pure_general(analysis):
            plan[AgentMode.GENERAL] = {}
            return plan

        # Interview (if needed and not yet interviewed)
        if analysis.needs_interview and not state.get('interviewed', False):
            plan[AgentMode.INTERVIEW] = {'user_input': None}  # Will be filled during execution

        # Analytical (if explicit questions asked)
        if analysis.needs_analytical and analysis.analytical_questions:
            plan[AgentMode.ANALYTICAL] = {'questions': analysis.analytical_questions}

        # Search (if needed and not delegated to interview)
        # Interview workflow handles its own search, so skip if interview is running
        if self._should_run_search(analysis, state) and AgentMode.INTERVIEW not in plan:
            plan[AgentMode.SEARCH] = {}

        return plan

    def _execute_sub_agents(
        self,
        plan: Dict[AgentMode, Dict[str, Any]],
        user_input: str,
        state: ProductSearchState
    ) -> List[SubAgentResult]:
        """
        Execute sub-agents according to plan.

        Args:
            plan: Execution plan from _create_execution_plan
            user_input: User's message
            state: Current state

        Returns:
            List of sub-agent results
        """
        results = []

        for mode, params in plan.items():
            if mode == AgentMode.ANALYTICAL:
                result = self.runner.run_analytical(params['questions'], state)
                results.append(result)

            elif mode == AgentMode.SEARCH:
                result = self.runner.run_search(state)
                results.append(result)

            elif mode == AgentMode.INTERVIEW:
                result = self.runner.run_interview(user_input, state)
                results.append(result)

            elif mode == AgentMode.GENERAL:
                result = self.runner.run_general(state)
                results.append(result)

        return results

    def _handle_special_cases(
        self,
        results: List[SubAgentResult],
        state: ProductSearchState
    ) -> Optional[ProductSearchState]:
        """
        Handle special cases that bypass normal synthesis.

        Special cases:
        - Pure general conversation (no synthesis needed)
        - Pure interview (no other modes, return interview state directly)

        Args:
            results: Sub-agent results
            state: Current state

        Returns:
            State if special case handled, None otherwise
        """
        # Pure general conversation
        if len(results) == 1 and results[0].mode == AgentMode.GENERAL:
            state_copy = state.copy()
            state_copy['ai_response'] = results[0].response
            state_copy['suggested_followups'] = results[0].suggested_followups
            return state_copy

        # Pure interview (no analytical/search)
        interview_results = [r for r in results if r.mode == AgentMode.INTERVIEW]
        other_results = [r for r in results if r.mode != AgentMode.INTERVIEW]

        if interview_results and not other_results:
            self.logger.info("Pure interview - returning interview state directly")
            return interview_results[0].updated_state

        return None

    def _update_state_from_results(
        self,
        results: List[SubAgentResult],
        state: ProductSearchState
    ) -> ProductSearchState:
        """
        Update state with data from sub-agent results.

        Args:
            results: Sub-agent results
            state: Current state

        Returns:
            Updated state
        """
        for result in results:
            # Update comparison table from analytical agent
            if result.comparison_table:
                state['comparison_table'] = result.comparison_table

            # Update products from search agent
            if result.mode == AgentMode.SEARCH and result.vehicles is not None:
                state['recommended_products'] = result.vehicles
                state['previous_filters'] = state['explicit_filters'].copy()

                if result.metadata.get('suggestion_reasoning'):
                    state['suggestion_reasoning'] = result.metadata['suggestion_reasoning']


            # Update from interview workflow
            if result.mode == AgentMode.INTERVIEW and result.updated_state:
                # Merge interview state updates (interview manages its own state completely)
                state = result.updated_state

        return state

    def _is_pure_general(self, analysis: RequestAnalysis) -> bool:
        """
        Check if request is purely general conversation.

        Args:
            analysis: Request analysis

        Returns:
            True if purely general conversation
        """
        return (
            analysis.is_general_conversation
            and not analysis.needs_search
            and not analysis.needs_analytical
            and not analysis.needs_interview
        )

    def _should_run_search(
        self,
        analysis: RequestAnalysis,
        state: ProductSearchState
    ) -> bool:
        """
        Determine if search sub-agent should run.

        Args:
            analysis: Request analysis
            state: Current state

        Returns:
            True if search should run
        """
        filters_changed = state['explicit_filters'] != state.get('previous_filters', {})
        has_products = len(state.get('recommended_products', [])) > 0

        # Should search if:
        # - User explicitly needs search OR
        # - Filters changed OR
        # - User updated filters but no products yet
        should_search = (
            analysis.needs_search
            or filters_changed
            or (analysis.has_filter_update and not has_products)
        )

        # Only actually run if filters changed or no products
        return should_search and (filters_changed or not has_products)


# Public API
def run_supervisor(
    user_input: str,
    state: ProductSearchState,
    progress_callback: Optional[Callable[[dict], None]] = None
) -> ProductSearchState:
    """
    Supervisor agent - orchestrates sub-agents to handle compound requests.

    This is the main entry point that maintains backward compatibility.
    The actual orchestration logic is handled by SupervisorOrchestrator class.

    Args:
        user_input: User's message
        state: Current conversation state
        progress_callback: Optional progress callback for streaming updates

    Returns:
        Updated state with unified response
    """
    orchestrator = SupervisorOrchestrator(progress_callback)
    return orchestrator.process_request(user_input, state)
