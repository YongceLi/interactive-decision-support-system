"""
Analytical agent - answers specific questions about electronics products using ReAct.
"""
import json
import re
from collections import OrderedDict
from typing import Optional, Callable, Dict, List, Any
from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent
from idss_agent.utils.config import get_config
from idss_agent.utils.prompts import render_prompt
from idss_agent.state.schema import ProductSearchState, AgentResponse, ComparisonTable
from idss_agent.tools.electronics_api import search_products, get_product_details
from idss_agent.utils.logger import get_logger
from idss_agent.processing.compatibility import (
    CompatibilityHandler,
    check_compatibility_binary,
    find_compatible_parts_recommendations,
    format_compatibility_recommendations_table
)
from idss_agent.tools.kg_compatibility import get_compatibility_tool, is_pc_part

logger = get_logger("components.analytical_tool")

MIN_COMPARISON_ATTRIBUTES = 6
MAX_COMPARISON_ATTRIBUTES = 12
ATTRIBUTE_PRIORITY = [
    "Price",
    "Seller",
    "Store",
    "Rating",
    "Review Count",
    "Capacity",
    "Speed",
    "Frequency",
    "Cores / Threads",
    "Base Clock",
    "Boost Clock",
    "Clock Speed",
    "CAS Latency",
    "Latency",
    "Voltage",
    "Form Factor",
    "Module Count",
    "Type",
    "Interface",
    "Compatibility",
    "Warranty",
    "RGB Lighting",
    "Cooling",
    "Power Consumption",
]

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
You are an expert electronics research analyst with deep knowledge of PC components, peripherals, and consumer hardware.

Your role is to answer specific, data-driven questions about products by leveraging the tools at your disposal.

**CRITICAL RULE: For compatibility queries, you MUST use the compatibility tools. Do NOT answer compatibility questions from general knowledge or training data.**

## Available Tools

**Cached Recommendation Lookup (`cached_recommendation_lookup`)**
- Input: '#N', product ID, or partial title. Use 'list' for all cached items.
- Returns: JSON describing products already fetched in this session.
- Use when: the user references products already shown (e.g., '#1', 'top 3') or when you need cached attributes before new API calls.

**Product Catalog Search (`search_products`)**
- Input: keyword query and optional filters.
- Returns: JSON array of products with pricing, seller, rating, and metadata.
- Use when: you need more options, to confirm availability, or to retrieve identifiers for follow-up questions.

**Product Detail Lookup (`get_product_details`)**
- Input: product_id from cached results or catalog search.
- Returns: Detailed specifications, descriptions, seller info, photos (RapidAPI `/products/{id}` endpoint).
- Use when: you need rich specs (clock speeds, memory timings, ports, warranty, etc.) for recommendations or comparisons.

**Compatibility Check (`check_parts_compatibility`)**
- Input: Two product slugs or names to check compatibility.
- Returns: Compatibility result with explanation.
- Use when: user asks "Is X compatible with Y?" for PC parts (CPU, GPU, motherboard, PSU, RAM, storage, case, cooler).
- IMPORTANT: Only use for PC parts. For other electronics, inform user that compatibility checking is only available for PC components.

**Find Compatible Parts (`find_compatible_parts`)**
- Input: Source product slug/name and target part type (e.g., "gpu", "cpu", "ram").
- Returns: List of compatible products.
- Use when: user asks "What [part type] is compatible with [product]?" for PC parts.
- IMPORTANT: Only use for PC parts. For other electronics, inform user that compatibility checking is only available for PC components.

**Web Search (`web_search`)**
- Input: natural language query.
- Returns: Latest web snippets and URLs.
- Use when: catalog/detail data is insufficient, you need external benchmarks/reviews, or up-to-date pricing news.

## Guidelines

**Data accuracy**
1. Pull concrete specs (cores/threads, memory type, clock speeds, latency, wattage, IO, etc.) from tools.
2. Confirm currency and seller before quoting price data.
3. If sources disagree, note the discrepancy and prefer the most recent or authoritative information.
4. Summarize findings clearly—avoid marketing fluff.

**Query best practices**
1. Check cached recommendations first via `cached_recommendation_lookup` whenever the user references existing products. Only call new APIs if cached data is incomplete.
2. Narrow catalog searches with model numbers, capacities, or feature keywords when possible.
3. After obtaining a product_id, call `get_product_details` to enrich the answer with full specifications.
4. When comparing products, gather the same set of attributes (price, seller, rating, specs, compatibility, thermals, accessories, etc.) for each item.

**Product references**
- Map "#1", "#2", etc. to cached recommendations by index.
- Prefer product IDs alongside titles/brands when invoking tools.
- Ask for clarification if identifiers are ambiguous.

**Compatibility queries (SPECIAL HANDLING - MANDATORY TOOL USE)**
When the user asks about compatibility for PC parts, you MUST use the compatibility tools. Do NOT answer compatibility questions from general knowledge.

1. **Binary compatibility check** ("Is X compatible with Y?"):
   - ALWAYS use `check_parts_compatibility` tool with both product slugs/names.
   - Return a clear yes/no answer with explanation from the tool.
   - Suggest follow-ups like "Show me compatible [part type]".

2. **Compatibility recommendations** ("What GPUs are compatible with my PSU?", "what gpus are compatible with name: [product]"):
   - ALWAYS use `find_compatible_parts` tool with source product name/slug and target part type.
   - Extract the product name from the query (e.g., "MSI 850W Homebrew PC Power Supply Unit MAG A850GL PCIe5")
   - Extract the target part type (e.g., "gpu", "cpu", "ram", "psu", "motherboard")
   - Format top 3 results as comparison table (see format below).
   - Include key compatibility attributes (socket, PCIe version, wattage, etc.).
   - NEVER generate compatibility recommendations without calling the tool first.
   
   **Example:**
   - User: "what gpus are compatible with name: Msi 850w Homebrew Pc Power Supply Unit Mag A850gl Pcie5 (PSU)"
   - You MUST call: `find_compatible_parts(source_product_name="Msi 850w Homebrew Pc Power Supply Unit Mag A850gl Pcie5", target_part_type="gpu")`
   - Then format the results from the tool response, do NOT make up GPU names.

3. **Non-PC parts**: If user asks about compatibility for non-PC electronics, inform them: "I'm not sure about compatibility for [product type]. The compatibility checking feature is currently only available for PC components like CPUs, GPUs, motherboards, power supplies, RAM, storage drives, cases, and CPU coolers."

4. **Unsupported compatibility relationships**: Some parts don't have direct compatibility (e.g., GPU and CPU). In these cases:
   - Explain that compatibility works through intermediate components (e.g., motherboard)
   - Suggest checking compatibility through the intermediate component instead
   - NEVER include raw error messages or debug information in your response
   - Provide helpful, user-friendly explanations instead of technical error messages

**IMPORTANT: Response Quality**
- NEVER include error messages, debug logs, or technical error details in your responses
- If a tool returns an error, provide a helpful, natural explanation to the user
- Convert technical errors into user-friendly guidance
- Example: Instead of "No compatible parts found", say "I couldn't find direct compatibility data for these parts. They may be compatible through a motherboard - would you like me to check motherboard compatibility instead?"

**Comparison queries (SPECIAL FORMAT)**
When the user asks to compare 2-4 products (e.g., "compare Ryzen 7 7800X3D vs i7-14700K", "compare top 3"):
1. Identify the specific products (from cached recommendations or by searching).
2. Use cached data plus `get_product_details` to collect rich specs for each product.
3. Output ONLY this exact JSON format—no additional prose:
```json
{
  "summary": "2-3 sentence summary highlighting key differences",
  "comparison_data": {
    "products": ["Corsair Vengeance RGB Pro 16GB", "G.SKILL TridentZ RGB 32GB"],
    "attributes": [
      {"name": "Price", "values": ["$81.99 (Amazon)", "$149.99 (Micro Center)"]},
      {"name": "Capacity", "values": ["16 GB (2 x 8 GB)", "32 GB (2 x 16 GB)"]},
      {"name": "Speed", "values": ["3600 MT/s", "6000 MT/s"]},
      {"name": "CAS Latency", "values": ["CL18", "CL36"]},
      {"name": "Voltage", "values": ["1.35 V", "1.40 V"]},
      {"name": "RGB Lighting", "values": ["Yes", "Yes"]}
    ]
  }
}
```
4. Include AT LEAST six attributes when possible (price, seller, rating, reviews, capacity, speed, latency, voltage, form factor, warranty, included accessories, etc.). Add more if data is available.
5. Ensure attribute names are concise and values are comparable across products.

**Error handling and fallbacks**
1. If a tool call fails, retry with simplified parameters or note what went wrong.
2. If data remains unavailable, explain what you attempted and suggest trusted sources for verification.
3. Invite the user to clarify models or desired specs when ambiguity remains.

Think step-by-step:
1. Understand the question and confirm product scope.
2. Decide which tools to call and in what order.
3. Collect evidence (cached data, catalog search, detail lookup, web search).
4. Synthesize the answer in 3-4 concise sentences unless returning comparison JSON.
5. Offer to help with follow-up questions or deeper analysis.
"""


def analytical_agent(
    state: ProductSearchState,
    progress_callback: Optional[Callable[[dict], None]] = None
) -> ProductSearchState:
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
    cached_products = state.get("recommended_products", [])

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

    @tool("check_parts_compatibility")
    def check_parts_compatibility(part1_name: str, part2_name: str) -> str:
        """
        Check if two PC parts are compatible.

        Args:
            part1_name: Name or slug of first product
            part2_name: Name or slug of second product

        Returns:
            JSON string with compatibility result
        """
        kg_tool = get_compatibility_tool()
        if not kg_tool.is_available():
            return json.dumps({
                "error": "Compatibility checking unavailable",
                "message": "The compatibility checking system is temporarily unavailable."
            })

        # Try to find products in KG
        product1 = kg_tool.find_product_by_name(part1_name)
        product2 = kg_tool.find_product_by_name(part2_name)

        if not product1:
            return json.dumps({
                "error": "Product not found",
                "message": f"Could not find '{part1_name}' in the compatibility database. Please provide the exact model name."
            })

        if not product2:
            return json.dumps({
                "error": "Product not found",
                "message": f"Could not find '{part2_name}' in the compatibility database. Please provide the exact model name."
            })

        # Check if both are PC parts
        if not is_pc_part(product1.get("product_type", "")) or not is_pc_part(product2.get("product_type", "")):
            return json.dumps({
                "error": "Not PC parts",
                "message": "Compatibility checking is only available for PC components (CPU, GPU, motherboard, PSU, RAM, storage, case, cooler)."
            })

        # Check compatibility
        result = kg_tool.check_compatibility(
            product1.get("slug"),
            product2.get("slug")
        )

        return json.dumps({
            "compatible": result.get("compatible", False),
            "explanation": result.get("explanation", "Compatibility check completed"),
            "part1_name": result.get("part1_name", product1.get("name")),
            "part2_name": result.get("part2_name", product2.get("name")),
            "compatibility_types": result.get("compatibility_types", [])
        })

    @tool("find_compatible_parts")
    def find_compatible_parts(source_product_name: str, target_part_type: str) -> str:
        """
        Find compatible parts for a given product.

        Args:
            source_product_name: Name or slug of source product
            target_part_type: Type of part to find (e.g., "gpu", "cpu", "ram", "psu", "motherboard", "case", "cooler")

        Returns:
            JSON string with list of compatible products
        """
        kg_tool = get_compatibility_tool()
        if not kg_tool.is_available():
            return json.dumps({
                "error": "Compatibility checking unavailable",
                "message": "The compatibility checking system is temporarily unavailable."
            })

        # Normalize target part type
        target_part_type = target_part_type.lower().strip()
        if target_part_type not in ["cpu", "gpu", "ram", "psu", "motherboard", "case", "cooler", "storage"]:
            return json.dumps({
                "error": "Invalid part type",
                "message": f"Invalid part type '{target_part_type}'. Supported types: cpu, gpu, ram, psu, motherboard, case, cooler, storage"
            })

        # Find source product
        source_product = kg_tool.find_product_by_name(source_product_name, product_type=None)
        if not source_product:
            return json.dumps({
                "error": "Product not found",
                "message": f"Could not find '{source_product_name}' in the compatibility database. Please provide the exact model name."
            })

        # Check if source is PC part
        if not is_pc_part(source_product.get("product_type", "")):
            return json.dumps({
                "error": "Not a PC part",
                "message": "Compatibility checking is only available for PC components (CPU, GPU, motherboard, PSU, RAM, storage, case, cooler)."
            })

        # Check if this compatibility relationship is supported
        source_type = source_product.get("product_type", "").lower()
        target_type_normalized = target_part_type.lower()
        
        # Check if compatibility relationship exists
        from idss_agent.tools.kg_compatibility import PART_COMPATIBILITY_MAP
        key1 = (source_type, target_type_normalized)
        key2 = (target_type_normalized, source_type)
        
        if key1 not in PART_COMPATIBILITY_MAP and key2 not in PART_COMPATIBILITY_MAP:
            # No direct compatibility relationship - provide helpful explanation
            if source_type == "gpu" and target_type_normalized == "cpu":
                return json.dumps({
                    "error": "Unsupported compatibility type",
                    "message": "GPUs and CPUs don't have direct compatibility relationships. They're compatible through the motherboard. To find compatible CPUs, you would need to check motherboard compatibility first. Would you like to find compatible motherboards for this GPU instead?"
                })
            elif source_type == "cpu" and target_type_normalized == "gpu":
                return json.dumps({
                    "error": "Unsupported compatibility type",
                    "message": "CPUs and GPUs don't have direct compatibility relationships. They're compatible through the motherboard. To find compatible GPUs, you would need to check motherboard compatibility first. Would you like to find compatible motherboards for this CPU instead?"
                })
            else:
                return json.dumps({
                    "error": "Unsupported compatibility type",
                    "message": f"Direct compatibility checking between {source_type} and {target_part_type} is not supported. Compatible parts are determined through intermediate components (e.g., motherboard)."
                })
        
        # Find compatible parts
        compatible_parts = find_compatible_parts_recommendations(
            source_product.get("slug"),
            target_part_type,
            limit=3
        )

        if not compatible_parts:
            return json.dumps({
                "error": "No compatible parts found",
                "message": f"No compatible {target_part_type} found in the database for {source_product.get('name')}. The product may not have compatibility data yet, or you may need to check compatibility through intermediate components."
            })

        # Format results
        results = []
        for part in compatible_parts:
            results.append({
                "name": part.get("name"),
                "slug": part.get("slug"),
                "brand": part.get("brand"),
                "price_avg": part.get("price_avg"),
                "price_min": part.get("price_min"),
                "price_max": part.get("price_max"),
                "product_type": part.get("product_type"),
                # Include relevant attributes
                "socket": part.get("socket"),
                "pcie_version": part.get("pcie_version"),
                "ram_standard": part.get("ram_standard"),
                "wattage": part.get("wattage"),
                "form_factor": part.get("form_factor"),
            })

        return json.dumps({
            "source_product": source_product.get("name"),
            "target_type": target_part_type,
            "compatible_parts": results
        })

    tools = [
        cached_recommendation_lookup,
        search_products,
        get_product_details,
        check_parts_compatibility,
        find_compatible_parts,
        web_search,
    ]

    # Build product context from state
    products = state.get("recommended_products", [])
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

        # Check for compatibility tool results
        compatibility_result = None
        tool_calls_found = []
        for message in messages:
            if isinstance(message, ToolMessage):
                # Try to identify tool name from message attributes or content
                tool_name = None
                if hasattr(message, 'name'):
                    tool_name = message.name
                elif hasattr(message, 'tool_call_id'):
                    # Try to match tool_call_id to tool name (if available in context)
                    tool_name = "unknown"
                
                # Detect compatibility tool by content structure
                try:
                    tool_result = json.loads(message.content) if isinstance(message.content, str) else message.content
                    if isinstance(tool_result, dict):
                        # Detect compatibility tool by result structure
                        if "compatible" in tool_result or "compatible_parts" in tool_result:
                            tool_name = tool_name or "compatibility_tool"
                        elif "error" in tool_result and "compatibility" in str(tool_result.get("message", "")).lower():
                            tool_name = tool_name or "compatibility_tool"
                    
                    if tool_name:
                        tool_calls_found.append(tool_name)
                    
                    # Check if this is a compatibility check result
                    if isinstance(tool_result, dict):
                        # Check for error responses first
                        if "error" in tool_result and "message" in tool_result:
                            # Compatibility tool returned an error
                            compatibility_result = {
                                "compatible": False,
                                "explanation": tool_result.get("message", "Compatibility checking unavailable"),
                                "error": tool_result.get("message", "Compatibility checking unavailable")
                            }
                        elif "compatible" in tool_result and "explanation" in tool_result:
                            # Binary compatibility check result
                            compatibility_result = {
                                "compatible": tool_result.get("compatible", False),
                                "explanation": tool_result.get("explanation", ""),
                                "part1_name": tool_result.get("part1_name"),
                                "part2_name": tool_result.get("part2_name"),
                                "compatibility_types": tool_result.get("compatibility_types", [])
                            }
                            if tool_result.get("error"):
                                compatibility_result["error"] = tool_result["error"]
                        elif "compatible_parts" in tool_result and "source_product" in tool_result:
                            # Compatibility recommendations - format as comparison table
                            compatible_parts = tool_result.get("compatible_parts", [])
                            source_product_name = tool_result.get("source_product", "Source Product")
                            target_type = tool_result.get("target_type", "parts")
                            
                            if compatible_parts:
                                # Format as comparison table
                                table = format_compatibility_recommendations_table(
                                    compatible_parts,
                                    source_product_name
                                )
                                state["comparison_table"] = table.model_dump()
                                
                                # Also set compatibility_result to indicate compatibility data was used
                                compatibility_result = {
                                    "compatible": True,
                                    "explanation": f"Found {len(compatible_parts)} compatible {target_type} for {source_product_name}",
                                    "source_product": source_product_name,
                                    "target_type": target_type,
                                    "compatible_parts_count": len(compatible_parts)
                                }
                            else:
                                # No compatible parts found - set error result
                                compatibility_result = {
                                    "compatible": False,
                                    "explanation": f"No compatible {target_type} found for {source_product_name}",
                                    "error": f"No compatible {target_type} found",
                                    "source_product": source_product_name,
                                    "target_type": target_type
                                }
                except (json.JSONDecodeError, KeyError, AttributeError) as e:
                    logger.debug(f"Could not parse compatibility result: {e}")
                    continue
        
        # Log tool calls for debugging
        if tool_calls_found:
            logger.info(f"[Analytical Agent] Tool calls made: {', '.join(tool_calls_found)}")
            if 'find_compatible_parts' in tool_calls_found or 'check_parts_compatibility' in tool_calls_found:
                logger.info(f"[Analytical Agent] Compatibility tool was called, compatibility_result set: {compatibility_result is not None}")

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

                # Set compatibility result if found (even with comparison)
                if compatibility_result:
                    state["compatibility_result"] = compatibility_result
                else:
                    state["compatibility_result"] = None

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
            fallback_comparison = None

            if comparison_result:
                table_model = comparison_result['comparison_table']
                headers = table_model.headers[1:]
                if len(table_model.rows) < MIN_COMPARISON_ATTRIBUTES:
                    fallback_comparison = _build_comparison_from_cached_products(
                        user_input,
                        products,
                        filters,
                        comparison_product_names=headers,
                    )
                if fallback_comparison:
                    comparison_data = fallback_comparison["table"]
                    state["ai_response"] = fallback_comparison["summary"]
                    state["comparison_table"] = comparison_data
                    logger.info(
                        "Comparison table rebuilt from cached data (%d attributes)",
                        len(comparison_data["rows"]),
                    )
                    
                    # Set compatibility result if found (even with fallback comparison)
                    if compatibility_result:
                        state["compatibility_result"] = compatibility_result
                    else:
                        state["compatibility_result"] = None
                    
                    try:
                        interactive = generate_interactive_elements(state["ai_response"], user_input)
                        state["quick_replies"] = interactive.quick_replies if config.features.get('enable_quick_replies', True) else None
                        state["suggested_followups"] = []
                    except Exception as e:
                        logger.warning(f"Failed to generate interactive elements: {e}")
                        state["quick_replies"] = None
                        state["suggested_followups"] = []
                    response_content = state["ai_response"]
                else:
                    # Use LLM-produced comparison
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
                    response_content = state["ai_response"]
            else:
                # No comparison_result - try fallback comparison or normal response
                fallback_comparison = None
                if _should_attempt_comparison(user_input):
                    fallback_comparison = _build_comparison_from_cached_products(
                        user_input,
                        products,
                        filters,
                    )
                if fallback_comparison:
                    comparison_data = fallback_comparison["table"]
                    state["ai_response"] = fallback_comparison["summary"]
                    state["comparison_table"] = comparison_data
                    logger.info(
                        "Generated comparison table from cached data (%d attributes)",
                        len(comparison_data["rows"]),
                    )
                    
                    # Set compatibility result if found (even with fallback comparison)
                    if compatibility_result:
                        state["compatibility_result"] = compatibility_result
                    else:
                        state["compatibility_result"] = None
                    
                    try:
                        interactive = generate_interactive_elements(state["ai_response"], user_input)
                        state["quick_replies"] = interactive.quick_replies if config.features.get('enable_quick_replies', True) else None
                        state["suggested_followups"] = []
                    except Exception as e:
                        logger.warning(f"Failed to generate interactive elements: {e}")
                        state["quick_replies"] = None
                        state["suggested_followups"] = []
                    response_content = state["ai_response"]
                else:
                    # Normal response - no comparison
                    state["ai_response"] = response_content
                    # Only clear comparison_table if it wasn't already set (e.g., by compatibility tool)
                    # If comparison_table was already set, preserve it (don't overwrite)
                    if state.get("comparison_table") is None:
                        state["comparison_table"] = None
                    
                    # Set compatibility result if found, otherwise clear it
                    if compatibility_result:
                        state["compatibility_result"] = compatibility_result
                    else:
                        state["compatibility_result"] = None

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
        state["compatibility_result"] = None
        state["comparison_table"] = None

    return state


def _build_comparison_from_cached_products(
    user_input: str,
    products: List[Dict[str, Any]],
    filters: Dict[str, Any],
    comparison_product_names: Optional[List[str]] = None,
) -> Optional[Dict[str, Any]]:
    if not products:
        return None

    selected = _select_products_for_comparison(user_input, products, comparison_product_names)
    if len(selected) < 2:
        return None

    country = (filters or {}).get("country") or "us"
    language = (filters or {}).get("language")

    attribute_maps: List[OrderedDict[str, str]] = []
    product_names: List[str] = []
    for product in selected:
        detail = _fetch_product_detail(product, country=country, language=language)
        attr_map = _create_attribute_map(product, detail)
        if not attr_map:
            continue
        attribute_maps.append(attr_map)
        product_names.append(_display_product_name(product))

    if len(attribute_maps) < 2:
        return None

    ordered_attrs = _determine_attribute_order(attribute_maps)
    if not ordered_attrs:
        return None

    rows: List[List[str]] = []
    for attr in ordered_attrs[:MAX_COMPARISON_ATTRIBUTES]:
        row = [attr]
        for attr_map in attribute_maps:
            row.append(attr_map.get(attr, "—"))
        rows.append(row)

    table = {
        "headers": ["Attribute"] + product_names,
        "rows": rows,
    }
    summary = _build_comparison_summary(product_names, attribute_maps, filters)
    return {"summary": summary, "table": table}


def _should_attempt_comparison(user_input: str) -> bool:
    if not user_input:
        return False
    lowered = user_input.lower()
    return any(keyword in lowered for keyword in ("compare", "vs", "versus", "#", "top", "which"))


def _select_products_for_comparison(
    user_input: str,
    products: List[Dict[str, Any]],
    comparison_product_names: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    if not products:
        return []

    selected: List[Dict[str, Any]] = []
    used_indices: set[int] = set()

    def add_by_index(idx: int):
        if 0 <= idx < len(products) and idx not in used_indices:
            selected.append(products[idx])
            used_indices.add(idx)

    if comparison_product_names:
        for name in comparison_product_names:
            idx = _match_product_by_name(name, products, used_indices)
            if idx is not None:
                add_by_index(idx)

    if user_input:
        for match in re.findall(r"#?\s*(\d+)", user_input):
            try:
                idx = int(match) - 1
            except ValueError:
                continue
            add_by_index(idx)

        lowered = user_input.lower()
        if not used_indices and "top" in lowered:
            top_match = re.search(r'top\s+(\d+)', lowered)
            count = 3
            if top_match:
                try:
                    count = max(2, int(top_match.group(1)))
                except ValueError:
                    count = 3
            for idx in range(min(count, len(products))):
                add_by_index(idx)

    if len(selected) < 2:
        for idx in range(len(products)):
            add_by_index(idx)
            if len(selected) >= 3:
                break

    return selected[:4]


def _match_product_by_name(
    name: str,
    products: List[Dict[str, Any]],
    used_indices: set[int],
) -> Optional[int]:
    if not name:
        return None
    target = name.lower()
    for idx, product in enumerate(products):
        if idx in used_indices:
            continue
        product_name = _display_product_name(product).lower()
        if target in product_name or product_name in target:
            return idx
    return None


def _display_product_name(product: Dict[str, Any]) -> str:
    product_info = product.get("product") or {}
    title = (
        product.get("title")
        or product_info.get("title")
        or product_info.get("name")
        or product.get("model")
        or "Unnamed product"
    )
    brand = product.get("brand") or product_info.get("brand")
    if brand and brand.lower() not in title.lower():
        return f"{brand} {title}".strip()
    return title


def _fetch_product_detail(
    product: Dict[str, Any],
    country: str = "us",
    language: Optional[str] = None,
) -> Dict[str, Any]:
    product_info = product.get("product") or {}
    product_id = (
        product_info.get("identifier")
        or product_info.get("id")
        or product.get("id")
    )
    if not product_id:
        return {}

    payload: Dict[str, Any] = {"product_id": product_id}
    if country:
        payload["country"] = country
    if language:
        payload["language"] = language

    try:
        response = get_product_details.invoke(payload)
        if isinstance(response, str):
            return json.loads(response)
        if isinstance(response, dict):
            return response
    except Exception as exc:
        logger.debug(f"Product detail lookup failed for {product_id}: {exc}")
    return {}


def _create_attribute_map(
    product: Dict[str, Any],
    detail: Dict[str, Any],
) -> OrderedDict[str, str]:
    attr_map: OrderedDict[str, str] = OrderedDict()

    def add_attr(name: str, value: Any):
        normalized_name = _normalize_attribute_name(name)
        if not normalized_name or normalized_name in attr_map:
            return
        formatted_value = _format_attribute_value(value)
        if formatted_value:
            attr_map[normalized_name] = formatted_value

    price_text = product.get("price_text") or product.get("offer", {}).get("price")
    price_value = product.get("price_value")
    currency = product.get("price_currency") or product.get("offer", {}).get("currency")
    if price_text:
        add_attr("Price", price_text)
    elif isinstance(price_value, (int, float)):
        prefix = "$" if not currency or currency.upper() == "USD" else f"{currency.upper()} "
        add_attr("Price", f"{prefix}{price_value:,.2f}")

    seller = product.get("source") or product.get("offer", {}).get("seller")
    if seller:
        add_attr("Seller", seller)

    rating = product.get("rating")
    if isinstance(rating, (int, float)):
        add_attr("Rating", f"{rating:.1f}/5")

    rating_count = product.get("rating_count") or product.get("reviewCount") or product.get("reviews")
    if rating_count:
        if isinstance(rating_count, (int, float)):
            add_attr("Review Count", f"{int(rating_count):,}")
        else:
            add_attr("Review Count", rating_count)

    availability = product.get("offer", {}).get("availability")
    if availability:
        add_attr("Availability", availability)

    potential_sources: List[Any] = []
    product_info = product.get("product") or {}
    for key in ("attributes", "specs", "specifications"):
        value = product_info.get(key)
        if value:
            potential_sources.append(value)
    for key in ("attributes", "specs", "specifications", "details", "features", "additionalInformation"):
        value = detail.get(key)
        if value:
            potential_sources.append(value)

    for source in potential_sources:
        _collect_attributes_from_source(source, add_attr)

    return attr_map


def _collect_attributes_from_source(source: Any, add_attr: Callable[[str, Any], None]) -> None:
    if isinstance(source, dict):
        for key, value in source.items():
            if isinstance(value, (dict, list)):
                _collect_attributes_from_source(value, add_attr)
            else:
                add_attr(key, value)
    elif isinstance(source, list):
        for item in source:
            if isinstance(item, dict):
                if "name" in item and "value" in item:
                    add_attr(item["name"], item["value"])
                elif "label" in item and "value" in item:
                    add_attr(item["label"], item["value"])
                else:
                    for key in ("attributes", "items", "values", "specs", "details"):
                        if key in item:
                            _collect_attributes_from_source(item[key], add_attr)
                    for key, value in item.items():
                        if key not in ("attributes", "items", "values", "specs", "details"):
                            if not isinstance(value, (dict, list)):
                                add_attr(key, value)


def _determine_attribute_order(attribute_maps: List[OrderedDict[str, str]]) -> List[str]:
    seen: List[str] = []
    for attr_map in attribute_maps:
        for key in attr_map.keys():
            if key not in seen:
                seen.append(key)

    ordered: List[str] = []
    for preferred in ATTRIBUTE_PRIORITY:
        for key in seen:
            if key.lower() == preferred.lower() and key not in ordered:
                ordered.append(key)
                break

    for key in seen:
        if key not in ordered:
            ordered.append(key)

    return ordered


def _build_comparison_summary(
    product_names: List[str],
    attribute_maps: List[OrderedDict[str, str]],
    filters: Dict[str, Any],
) -> str:
    product_label = (
        filters.get("product")
        or filters.get("category")
        or filters.get("keywords")
        or "options"
    )
    product_label = str(product_label).strip()
    if product_label:
        product_label = product_label.replace("_", " ")
    summary_lines = [
        f"Here's a comparison of the top {len(product_names)} {product_label} options:".strip()
    ]

    highlight_keys = [
        "Price",
        "Capacity",
        "Speed",
        "Cores / Threads",
        "Base Clock",
        "Boost Clock",
        "Rating",
    ]

    for name, attrs in zip(product_names, attribute_maps):
        highlights: List[str] = []
        for key in highlight_keys:
            value = attrs.get(key)
            if not value:
                continue
            if key == "Rating" and attrs.get("Review Count"):
                highlights.append(f"{value} ({attrs['Review Count']} reviews)")
            else:
                highlights.append(value)
            if len(highlights) >= 2:
                break
        if not highlights:
            highlights = list(attrs.values())[:2]
        highlight_text = ", ".join(highlights) if highlights else ""
        if highlight_text:
            summary_lines.append(f"- **{name}**: {highlight_text}")
        else:
            summary_lines.append(f"- **{name}**")

    summary_lines.append("Let me know if you want help choosing or need deeper specs.")
    return "\n".join(summary_lines)


def _normalize_attribute_name(name: Any) -> str:
    if not name:
        return ""
    text = str(name).strip().strip(":")
    if not text:
        return ""
    text = re.sub(r"[_\-]+", " ", text)
    text = re.sub(r"\s+", " ", text)
    words = []
    for word in text.split(" "):
        if not word:
            continue
        if word.isupper() and len(word) <= 4:
            words.append(word)
        else:
            words.append(word.capitalize())
    return " ".join(words)


def _format_attribute_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (int, float)):
        return f"{value}"
    if isinstance(value, list):
        formatted_items = [_format_attribute_value(item) for item in value]
        formatted_items = [item for item in formatted_items if item]
        return ", ".join(formatted_items)
    if isinstance(value, dict):
        if "name" in value and "value" in value:
            return _format_attribute_value(value["value"])
        parts = []
        for key, val in value.items():
            formatted = _format_attribute_value(val)
            if formatted:
                parts.append(f"{_normalize_attribute_name(key)}: {formatted}")
        return ", ".join(parts)
    text = str(value).strip()
    return text


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
    state: ProductSearchState,
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
