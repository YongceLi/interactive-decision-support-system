"""
Request analyzer - analyzes user requests to detect multiple intents and needs.

This module handles compound requests like:
- "I want a black one, what's the maintenance cost?" (filter update + analytical question)
- "Show me Honda Accords and compare top 3" (search + comparison)
- "What's the safety rating?" (pure analytical, no search)
"""
from typing import List, Dict, Any
from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from idss_agent.state.schema import VehicleSearchState
from idss_agent.utils.logger import get_logger

logger = get_logger("request_analyzer")


class RequestAnalysis(BaseModel):
    """Structured analysis of user request."""

    needs_interview: bool = Field(
        description=(
            "True if user needs interview (early in buying journey, no clear preferences yet). "
            "Only true if: user expresses buying intent AND hasn't been interviewed yet AND hasn't provided enough info."
        )
    )

    needs_search: bool = Field(
        description=(
            "True if user wants to see vehicle listings or has provided/updated filters. "
            "Examples: 'show me vehicles', 'I want a black one', 'under $30k'"
        )
    )

    needs_analytical: bool = Field(
        description=(
            "True if user asks questions requiring research/analysis. "
            "Examples: 'what's the maintenance cost?', 'compare X vs Y', 'which is safer?'"
        )
    )

    analytical_questions: List[str] = Field(
        default_factory=list,
        description=(
            "List of analytical questions extracted from the request. "
            "Examples: ['What is the maintenance cost?', 'Which has better safety?']"
        )
    )

    has_filter_update: bool = Field(
        description=(
            "True if user mentioned new vehicle criteria or change some of the existing filters (make, model, color, price, etc.)"
        )
    )

    is_general_conversation: bool = Field(
        description=(
            "True if this is just casual conversation, greeting, or meta questions. "
            "Examples: 'hello', 'how does this work?', 'thank you'"
        )
    )

    reasoning: str = Field(
        description="Brief explanation of the analysis"
    )


def analyze_request(
    user_input: str,
    state: VehicleSearchState
) -> RequestAnalysis:
    """
    Analyze user request to detect multiple intents and needs.

    Args:
        user_input: Latest user message
        state: Current conversation state

    Returns:
        RequestAnalysis with detected needs
    """

    # Get context
    interviewed = state.get('interviewed', False)
    has_filters = bool(state.get('explicit_filters', {}))
    has_preferences = bool(state.get('implicit_preferences', {}))
    has_vehicles = len(state.get('recommended_vehicles', [])) > 0

    # Build context for LLM
    context = f"""
**Conversation Context:**
- User has been interviewed: {interviewed}
- User has provided filters: {has_filters}
- User has implicit preferences: {has_preferences}
- Current vehicles shown: {len(state.get('recommended_vehicles', []))}
- Current filters: {state.get('explicit_filters', {})}
- Implicit preferences: {state.get('implicit_preferences', {})}
"""

    # Create prompt for analysis
    system_prompt = """You are a request analyzer for a vehicle search assistant.

Analyze the user's request and detect what they need:

1. **needs_interview**: User needs guided questions to understand their needs
   - Only true if: buying intent + not interviewed + insufficient info

2. **needs_search**: User wants to see vehicles or updated results
   - Examples: "show me", "I want", "under $X", "black color"

3. **needs_analytical**: User asks questions requiring research
   - Examples: "what's the...", "compare", "which is better", "tell me about"

4. **analytical_questions**: Extract specific questions
   - List each question separately

5. **has_filter_update**: User mentioned vehicle criteria
   - Make, model, color, price, features, etc.

6. **is_general_conversation**: Just chatting, not searching
   - Greetings, thank you, What can you do?, etc.

**Important**: A request can have MULTIPLE needs simultaneously!
Example: "I want a black one, what's the maintenance cost?"
- needs_search: True (wants black color)
- needs_analytical: True (asks about maintenance)
- has_filter_update: True (color = black)
- analytical_questions: ["What's the maintenance cost?"]
"""

    user_prompt = f"""{context}

**Latest User Message:**
"{user_input}"

Analyze this request and determine what the user needs."""

    # Call LLM for analysis
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    structured_llm = llm.with_structured_output(RequestAnalysis)

    try:
        result = structured_llm.invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt)
        ])

        logger.info(f"Request analysis: interview={result.needs_interview}, "
                   f"search={result.needs_search}, analytical={result.needs_analytical}, "
                   f"questions={len(result.analytical_questions)}")
        logger.info(f"  Reasoning: {result.reasoning}")

        return result

    except Exception as e:
        logger.error(f"Error analyzing request: {e}")
        # Fallback to safe defaults
        return RequestAnalysis(
            needs_interview=False,
            needs_search=False,
            needs_analytical=False,
            analytical_questions=[],
            has_filter_update=False,
            is_general_conversation=True,
            reasoning=f"Error during analysis: {str(e)}"
        )
