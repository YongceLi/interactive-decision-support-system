"""
Semantic parser node for extracting vehicle search criteria from user input.
"""
import json
from typing import Optional, Callable
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from idss_agent.logger import get_logger
from idss_agent.state import VehicleSearchState, get_latest_user_message
from idss_agent.config import get_config
from idss_agent.prompt_loader import render_prompt

logger = get_logger("components.semantic_parser")


def semantic_parser_node(
    state: VehicleSearchState,
    progress_callback: Optional[Callable[[dict], None]] = None
) -> VehicleSearchState:
    """
    Semantic parser node that extracts vehicle preferences from the ENTIRE conversation.

    This node:
    1. Analyzes the COMPLETE conversation history
    2. Uses an LLM to generate COMPLETE filters representing current search intent
    3. REPLACES filters entirely (not merge) based on LLM's analysis
    4. Stores previous filters for history tracking

    Args:
        state: Current vehicle search state
        progress_callback: Optional callback for progress updates

    Returns:
        Updated state with parsed filters and preferences
    """
    # Get the latest user message from conversation history
    user_input = get_latest_user_message(state)

    if not user_input:
        return state

    # Emit progress: Starting semantic parsing
    if progress_callback:
        progress_callback({
            "step_id": "semantic_parsing",
            "description": "Analyzing your message for search criteria",
            "status": "in_progress"
        })

    # Get configuration
    config = get_config()
    model_config = config.get_model_config('semantic_parser')

    # Create LLM with config parameters
    llm = ChatOpenAI(
        model=model_config['name'],
        temperature=model_config['temperature'],
        max_tokens=model_config.get('max_tokens')
    )

    # Build COMPLETE conversation context from ALL LangChain messages
    history_context = "\n".join([
        f"{'User' if isinstance(msg, HumanMessage) else 'Assistant'}: {msg.content}"
        for msg in state.get("conversation_history", [])  # ALL messages, not just last 5
    ])

    # Store current filters as previous (for history tracking)
    current_filters = state.get("explicit_filters", {})
    current_implicit = state.get("implicit_preferences", {})

    context_info = f"""
COMPLETE Conversation History:
{history_context}

Based on the ENTIRE conversation above, extract the user's CURRENT search intent.
"""

    # Load system prompt from template
    system_prompt = render_prompt('semantic_parser.j2')

    # Call LLM to parse
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=context_info)
    ]

    response = llm.invoke(messages)

    try:
        # Strip markdown code blocks if present
        content = response.content.strip()
        if content.startswith("```json"):
            content = content[7:]  # Remove ```json
        if content.startswith("```"):
            content = content[3:]  # Remove ```
        if content.endswith("```"):
            content = content[:-3]  # Remove trailing ```
        content = content.strip()

        parsed_data = json.loads(content)

        # Check if there are new filters
        has_new_filters = parsed_data.get("has_new_filters", True)  # Default to True for backward compatibility

        if not has_new_filters:
            # User is asking a follow-up question, not providing new filters
            logger.info("No new filters detected - user asking follow-up question, keeping existing filters")

            # Emit progress: Semantic parsing complete (no changes)
            if progress_callback:
                progress_callback({
                    "step_id": "semantic_parsing",
                    "description": "No new search criteria detected",
                    "status": "completed"
                })

            return state

        # REPLACE explicit filters entirely (not merge!)
        new_filters = parsed_data.get("explicit_filters", {})

        # Log the change for debugging
        if new_filters != current_filters:
            logger.info(f"Filters changed: {current_filters} → {new_filters}")
        else:
            logger.info("New filters extracted (same as current)")

        state["explicit_filters"] = new_filters  # REPLACE, not merge!

        # REPLACE implicit preferences entirely
        new_implicit = parsed_data.get("implicit_preferences", {})
        state["implicit_preferences"] = new_implicit  # REPLACE, not merge!

    except json.JSONDecodeError as e:
        # If parsing fails, log it but don't crash
        logger.warning(f"Failed to parse LLM response as JSON: {e}")
        logger.debug(f"Response content: {response.content}")

    # Emit progress: Semantic parsing complete
    if progress_callback:
        progress_callback({
            "step_id": "semantic_parsing",
            "description": "Search criteria extracted",
            "status": "completed"
        })

    return state


def format_state_summary(state: VehicleSearchState) -> str:
    """
    Format the current state into a readable summary.

    Args:
        state: Current vehicle search state

    Returns:
        Human-readable string summary of the state
    """
    filters = state.get("explicit_filters", {})
    implicit = state.get("implicit_preferences", {})

    summary_parts = []

    # Format explicit filters
    if filters:
        summary_parts.append("**Search Criteria:**")
        for key, value in filters.items():
            if value:
                summary_parts.append(f"  - {key.replace('_', ' ').title()}: {value}")

    # Format implicit preferences
    if implicit:
        summary_parts.append("\n**Inferred Preferences:**")
        for key, value in implicit.items():
            if value:
                if isinstance(value, list):
                    summary_parts.append(f"  - {key.replace('_', ' ').title()}: {', '.join(value)}")
                else:
                    summary_parts.append(f"  - {key.replace('_', ' ').title()}: {value}")

    return "\n".join(summary_parts) if summary_parts else "No preferences captured yet."
