"""
Analytical agent - answers specific questions about vehicles using ReAct.
"""
import os
from typing import Optional, Callable
from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from langgraph.prebuilt import create_react_agent
from idss_agent.config import get_config
from idss_agent.prompt_loader import render_prompt
from idss_agent.state import VehicleSearchState
from idss_agent.components.autodev_apis import get_vehicle_listing_by_vin, get_vehicle_photos_by_vin
from idss_agent.components.vehicle_database import get_vehicle_database_tools
from idss_agent.logger import get_logger

logger = get_logger("components.analytical_tool")


class InteractiveElements(BaseModel):
    """Quick replies and suggestions for analytical responses."""
    quick_replies: Optional[list[str]] = Field(
        default=None,
        description=(
            "Short answer options (less than 5 words each) if the response asks a direct question. "
            "Provide less than 5 options. Leave null if no direct question asked. "
        )
    )
    suggested_followups: list[str] = Field(
        description=(
            "Suggested next user inputs (short phrases, less than 5 options) to help users continue exploration. "
            "Should be contextually relevant to the analytical response and ask for new information."
        ),
        max_length=5
    )


def generate_interactive_elements(ai_response: str, user_question: str) -> InteractiveElements:
    """
    Generate quick replies and suggested followups for an analytical response.

    Args:
        ai_response: The analytical agent's response
        user_question: The user's original question

    Returns:
        InteractiveElements with quick_replies and suggested_followups
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
    * `safety_data`: NHTSA crash test ratings, safety features (query by Make, Model, ModelYear)
    * `feature_data`: EPA fuel economy, MPG ratings, engine specs (query by Make, Model, Year)

## Guidelines

**Data Accuracy:**
1. ALWAYS verify table schema before writing SQL queries
2. Use exact column names and table names from schema
3. Handle case sensitivity properly (Make/Model/Year vs make/model/year)
4. If a query fails, check the schema and try again with correct column names

**Query Best Practices:**
1. Use WHERE clauses to filter by Make, Model, Year when relevant
2. Use LIMIT to prevent overwhelming results (typically LIMIT 5-10)
3. Order results by relevance (e.g., ModelYear DESC for latest models)
4. Aggregate data when comparing multiple vehicles (AVG, MAX, MIN)
5. Join tables when combining safety and fuel economy data

**Vehicle References:**
- When user references "#1", "#2", etc., use the VIN from the provided context
- When comparing vehicles, fetch data for each using appropriate tools
- When discussing specific listings, use get_vehicle_listing_by_vin

**Response Quality:**
1. Be concise and direct - answer the specific question asked in one concise paragraph
2. Use bullet points for multiple data points
3. Include relevant numbers, ratings, and comparisons
4. Cite data sources when helpful (e.g., "According to NHTSA safety ratings...")
5. If data is unavailable, clearly state what you couldn't find and why

**Error Handling:**
- If a VIN is invalid or not found, explain clearly
- If database query returns no results, suggest why (model year not in database, name mismatch)
- If tools fail, try alternative approaches or explain limitations

**Common Queries:**
- Safety ratings: Query safety_data by Make/Model/ModelYear
- Fuel economy: Query feature_data by Make/Model/Year
- Vehicle comparisons: Fetch data for each vehicle, present side-by-side
- Specific vehicle details: Use get_vehicle_listing_by_vin with VIN
- Feature availability: Check listing details or feature_data

Think step-by-step:
1. Understand what the user is asking
2. Identify which tools/databases are needed
3. Check schema if using SQL
4. Execute tools in logical order
5. Synthesize information into a clear answer
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
        get_vehicle_photos_by_vin
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
        else:
            state["ai_response"] = response_content
            logger.info(f"Analytical agent: Response generated ({len(response_content)} chars)")

            # Generate interactive elements (quick replies + suggestions)
            try:
                interactive = generate_interactive_elements(response_content, user_input)
                state["quick_replies"] = interactive.quick_replies
                state["suggested_followups"] = interactive.suggested_followups
            except Exception as e:
                logger.warning(f"Failed to generate interactive elements: {e}")
                # Fallback to sensible defaults
                state["quick_replies"] = None
                state["suggested_followups"] = [
                    "Compare with alternatives",
                    "Show me similar vehicles",
                    "What about other features?",
                    "Check pricing options"
                ]

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
