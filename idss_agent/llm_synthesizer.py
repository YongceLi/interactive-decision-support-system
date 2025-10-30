"""
LLM-based response synthesizer for multi-mode scenarios.

Used when multiple sub-agents are active to create smooth, natural responses.
Single-mode responses use direct output (no synthesis needed).
"""
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from idss_agent.logger import get_logger

logger = get_logger("llm_synthesizer")


class SynthesizedResponse(BaseModel):
    """Synthesized response with interactive elements."""
    ai_response: str = Field(
        description="The synthesized conversational response (smooth, natural)"
    )
    quick_replies: Optional[list[str]] = Field(
        default=None,
        description="Short answer options if asking a question (2-4 options, 2-5 words each)"
    )
    suggested_followups: list[str] = Field(
        description="Suggested next queries (3-5 short phrases)",
        min_length=3,
        max_length=5
    )


def llm_synthesize_multi_mode(
    sub_agent_results: Dict[str, Any],
    user_input: str,
    context: str = ""
) -> SynthesizedResponse:
    """
    Use LLM to synthesize smooth response from multiple sub-agent results.

    This handles combinations like:
    - Interview + Analytical
    - Interview + Search
    - Analytical + Search
    - All three together

    Args:
        sub_agent_results: Dict with keys 'interview', 'analytical', 'search'
        user_input: Original user input
        context: Additional context (filters, preferences)

    Returns:
        SynthesizedResponse with smooth, unified message
    """
    has_interview = 'interview' in sub_agent_results
    has_analytical = 'analytical' in sub_agent_results
    has_search = 'search' in sub_agent_results

    logger.info(f"LLM synthesizer: Combining interview={has_interview}, "
                f"analytical={has_analytical}, search={has_search}")

    # Build system prompt
    system_prompt = """You are a professional answer synthesizer in a vehicle searching agent.
You are given the results from multiple sub-agents and you need to synthesize a concise, smooth, natural response from them.

**CRITICAL CONCISENESS RULES:**
- MAXIMUM 500 characters total 
- Use SHORT sentences
- NO unnecessary words
- Use BULLET POINTS when applicable for readability

**Guidelines:**
1. If user asked a specific question, ANSWER IT FIRST
2. Then BRIEFLY recommend a listed vehicle, highlight its features.
3. Finally ask interview question (if present) - keep it short
4. Flow naturally
"""

    # Build content sections
    content_sections = []

    # 1. Analytical answer (if user asked question)
    if has_analytical:
        analytical = sub_agent_results['analytical']
        content_sections.append({
            'type': 'analytical_answer',
            'content': analytical.get('answer', ''),
            'note': 'USER ASKED THIS QUESTION - ANSWER IT FIRST'
        })

    # 2. Vehicle listings (if showing vehicles)
    if has_search:
        search = sub_agent_results['search']
        vehicles = search.get('vehicles', [])[:3]

        vehicle_list = []
        for i, vehicle in enumerate(vehicles, 1):
            v = vehicle.get('vehicle', {})
            r = vehicle.get('retailListing', {})
            vehicle_list.append(
                f"{i}. {v.get('year')} {v.get('make')} {v.get('model')} - "
                f"${r.get('price', 0):,} ({r.get('miles', 0):,} miles)"
            )

        total_count = len(sub_agent_results['search'].get('vehicles', []))
        vehicles_text = '\n'.join(vehicle_list)
        if total_count > 3:
            vehicles_text += f"\n...and {total_count - 3} more vehicles available"

        content_sections.append({
            'type': 'vehicle_listings',
            'content': vehicles_text,
            'note': 'Show these vehicles naturally'
        })

        # Add suggestion reasoning if available
        if search.get('suggestion_reasoning'):
            content_sections.append({
                'type': 'reasoning',
                'content': search['suggestion_reasoning'],
                'note': 'Explain why these vehicles match'
            })

    # 3. Interview question (if continuing interview)
    if has_interview:
        interview = sub_agent_results['interview']
        content_sections.append({
            'type': 'interview_question',
            'content': interview.get('response', ''),
            'note': 'Ask this to continue understanding their needs'
        })

    # Build user prompt
    user_prompt = f"""**User Input:**
"{user_input}"

{f"**Context:** {context}" if context else ""}

**Information to Combine:**

"""

    for section in content_sections:
        user_prompt += f"\n**{section['type'].replace('_', ' ').title()}:**\n"
        user_prompt += f"{section['content']}\n"
        user_prompt += f"*({section['note']})*\n"

    user_prompt += """
Please synthesize these into ONE smooth, conversational response that:
1. Answers any direct questions FIRST
2. Presents information naturally
3. Transitions smoothly between topics
4. Feels like a single, cohesive message from a helpful assistant
5. Ends with any interview questions (if present)
"""

    # Call LLM for synthesis
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.7)
    structured_llm = llm.with_structured_output(SynthesizedResponse)

    try:
        result = structured_llm.invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt)
        ])

        # Preserve quick replies from interview if available
        if has_interview and sub_agent_results['interview'].get('quick_replies'):
            result.quick_replies = sub_agent_results['interview']['quick_replies']

        logger.info(f"✓ Synthesized smooth multi-mode response ({len(result.ai_response)} chars)")
        return result

    except Exception as e:
        logger.error(f"LLM synthesis failed: {e}")

        # Fallback: simple concatenation
        fallback_parts = []

        if has_analytical:
            fallback_parts.append(sub_agent_results['analytical']['answer'])

        if has_search:
            fallback_parts.append(f"\nHere are some vehicles:\n\n{vehicles_text}")

        if has_interview:
            fallback_parts.append(f"\n{sub_agent_results['interview']['response']}")

        fallback_response = "\n".join(fallback_parts)

        return SynthesizedResponse(
            ai_response=fallback_response,
            quick_replies=sub_agent_results.get('interview', {}).get('quick_replies'),
            suggested_followups=[
                "Show me more options",
                "Tell me more details",
                "Compare these vehicles"
            ]
        )


def format_vehicle_summary_simple(vehicles: List[Dict[str, Any]], max_count: int = 3) -> str:
    """
    Format vehicles into simple text summary (for single-mode search).

    Args:
        vehicles: List of vehicle dicts
        max_count: Max number to show

    Returns:
        Formatted vehicle listing
    """
    if not vehicles:
        return "No vehicles found matching your criteria."

    summary_lines = []
    for i, vehicle in enumerate(vehicles[:max_count], 1):
        v = vehicle.get('vehicle', {})
        r = vehicle.get('retailListing', {})
        summary_lines.append(
            f"{i}. **{v.get('year')} {v.get('make')} {v.get('model')}** - "
            f"${r.get('price', 0):,} ({r.get('miles', 0):,} miles)"
        )

    total = len(vehicles)
    if total > max_count:
        summary_lines.append(f"\n...and {total - max_count} more vehicles available")

    return "\n".join(summary_lines)
