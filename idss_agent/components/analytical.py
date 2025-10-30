"""
Analytical agent - answers specific questions about vehicles using ReAct.
"""
import os
import json
import re
from typing import Optional, Callable, Dict, List, Any
from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent
from idss_agent.config import get_config
from idss_agent.prompt_loader import render_prompt
from idss_agent.state import VehicleSearchState, AgentResponse, ComparisonTable
from idss_agent.components.autodev_apis import get_vehicle_listing_by_vin, get_vehicle_photos_by_vin
from idss_agent.components.vehicle_database import get_vehicle_database_tools
from idss_agent.logger import get_logger

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
        if 'vehicles' not in comparison_data or 'attributes' not in comparison_data:
            return None

        # Build comparison table
        vehicles = comparison_data['vehicles']
        attributes = comparison_data['attributes']

        # Create headers: ["Attribute", "Vehicle 1", "Vehicle 2", ...]
        headers = ["Attribute"] + vehicles

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
    Search the web for current information about vehicles.

    Use this tool when local databases don't have the information you need.
    This is especially useful for:
    - Recent model years not yet in databases
    - Current pricing and availability
    - Latest specifications and features
    - Recent safety ratings or reviews

    Args:
        query: Search query string (e.g., "2025 Honda Accord specifications")

    Returns:
        Search results with relevant information
    """
    try:
        # Import WebSearch here to avoid circular imports
        from langchain_community.tools.tavily_search import TavilySearchResults

        # Create Tavily search tool (requires TAVILY_API_KEY environment variable)
        search = TavilySearchResults(max_results=3)
        results = search.invoke({"query": query})

        # Format results
        if isinstance(results, list) and results:
            formatted = []
            for i, result in enumerate(results[:3], 1):
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
            "Examples: ['Vehicle #1', 'Vehicle #2', 'Compare both'], ['Show photos', 'Compare pricing', 'Safety ratings'], "
            "['Yes, show me', 'No, skip it', 'Not sure']. "
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


# System prompt for analytical agent (cached for efficiency)
ANALYTICAL_SYSTEM_PROMPT = """
You are an expert vehicle research analyst with access to comprehensive automotive databases and listing information.

Your role is to answer specific, data-driven questions about vehicles by leveraging the tools at your disposal.

## Available Tools

**Auto.dev API Tools:**
- `get_vehicle_listing_by_vin`: Retrieve complete listing details for a specific vehicle by VIN
  - Returns: pricing, location, dealer info, mileage, condition, features
  - Use when: User asks about a specific vehicle's details, availability, or pricing

- `get_vehicle_photos_by_vin`: Fetch photos for a specific vehicle by VIN
  - Returns: retail photos, exterior/interior images
  - Use when: User wants to see vehicle images or appearance details

**Database Tools:**
- `sql_db_list_tables`: List all available tables in the database
  - Returns: table names
  - Use when: You need to understand what data is available

- `sql_db_schema`: Get schema for specific tables
  - Input: table_names (comma-separated)
  - Returns: CREATE statements with column definitions
  - Use when: You need to understand table structure before querying

- `sql_db_query`: Execute SQL SELECT queries on the database
  - Input: SQL query string
  - Returns: Query results
  - **IMPORTANT**: ALWAYS check schema first before querying
  - Available databases:
    * `safety_data`: NHTSA crash test ratings, safety features (query by make, model, model_yr - use LIKE patterns!)
    * `feature_data`: EPA fuel economy, MPG ratings, engine specs (query by make, model, year)

**Web Search Tool:**
- `web_search`: Search the web for current information
  - Input: search query string
  - Returns: Search results with up-to-date information
  - **Use when**: Local databases don't have the information needed
  - Example queries: "2025 Honda Accord specifications", "Toyota Camry 2024 safety ratings"
  - This is your fallback when database queries return no results

## Guidelines

**Data Accuracy:**
1. ALWAYS verify table schema before writing SQL queries
2. Use exact column names and table names from schema
3. Handle case sensitivity properly - column names are lowercase: `make`, `model`, `model_yr` (not Make/Model/ModelYear)
4. If a query fails, check the schema and try again with correct column names
5. **IMPORTANT**: Model names may include variants (e.g., "ACCORD SEDAN", "ACCORD HYBRID")
   - Always use `LIKE '%ModelName%'` pattern matching instead of exact equality
   - Example: `WHERE model LIKE '%Accord%'` not `WHERE model = 'Accord'`

**Query Best Practices:**
1. Use WHERE clauses with LIKE patterns for make/model matching: `WHERE make LIKE '%Honda%' AND model LIKE '%Accord%'`
2. Use LIMIT to prevent overwhelming results (typically LIMIT 5-10)
3. Order results by relevance (e.g., model_yr DESC for latest models)
4. Aggregate data when comparing multiple vehicles (AVG, MAX, MIN)
5. Join tables when combining safety and fuel economy data
6. **Always use pattern matching** for model names to catch all variants

**Vehicle References:**
- When user references "#1", "#2", etc., use the VIN from the "Available Vehicles" context below
- When user says "top 3" or "first 3", they mean vehicles #1, #2, #3 from the context
- When user says "compare top 3" or "compare first few", extract VINs from context and compare those specific listings
- When comparing specific vehicles by number, use their VINs to fetch detailed data
- When discussing specific listings, use get_vehicle_listing_by_vin

**Comparison Queries (SPECIAL FORMAT):**
When user asks to compare 2-4 vehicles - WHETHER BY NAME (e.g., "compare Honda Accord vs Toyota Camry") OR BY REFERENCE (e.g., "compare top 3", "compare #1, #2, #3"):
1. Identify which vehicles to compare (by name or from Available Vehicles context)
2. Gather data for each vehicle using available tools (use get_vehicle_listing_by_vin for specific listings)
3. Output your response in this EXACT JSON format:
```json
{
  "summary": "2-3 sentence summary highlighting key differences",
  "comparison_data": {
    "vehicles": ["Honda Accord 2024", "Toyota Camry 2024"],
    "attributes": [
      {"name": "Price Range", "values": ["$28,500 - $36,200", "$27,400 - $35,000"]},
      {"name": "Safety Rating", "values": ["5-star ⭐⭐⭐⭐⭐", "5-star ⭐⭐⭐⭐⭐"]},
      {"name": "Fuel Economy (City)", "values": ["29 MPG", "28 MPG"]},
      {"name": "Fuel Economy (Highway)", "values": ["37 MPG", "39 MPG"]},
      {"name": "Fuel Economy (Combined)", "values": ["32 MPG", "32 MPG"]},
      {"name": "Engine", "values": ["1.5L 4-cyl", "2.5L 4-cyl"]},
      {"name": "Transmission", "values": ["CVT", "8-speed Auto"]}
    ]
  }
}
```
3. **CRITICAL**: For ALL comparison requests (including "top 3", "#1 vs #2", etc.), you MUST output ONLY the JSON format above - no other text
4. For specific vehicle comparisons (#1, #2, #3), use get_vehicle_listing_by_vin to get detailed data
5. Include these attributes when available:
   - Price Range (from CA dataset or web search)
   - Safety Rating (from safety_data database)
   - Fuel Economy - City/Highway/Combined (from feature_data database)
   - Engine (from feature_data database)
   - Transmission (from feature_data database)
   - Any other relevant specs user asked about

**Error Handling & Fallbacks:**
1. If database query returns no results:
   - First, check if you used LIKE patterns correctly
   - Try broader patterns: `LIKE '%Accord%'` instead of exact match
   - Check schema to verify column names
2. If local databases have no information:
   - Use web search tool to find current information online
   - Search for: "[make] [model] [year] specifications safety ratings"
3. Only after trying all available tools should you say information is unavailable

Think step-by-step:
1. Understand what the user is asking - is it general or specific?
2. Identify which tools/databases are needed
3. Check schema if using SQL
4. Execute tools in logical order
5. **Synthesize information concisely:**
   - For general questions: 2-3 highlights + invitation to ask more
   - For specific questions: Direct answer + 1-2 related points
   - Think: "What would a salesperson say?"
6. Keep total response to 3-4 sentences for general queries
"""


def analytical_agent(
    state: VehicleSearchState,
    progress_callback: Optional[Callable[[dict], None]] = None
) -> VehicleSearchState:
    """
    Agent that answers specific questions about vehicles using available data.

    This creates a ReAct agent with access to:
    - Vehicle details by VIN
    - Vehicle photos
    - Safety database (NHTSA ratings)
    - Fuel economy database (EPA data)

    Uses system + user message format for optimal prompt caching:
    - System message: Role, tools, guidelines (cached)
    - User message: Vehicle context + question (dynamic)

    Args:
        state: Current state with vehicle context and user question
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
        state["ai_response"] = "I didn't receive a question. How can I help you with vehicle information?"
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
    db_tools = get_vehicle_database_tools(llm)
    tools = [
        get_vehicle_listing_by_vin,
        get_vehicle_photos_by_vin,
        web_search  # Add web search as fallback tool
    ] + db_tools

    # Build vehicle context from state
    vehicles = state.get("recommended_vehicles", [])
    filters = state.get("explicit_filters", {})
    preferences = state.get("implicit_preferences", {})

    # Create vehicle reference map (for "#1", "#2" references)
    vehicle_context_parts = []

    if vehicles:
        vehicle_context_parts.append("## Available Vehicles (for reference)\n")
        for i, vehicle in enumerate(vehicles[:10], 1):
            v = vehicle.get("vehicle", {})
            listing = vehicle.get("retailListing", {})
            price = listing.get("price", 0)
            miles = listing.get("miles", 0)
            vehicle_context_parts.append(
                f"#{i}: {v.get('year')} {v.get('make')} {v.get('model')} | "
                f"${price:,} | {miles:,} miles | VIN: {v.get('vin')}"
            )

    # Add search context if available
    if filters:
        active_filters = {k: v for k, v in filters.items() if v}
        if active_filters:
            vehicle_context_parts.append("\n## Current Search Filters")
            for key, value in active_filters.items():
                vehicle_context_parts.append(f"- {key}: {value}")

    if preferences:
        active_prefs = {k: v for k, v in preferences.items() if v}
        if active_prefs:
            vehicle_context_parts.append("\n## User Preferences")
            for key, value in active_prefs.items():
                vehicle_context_parts.append(f"- {key}: {value}")

    # Build messages for agent
    messages = [SystemMessage(content=ANALYTICAL_SYSTEM_PROMPT)]

    # Add vehicle context if available (before conversation history)
    if vehicle_context_parts:
        vehicle_context = "\n".join(vehicle_context_parts)
        messages.append(HumanMessage(content=f"Context:\n{vehicle_context}"))

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
                logger.info(f"Comparison detected: {len(comparison_result['comparison_table'].headers)} vehicles compared")

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
        elif "invalid" in error_msg and "vin" in error_msg:
            state["ai_response"] = "I couldn't find that vehicle. Please check the VIN or vehicle number and try again."
        else:
            state["ai_response"] = "I encountered an error while researching your question. Please try rephrasing it or ask something else."

        # Set empty interactive elements on error
        state["quick_replies"] = None
        state["suggested_followups"] = []

    return state
