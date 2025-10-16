"""
Web research node for enriching recommendations with market insights.

Uses web search to find the best vehicle matches when user has
implicit preferences but no specific make/model in mind.
"""
import json
from typing import Dict, Any
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.prebuilt import create_react_agent
from idss_agent.state import VehicleSearchState
from idss_agent.tools.web_research import research_vehicle_recommendations


# Web research agent prompt
WEB_RESEARCH_PROMPT = """
You are a vehicle research specialist helping to find the best vehicle matches for a customer.

Based on the customer's preferences, lifestyle, and use cases, use web research to find
specific vehicle recommendations (makes and models) that would be a great fit.

Customer's information:
{customer_context}

Your task:
1. Formulate a search query based on their needs (e.g., "best family SUV with 3 rows under 35k 2024")
2. Use the research_vehicle_recommendations tool to search
3. Extract specific makes and models from the research
4. Update the explicit filters with these recommendations

Focus on:
- Specific vehicle makes and models that match their needs
- Current year and recent model years that fit their budget
- Vehicles that align with their priorities (safety, reliability, fuel economy, etc.)

After research, provide:
1. Recommended makes/models to search for
2. Brief reasoning for each recommendation
3. Any additional filters to apply (body style, year range, features)
"""


def web_research_node(state: VehicleSearchState) -> VehicleSearchState:
    """
    Perform web research to enrich recommendations.

    This node:
    1. Analyzes customer's implicit preferences and use cases
    2. Performs targeted web research for vehicle recommendations
    3. Extracts specific makes/models from research results
    4. Updates filters with researched recommendations

    Args:
        state: Current vehicle search state

    Returns:
        Updated state with enriched filters from web research
    """
    # Build customer context
    implicit = state.get("implicit_preferences", {})
    insights = state.get("exploration_insights", {})
    filters = state.get("explicit_filters", {})

    # Create a comprehensive customer context
    context_parts = []

    if insights.get("use_cases"):
        context_parts.append(f"Use cases: {', '.join(insights['use_cases'])}")

    if insights.get("lifestyle_notes"):
        context_parts.append(f"Lifestyle: {insights['lifestyle_notes']}")

    if insights.get("current_situation"):
        context_parts.append(f"Current situation: {insights['current_situation']}")

    if implicit.get("priorities"):
        context_parts.append(f"Priorities: {', '.join(implicit['priorities'])}")

    if implicit.get("lifestyle"):
        context_parts.append(f"Lifestyle type: {implicit['lifestyle']}")

    if filters.get("price"):
        context_parts.append(f"Budget: ${filters['price']}")

    if filters.get("body_style"):
        context_parts.append(f"Preferred body style: {filters['body_style']}")

    if insights.get("must_haves"):
        context_parts.append(f"Must-haves: {', '.join(insights['must_haves'])}")

    customer_context = "\n".join(context_parts) if context_parts else "No detailed context available"

    # Create the research agent with web search tool
    llm = ChatOpenAI(model="gpt-4o", temperature=0)

    # Create ReAct agent with web research tool
    research_agent = create_react_agent(llm, tools=[research_vehicle_recommendations])

    try:
        # Build the prompt with customer context
        full_prompt = WEB_RESEARCH_PROMPT.format(customer_context=customer_context)
        full_prompt += "\n\nFind the best vehicle recommendations for this customer and extract specific makes/models."

        # Run the research agent
        result = research_agent.invoke({
            "messages": [HumanMessage(content=full_prompt)]
        })

        # Extract the final response
        messages = result.get("messages", [])
        if messages:
            final_message = messages[-1]
            research_insights = final_message.content

            # Parse the recommendations and update filters
            # Use LLM to extract structured data from research
            extraction_llm = ChatOpenAI(model="gpt-4o", temperature=0)

            extraction_prompt = f"""
Based on this vehicle research, extract specific makes and models to search for.

Research results:
{research_insights}

Current filters:
{json.dumps(filters, indent=2)}

Output JSON with recommended filters:
{{
  "make": "Toyota,Honda,Subaru",  // comma-separated makes
  "model": "RAV4,CR-V,Outback",  // comma-separated models (optional)
  "year": "2020-2024",  // recommended year range
  "body_style": "suv",  // if clear from research
  "notes": "Brief explanation of why these vehicles match"
}}

Output ONLY valid JSON.
"""

            extraction_response = extraction_llm.invoke([
                SystemMessage(content="Extract structured filter data from vehicle research."),
                HumanMessage(content=extraction_prompt)
            ])

            # Parse extraction
            content = extraction_response.content.strip()
            if content.startswith("```json"):
                content = content[7:]
            if content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()

            recommended_filters = json.loads(content)

            # Update explicit filters with research recommendations
            # Only add filters that don't already exist
            current_filters = state.get("explicit_filters", {})

            if recommended_filters.get("make") and not current_filters.get("make"):
                current_filters["make"] = recommended_filters["make"]

            if recommended_filters.get("model") and not current_filters.get("model"):
                current_filters["model"] = recommended_filters["model"]

            if recommended_filters.get("year") and not current_filters.get("year"):
                current_filters["year"] = recommended_filters["year"]

            if recommended_filters.get("body_style") and not current_filters.get("body_style"):
                current_filters["body_style"] = recommended_filters["body_style"]

            state["explicit_filters"] = current_filters

            # Store research notes in exploration insights
            if recommended_filters.get("notes"):
                current_insights = state.get("exploration_insights", {})
                current_insights["web_research_notes"] = recommended_filters["notes"]
                state["exploration_insights"] = current_insights

    except Exception as e:
        print(f"Warning: Web research failed: {e}")
        # Continue without web research enrichment

    return state
