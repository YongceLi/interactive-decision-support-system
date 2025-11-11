"""
Analytical agent - answers specific questions about electronics products using ReAct.
"""
import os
import json
import re
from typing import Optional, Callable, Dict, List, Any
from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent
from idss_agent.utils.config import get_config
from idss_agent.utils.prompts import render_prompt
from idss_agent.state.schema import VehicleSearchState, AgentResponse, ComparisonTable
from idss_agent.tools.electronics_api import search_products, get_product_details
from idss_agent.utils.logger import get_logger

logger = get_logger("components.analytical_tool")


def parse_comparison_response(response_text: str) -> Optional[Dict[str, Any]]:
    """
    Parse comparison JSON from agent response.

    Args:
        response_text: Agent's response text

    Returns:
        Dict with 'summary' and 'comparison_table', or None if not a comparison
    """
    try:
        # Try to extract JSON from response (might be wrapped in markdown code blocks)
        json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', response_text, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
        else:
            # Try to find raw JSON
            json_match = re.search(r'\{.*"summary".*"comparison_data".*\}', response_text, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
            else:
                return None

        # Parse JSON
        data = json.loads(json_str)

        # Validate structure
        if 'summary' not in data or 'comparison_data' not in data:
            return None

        comparison_data = data['comparison_data']
        entities = (
            comparison_data.get('products')
            or comparison_data.get('items')
            or comparison_data.get('vehicles')
        )
        if not entities or 'attributes' not in comparison_data:
            return None

        # Build comparison table
        product_names = entities
        attributes = comparison_data['attributes']

        # Create headers: ["Attribute", "Product 1", "Product 2", ...]
        headers = ["Attribute"] + product_names

        # Create rows: each attribute becomes a row
        rows = []
        for attr in attributes:
            row = [attr['name']] + attr['values']
            rows.append(row)

        comparison_table = ComparisonTable(headers=headers, rows=rows)

        return {
            'summary': data['summary'],
            'comparison_table': comparison_table
        }

    except (json.JSONDecodeError, KeyError, IndexError) as e:
        logger.debug(f"Failed to parse comparison JSON: {e}")
        return None


@tool
def web_search(query: str) -> str:
    """
    Search the web for current information about electronics and consumer tech products.

    Args:
        query: Search query string

    Returns:
        Search results
    """
    try:
        from langchain_community.tools.tavily_search import TavilySearchResults

        config = get_config()
        max_results = config.limits.get('web_search_max_results', 3)
        search = TavilySearchResults(max_results=max_results)
        results = search.invoke({"query": query})

        # Format results
        if isinstance(results, list) and results:
            formatted = []
            for i, result in enumerate(results[:max_results], 1):
                content = result.get('content', '')
                url = result.get('url', '')
                formatted.append(f"[Result {i}]\n{content}\nSource: {url}\n")
            return "\n".join(formatted)
        return "No web search results found. Please try a different query."

    except ImportError:
        logger.warning("Tavily search not available, falling back to basic response")
        return f"Web search tool not configured. For query '{query}', please check online resources manually."
    except Exception as e:
        logger.error(f"Web search error: {e}")
        return f"Web search temporarily unavailable: {str(e)}"


class InteractiveElements(BaseModel):
    """Quick replies for analytical responses."""
    quick_replies: Optional[list[str]] = Field(
        default=None,
        description=(
            "Short answer options (5 words or less each) if the response asks a direct question. "
            "Provide 2-4 CONCRETE, ACTIONABLE options that directly answer the question. "
            "Leave null if no direct question asked."
        )
    )


def generate_interactive_elements(ai_response: str, user_question: str) -> InteractiveElements:
    """
    Generate quick replies for an analytical response.

    Args:
        ai_response: The analytical agent's response
        user_question: The user's original question

    Returns:
        InteractiveElements with quick_replies (suggested_followups disabled for analytical mode)
    """
    # Get configuration
    config = get_config()
    model_config = config.get_model_config('analytical_postprocess')

    llm = ChatOpenAI(
        model=model_config['name'],
        temperature=model_config['temperature'],
        max_tokens=model_config.get('max_tokens', 800)
    )
    structured_llm = llm.with_structured_output(InteractiveElements)

    # Load prompt template
    template_prompt = render_prompt('analytical.j2')

    # Build full prompt
    prompt = f"""{template_prompt}

User Question: {user_question}

AI Response: {ai_response}

Generate the interactive elements now.
"""

    result: InteractiveElements = structured_llm.invoke([HumanMessage(content=prompt)])
    return result


# System prompt for analytical agent
ANALYTICAL_SYSTEM_PROMPT = """
You are an expert electronics research analyst with deep knowledge of consumer technology (PC components, laptops, smart home gear, peripherals, etc.).

Your role is to answer specific, data-driven questions about products by leveraging the tools at your disposal.

## Available Tools

**Cached Recommendation Lookup (`cached_recommendation_lookup`)**
- Input: '#N', product ID, or partial title. Use 'list' for all cached items.
- Returns: JSON describing products already fetched in this session.
- Use when: referencing products the user already sees (e.g., '#1', '#2') or needing their cached metadata before making new API calls.

**Product Catalog Search (`search_products`)**
- Input: keyword query and optional filters.
- Returns: JSON array of products with pricing, seller, rating, and metadata.
- Use when: you need more product options, to confirm availability, or to retrieve identifiers for follow-up questions.

**Product Detail Lookup (`get_product_details`)**
- Input: product_id from the catalog search.
- Returns: Detailed specifications, pricing, description, images, and seller info.
- Use when: the user references a specific product ID or you already have an identifier from recommendations.

**Web Search (`web_search`)**
- Input: natural language query.
- Returns: Latest web snippets and URLs.
- Use when: catalog data is insufficient, you need benchmarks/reviews, or you want up-to-date pricing news.

## Guidelines

**Data accuracy**
1. Cite concrete specs (core counts, clock speeds, RAM type, display size, power draw, etc.) pulled from tools.
2. Verify currency and seller before quoting price data.
3. If sources disagree, note the discrepancy and favor the most recent or authoritative information.
4. Summarize findings in clear, user-friendly language—avoid copying marketing fluff verbatim.

**Query best practices**
1. Check cached recommendations first via `cached_recommendation_lookup` when the user references products you already showed them (like '#1', '#2', or named items). Only call external APIs if necessary data is missing.
2. Narrow catalog searches with model numbers, capacity, or feature keywords when possible.
3. Use product detail lookup immediately after obtaining a product_id to enrich your answer.
4. When comparing products, gather the same set of attributes (price, cores/threads, boost clocks, TDP, bundled cooler, socket compatibility, etc.) for each item.

**Product references**
- When the user references "#1", "#2", etc., map those to the recommended products list provided in the context.
- Use `product_id`, `title`, and `brand` for clarity. Prefer product IDs when calling detail lookups.
- If an identifier is missing, fall back to title + brand in searches or ask the user for clarification.

**Comparison queries (SPECIAL FORMAT)**
When the user asks to compare 2-4 products (e.g., "compare Ryzen 7 7800X3D vs i7-14700K" or "compare top 3"):
1. Identify which products to compare (from context or via catalog search).
2. Gather matching specs/prices for each product using the available tools.
3. Output your response in this EXACT JSON format:
```json
{
  "summary": "2-3 sentence summary highlighting key differences",
  "comparison_data": {
    "products": ["AMD Ryzen 7 7800X3D", "Intel Core i7-14700K"],
    "attributes": [
      {"name": "Price", "values": ["$399 (Walmart)", "$409 (Best Buy)"]},
      {"name": "Cores / Threads", "values": ["8C / 16T", "8P+12E / 28T"]},
      {"name": "Base / Boost Clock", "values": ["4.2 / 5.0 GHz", "3.4 / 5.6 GHz"]},
      {"name": "TDP", "values": ["120W", "125W"]}
    ]
  }
}
```
4. **CRITICAL**: For ALL comparison requests, output ONLY the JSON above—no additional prose.
5. Include the attributes that matter most to the user (performance, thermals, compatibility, bundled accessories, etc.).

**Error handling and fallbacks**
1. If a tool call fails, retry with a simplified query or fewer filters.
2. If data remains unavailable, explain what you attempted and suggest where the user can verify the information.
3. Encourage the user to clarify model numbers or desired specs when ambiguity remains.

Think step-by-step:
1. Understand the user's question and confirm the product scope.
2. Decide which tools to call and in what order.
3. Collect evidence (catalog data, detail lookup, web snippets).
4. Synthesize the answer in 3-4 concise sentences unless returning comparison JSON.
5. Offer to help with follow-up questions or deeper analysis.
"""


def analytical_agent(
    state: VehicleSearchState,
    progress_callback: Optional[Callable[[dict], None]] = None
) -> VehicleSearchState:
    """
    Agent that answers specific questions about electronics products using available data sources.

    This creates a ReAct agent with access to:
    - RapidAPI product catalog search
    - RapidAPI product detail lookup
    - Web search for up-to-date reviews and benchmarks

    Uses system + user message format for optimal prompt caching:
    - System message: Role, tools, guidelines (cached)
    - User message: Product context + question (dynamic)

    Args:
        state: Current state with product context and user question
        progress_callback: Optional callback for progress updates

    Returns:
        Updated state with ai_response
    """
    # Get configuration
    config = get_config()
    model_config = config.get_model_config('analytical')
    max_history = config.limits.get('max_conversation_history', 10)

    # Get conversation history for analytical context
    conversation_history = state.get("conversation_history", [])
    recent_history = conversation_history[-max_history:] if len(conversation_history) > max_history else conversation_history

    if not recent_history:
        logger.warning("Analytical agent: No conversation history found")
        state["ai_response"] = "I didn't receive a question. How can I help you with product information?"
        return state

    # Get latest user message
    user_input = recent_history[-1].content if recent_history else ""
    logger.info(f"Analytical query: {user_input[:100]}... (with {len(recent_history)} messages of context)")

    # Create LLM with config parameters
    llm = ChatOpenAI(
        model=model_config['name'],
        temperature=model_config['temperature'],
        max_tokens=model_config.get('max_tokens', 4000)
    )

    # Get available tools
    cached_products = state.get("recommended_products") or state.get("recommended_vehicles", [])

    @tool("cached_recommendation_lookup")
    def cached_recommendation_lookup(selector: str) -> str:
        """
        Retrieve data from the current cached recommendations without calling external APIs.

        Args:
            selector: Use '#N' for the Nth product, a product ID, or part of the product title.
                      Use 'list' to retrieve all cached products.

        Returns:
            JSON string containing matching products with metadata.
        """
        if not cached_products:
            return json.dumps({"error": "No cached recommendations available."})

        selector_normalized = selector.strip().lower()

        def serialize_product(product: Dict[str, Any], idx: int) -> Dict[str, Any]:
            product_info = product.get("product") or {}
            offer = product.get("offer") or {}
            return {
                "index": idx + 1,
                "id": product.get("id"),
                "product_identifier": product_info.get("identifier") or product_info.get("id"),
                "title": product.get("title") or product_info.get("title"),
                "brand": product.get("brand") or product_info.get("brand"),
                "price_text": product.get("price_text") or offer.get("price"),
                "price_value": product.get("price_value"),
                "currency": product.get("price_currency") or offer.get("currency"),
                "rating": product.get("rating"),
                "rating_count": product.get("rating_count") or product.get("reviewCount"),
                "attributes": product_info.get("attributes"),
                "source": product.get("source") or offer.get("seller"),
                "link": product.get("link") or offer.get("url"),
                "raw": product,
            }

        results: List[Dict[str, Any]] = []

        if selector_normalized in ("", "list", "all", "*"):
            results = [serialize_product(prod, idx) for idx, prod in enumerate(cached_products)]
        else:
            # Match by index (#1), identifier, or fuzzy title match
            index_match = re.match(r"#?(\d+)", selector_normalized)
            if index_match:
                idx = int(index_match.group(1)) - 1
                if 0 <= idx < len(cached_products):
                    results.append(serialize_product(cached_products[idx], idx))

            if not results:
                for idx, product in enumerate(cached_products):
                    product_info = product.get("product") or {}
                    identifiers = {
                        str(product.get("id") or "").lower(),
                        str(product_info.get("identifier") or "").lower(),
                        str(product_info.get("id") or "").lower(),
                    }
                    title = (product.get("title") or product_info.get("title") or "").lower()
                    if selector_normalized in identifiers or selector_normalized in title:
                        results.append(serialize_product(product, idx))

            if not results:
                # Try substring match on title
                for idx, product in enumerate(cached_products):
                    product_info = product.get("product") or {}
                    title = (product.get("title") or product_info.get("title") or "").lower()
                    if selector_normalized and selector_normalized in title:
                        results.append(serialize_product(product, idx))

        if not results:
            available = [
                {
                    "index": idx + 1,
                    "title": product.get("title") or (product.get("product") or {}).get("title"),
                }
                for idx, product in enumerate(cached_products[:10])
            ]
            return json.dumps({
                "error": f"No cached product matched selector '{selector}'.",
                "available_examples": available,
            })

        return json.dumps({"results": results})

    tools = [
        cached_recommendation_lookup,
        search_products,
        get_product_details,
        web_search,
    ]

    # Build product context from state
    products = state.get("recommended_products") or state.get("recommended_vehicles", [])
    filters = state.get("explicit_filters", {})
    preferences = state.get("implicit_preferences", {})

    # Create product reference map (for "#1", "#2" references)
    product_context_parts: List[str] = []

    if products:
        product_context_parts.append("## Available Products (for reference)\n")
        for index, product in enumerate(products[:10], 1):
            product_info = product.get("product", {}) or {}
            display_title = (
                product.get("title")
                or product_info.get("title")
                or product_info.get("name")
                or product.get("model")
                or "Unnamed product"
            )
            brand = product.get("brand") or product_info.get("brand")
            if brand and brand.lower() not in display_title.lower():
                display_name = f"{brand} {display_title}"
            else:
                display_name = display_title

            price_text = product.get("price_text")
            price_value = product.get("price_value")
            currency = product.get("price_currency") or product.get("offer", {}).get("currency")
            if price_text:
                price_display = price_text
            elif isinstance(price_value, (int, float)):
                if currency and currency.upper() == "USD":
                    price_display = f"${price_value:,.2f}"
                elif currency:
                    price_display = f"{currency} {price_value:,.2f}"
                else:
                    price_display = f"${price_value:,.2f}"
            else:
                price_display = "N/A"

            source = product.get("source") or product.get("offer", {}).get("seller")
            rating = product.get("rating")
            rating_display = f"{rating:.1f}/5" if isinstance(rating, (int, float)) else "N/A"
            rating_count = (
                product.get("rating_count")
                or product.get("reviewCount")
                or product.get("reviews")
            )
            if rating_count:
                rating_display = f"{rating_display} ({rating_count} reviews)"

            product_id = (
                product_info.get("identifier")
                or product_info.get("id")
                or product.get("id")
            )
            product_context_parts.append(
                f"#{index}: {display_name} | Price: {price_display} | Seller: {source or 'Unknown'} | Rating: {rating_display} | Product ID: {product_id or 'N/A'}"
            )

    # Add search context if available
    if filters:
        active_filters = {k: v for k, v in filters.items() if v}
        if active_filters:
            product_context_parts.append("\n## Current Search Filters")
            for key, value in active_filters.items():
                product_context_parts.append(f"- {key}: {value}")

    if preferences:
        active_prefs = {k: v for k, v in preferences.items() if v}
        if active_prefs:
            product_context_parts.append("\n## User Preferences")
            for key, value in active_prefs.items():
                product_context_parts.append(f"- {key}: {value}")

    # Build messages for agent
    messages = [SystemMessage(content=ANALYTICAL_SYSTEM_PROMPT)]

    # Add product context if available (before conversation history)
    if product_context_parts:
        product_context = "\n".join(product_context_parts)
        messages.append(HumanMessage(content=f"Context:\n{product_context}"))

    # Add recent conversation history (includes current question)
    messages.extend(recent_history)

    # Create analytical agent
    agent = create_react_agent(llm, tools)

    # Emit progress: Starting analysis
    if progress_callback:
        progress_callback({
            "step_id": "executing_tools",
            "description": "Analyzing data",
            "status": "in_progress"
        })

    try:
        # Invoke with system message (cached) + context + history
        result = agent.invoke({"messages": messages})
        evidence_summary = _collect_evidence(result.get("messages", []))

        # Emit progress: Synthesizing answer
        if progress_callback:
            progress_callback({
                "step_id": "generating_response",
                "description": "Synthesizing answer",
                "status": "in_progress"
            })

        # Extract final response
        messages = result.get("messages", [])
        if not messages:
            logger.warning("Analytical agent: No messages returned from ReAct agent")
            state["ai_response"] = "I couldn't generate a response. Please try rephrasing your question."
            return state

        # Get the last AI message
        final_message = messages[-1]
        response_content = final_message.content

        # Validate response
        if not response_content or len(response_content.strip()) == 0:
            logger.warning("Analytical agent: Empty response from agent")
            state["ai_response"] = "I couldn't find enough information to answer that question. Could you provide more details?"
            state["quick_replies"] = None
            state["suggested_followups"] = []
            state["comparison_table"] = None
        else:
            logger.info(f"Analytical agent: Response generated ({len(response_content)} chars)")

            # Check if this is a comparison response (contains JSON)
            comparison_result = parse_comparison_response(response_content)

            if comparison_result:
                # It's a comparison - use summary as response, store table separately
                state["ai_response"] = comparison_result['summary']
                state["comparison_table"] = comparison_result['comparison_table'].model_dump()
                logger.info(f"Comparison detected: {len(comparison_result['comparison_table'].headers)} products compared")

                # Generate interactive elements from summary
                try:
                    interactive = generate_interactive_elements(comparison_result['summary'], user_input)
                    # Apply feature flags
                    state["quick_replies"] = interactive.quick_replies if config.features.get('enable_quick_replies', True) else None
                    state["suggested_followups"] = []  # Analytical mode uses quick_replies only (agent asks questions, user answers)
                except Exception as e:
                    logger.warning(f"Failed to generate interactive elements: {e}")
                    # Apply feature flags for fallback values
                    state["quick_replies"] = None
                    state["suggested_followups"] = []  # Analytical mode uses quick_replies only
            else:
                # Normal response - no comparison
                state["ai_response"] = response_content
                state["comparison_table"] = None

                # Generate interactive elements (quick replies only)
                try:
                    interactive = generate_interactive_elements(response_content, user_input)
                    # Apply feature flags
                    state["quick_replies"] = interactive.quick_replies if config.features.get('enable_quick_replies', True) else None
                    state["suggested_followups"] = []  # Analytical mode uses quick_replies only (agent asks questions, user answers)
                except Exception as e:
                    logger.warning(f"Failed to generate interactive elements: {e}")
                    state["quick_replies"] = None
                    state["suggested_followups"] = []  # Analytical mode uses quick_replies only

            _apply_verification(state, response_content, evidence_summary, config, user_input)

        # Emit progress: Answer ready
        if progress_callback:
            progress_callback({
                "step_id": "generating_response",
                "description": "Answer ready",
                "status": "completed"
            })

        # Mark as complete
        if progress_callback:
            progress_callback({
                "step_id": "complete",
                "description": "Complete",
                "status": "completed"
            })

    except Exception as e:
        logger.error(f"Analytical agent error: {e}", exc_info=True)

        # Provide helpful error message based on error type
        error_msg = str(e).lower()
        if "rate limit" in error_msg or "quota" in error_msg:
            state["ai_response"] = "I'm currently experiencing high demand. Please try again in a moment."
        elif "timeout" in error_msg:
            state["ai_response"] = "The query took too long to process. Please try a simpler question."
        elif "invalid" in error_msg and ("product" in error_msg or "id" in error_msg):
            state["ai_response"] = "I couldn't find that product. Please double-check the product ID or name and try again."
        else:
            state["ai_response"] = "I encountered an error while researching your question. Please try rephrasing it or ask something else."

        # Set empty interactive elements on error
        state["quick_replies"] = None
        state["suggested_followups"] = []

    return state


def _collect_evidence(messages: List[Any]) -> str:
    """
    Collect tool outputs and intermediate evidence from ReAct execution.
    """
    if not messages:
        return ""

    evidence_lines: List[str] = []
    for message in messages:
        if isinstance(message, ToolMessage):
            snippet = message.content if isinstance(message.content, str) else json.dumps(message.content, ensure_ascii=False)
            evidence_lines.append(snippet.strip())
    return "\n".join(evidence_lines[-5:])


def _apply_verification(
    state: VehicleSearchState,
    ai_response: str,
    evidence_summary: str,
    config,
    user_question: str
) -> None:
    """
    Run a lightweight verifier pass to assess factual confidence.
    """
    diagnostics = state.setdefault("diagnostics", {})
    diagnostics.setdefault("analytical", {})
    diagnostics["analytical"]["evidence"] = evidence_summary

    if not ai_response:
        return

    try:
        model_config = config.get_model_config('analytical_postprocess')
        verifier = ChatOpenAI(
            model=model_config['name'],
            temperature=0,
            max_tokens=model_config.get('max_tokens', 300)
        )
    except Exception as e:
        logger.warning(f"Verifier model unavailable: {e}")
        return

    prompt = f"""
You are a fact-checking assistant. Evaluate if the assistant response is supported by the evidence.

User question: {user_question}

Assistant answer:
{ai_response}

Evidence collected:
{evidence_summary or "No evidence"}

Respond with a JSON object containing:
  "confident": boolean,
  "issues": optional string describing factual gaps (empty if none).
"""

    try:
        verification = verifier.invoke(prompt)
        payload = verification.content if hasattr(verification, "content") else verification
        if isinstance(payload, str):
            payload = payload.strip()
            if payload.startswith("```"):
                payload = payload.strip("`")
            verdict = json.loads(payload)
        elif isinstance(payload, dict):
            verdict = payload
        else:
            verdict = {}

        diagnostics["analytical"]["verification"] = verdict

        if not verdict.get("confident", True):
            issues = verdict.get("issues")
            if issues:
                state["ai_response"] = f"{state['ai_response']}\n\n_I want to double-check: {issues}_"
    except Exception as e:
        logger.warning(f"Verification step failed: {e}")
