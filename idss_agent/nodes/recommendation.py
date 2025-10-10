"""
Recommendation agent node - uses ReAct to build a list of 20 vehicles.
"""
import json
from typing import Dict, Any
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage
from langgraph.prebuilt import create_react_agent
from idss_agent.state import VehicleSearchState
from idss_agent.tools.autodev_apis import search_vehicle_listings


def update_recommendation_list(state: VehicleSearchState) -> VehicleSearchState:
    """
    Use a ReAct agent to build a recommendation list of up to 20 vehicles.

    The agent:
    - Has access to search_vehicle_listings tool
    - Knows current filters and preferences
    - Goal: Return exactly 20 relevant vehicles (or fewer if not available)
    - Can loosen criteria if needed to reach 20

    Args:
        state: Current vehicle search state

    Returns:
        Updated state with recommended_vehicles populated
    """

    filters = state['explicit_filters']
    implicit = state['implicit_preferences']

    # Build prompt for recommendation agent
    recommendation_prompt = f"""
You are a vehicle recommendation agent. Your goal is to find up to 20 vehicles for the user.

**Current Filters:**
{json.dumps(filters, indent=2)}

**User Preferences:**
{json.dumps(implicit, indent=2)}

**Instructions:**
1. Use search_vehicle_listings tool with the current filters
2. ALWAYS set page=1 and limit=50
3. Once you get the results from the tool, your job is DONE
4. Respond with a simple summary like: "Found X vehicles matching the criteria."

**IMPORTANT:**
- Call the tool ONCE with current filters, page=1, limit=50
- After you see the tool results, immediately finish with a brief summary
- Do NOT call the tool multiple times
- Do NOT try to list all vehicles in your response
"""

    # Create ReAct agent with search tool
    tools = [search_vehicle_listings]
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    agent = create_react_agent(llm, tools)

    # Run the agent
    result = agent.invoke({"messages": [HumanMessage(content=recommendation_prompt)]})

    # Extract the final response from agent
    final_message = result['messages'][-1].content

    # Parse the search results from the agent's tool calls
    # Look through messages for tool results
    vehicles = []
    for msg in result['messages']:
        # Check if this is a tool message with search results
        if hasattr(msg, 'content') and isinstance(msg.content, str):
            try:
                # Try to parse as JSON
                data = json.loads(msg.content)

                # Check if it's a list of vehicles or has a data field
                if isinstance(data, list):
                    vehicles = data
                    break
                elif isinstance(data, dict):
                    if 'data' in data and isinstance(data['data'], list):
                        vehicles = data['data']
                        break
                    elif 'vehicles' in data and isinstance(data['vehicles'], list):
                        vehicles = data['vehicles']
                        break
            except (json.JSONDecodeError, AttributeError):
                continue

    # Limit to 20 vehicles
    state['recommended_vehicles'] = vehicles[:20]

    return state


def parse_vehicle_list(response_content: str) -> list[Dict[str, Any]]:
    """
    Parse vehicle list from agent response.

    Expects JSON format from the agent.

    Args:
        response_content: Agent's response content

    Returns:
        List of vehicle dictionaries
    """
    try:
        # Try to find JSON in the response
        content = response_content.strip()

        # Strip markdown if present
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()

        # Parse JSON
        vehicles = json.loads(content)

        if isinstance(vehicles, list):
            return vehicles[:20]  
        elif isinstance(vehicles, dict) and 'vehicles' in vehicles:
            return vehicles['vehicles'][:20]
        else:
            return []

    except json.JSONDecodeError:
        print(f"Warning: Could not parse vehicle list from response")
        return []
