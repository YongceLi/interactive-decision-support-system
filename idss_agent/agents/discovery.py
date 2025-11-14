"""
Discovery agent - generates responses with listing summary and elicitation questions.
"""
import json
from typing import List, Dict, Any, Optional, Callable
from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from idss_agent.utils.config import get_config
from idss_agent.utils.prompts import render_prompt
from idss_agent.state.schema import ProductSearchState, AgentResponse


def format_products_for_llm(products: List[Dict[str, Any]], limit: int = 3, max_chars: int = 4000) -> str:
    """Return raw JSON for the top products, truncated to a safe length."""
    if not products:
        return "[]"

    limited = products[:limit]
    raw_json = json.dumps(limited, indent=2)

    if len(raw_json) > max_chars:
        raw_json = raw_json[: max_chars - 3] + "..."

    return raw_json


def discovery_agent(
    state: ProductSearchState,
    progress_callback: Optional[Callable[[dict], None]] = None
) -> ProductSearchState:
    """
    Discovery agent - generates product overview and elicitation questions.

    This agent:
    1. Acknowledges user preferences
    2. Uses bullet points to explain how the first product matches the user's preferences
    3. Asks 1-2 strategic elicitation questions

    Args:
        state: Current product search state
        progress_callback: Optional callback for progress updates

    Returns:
        Updated state with ai_response
    """

    # Emit progress: Starting response generation
    config = get_config()
    terminology = config.get_terminology_context()
    product_plural = terminology.get('product_plural', 'products')

    if progress_callback:
        progress_callback({
            "step_id": "generating_response",
            "description": f"Presenting {product_plural}",
            "status": "in_progress"
        })

    filters = state['explicit_filters']
    implicit = state['implicit_preferences']
    products = state.get('recommended_products') or state.get('recommended_vehicles', [])
    already_asked = state.get('questions_asked', [])

    model_config = config.get_model_config('discovery')
    top_limit = (
        config.limits.get('top_products_to_show')
        or config.limits.get('top_vehicles_to_show', 3)
    )
    max_summary_chars = (
        config.limits.get('max_product_summary_chars')
        or config.limits.get('max_vehicle_summary_chars', 4000)
    )

    # Format products for LLM
    products_summary = format_products_for_llm(
        products,
        limit=top_limit,
        max_chars=max_summary_chars,
    )

    # Load system prompt from template
    discovery_system_prompt = render_prompt('discovery.j2')

    # Check if filters were relaxed (fallback occurred)
    fallback_message = state.get('fallback_message')
    fallback_note = ""
    if fallback_message:
        fallback_note = f"""
**IMPORTANT - Fallback Applied:**
The original filters didn't find {product_plural}, so we relaxed some constraints.
Include this message naturally in your response: "{fallback_message}"
"""

    prompt = f"""
**User's Current Filters:**
{json.dumps(filters, indent=2)}

**User's Preferences:**
{json.dumps(implicit, indent=2)}

**Current Listings ({len(products)} {product_plural} found, showing top {top_limit} as JSON):**
{products_summary}

**Topics Already Asked About:** {already_asked}
(Avoid asking about these topics again)

{fallback_note}

Generate your response:
"""

    messages = [
        SystemMessage(content=discovery_system_prompt),
        HumanMessage(content=prompt),
    ]

    # Create LLM with config parameters
    llm = ChatOpenAI(
        model=model_config['name'],
        temperature=model_config['temperature'],
        max_tokens=model_config.get('max_tokens', 800)
    )
    structured_llm = llm.with_structured_output(AgentResponse)
    response: AgentResponse = structured_llm.invoke(messages)

    state['ai_response'] = response.ai_response

    # Apply feature flags for interactive elements
    state['quick_replies'] = response.quick_replies if config.features.get('enable_quick_replies', True) else None
    state['suggested_followups'] = []  # Discovery mode uses quick_replies only (agent asks questions, user answers)
    state['comparison_table'] = None  # Clear comparison table in discovery mode

    # Extract and track which topics were asked about
    state = extract_questions_asked(state, response.ai_response)

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


def extract_questions_asked(state: ProductSearchState, ai_response: str) -> ProductSearchState:
    """
    Use LLM to extract which topics were asked about in the response.

    This allows us to avoid repeating questions in future turns.

    Args:
        state: Current product search state
        ai_response: The assistant's response text

    Returns:
        Updated state with questions_asked list
    """

    config = get_config()
    terminology = config.get_terminology_context()
    product_name = terminology.get('product_name', 'product')

    extraction_prompt = f"""
Given this assistant response, identify which topics were asked about in the questions.

Response:
"{ai_response}"

Possible topics:
- budget (asking about price range or spending comfort)
- usage (asking how they'll use the {product_name} or what tasks it must handle)
- priorities (asking what matters most, like performance, portability, aesthetics)
- features (asking about specific specs or capabilities)
- brand (asking about preferred manufacturers)
- retailer (asking where they prefer to shop or buy)
- availability (asking about when they need the {product_name} or timeline)
- support (asking about warranty, support, or service expectations)

Return ONLY a JSON array of topics that were asked about, e.g.:
["budget", "usage", "features"]

If no questions were asked, return an empty array: []
"""

    model_config = config.get_model_config('discovery_extraction')

    llm = ChatOpenAI(
        model=model_config['name'],
        temperature=model_config['temperature'],
        max_tokens=model_config.get('max_tokens', 500)
    )
    result = llm.invoke(extraction_prompt)

    try:
        content = result.content.strip()
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()

        topics = json.loads(content)

        if isinstance(topics, list):
            current_questions = state.get('questions_asked', [])
            for topic in topics:
                if topic not in current_questions:
                    current_questions.append(topic)
            state['questions_asked'] = current_questions

    except json.JSONDecodeError as e:
        print(f"Warning: Could not parse topics from response: {e}")

    return state
