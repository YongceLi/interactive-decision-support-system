"""
Discovery agent node - generates responses with listing summary and elicitation questions.
"""
import json
from typing import List, Dict, Any
from langchain_openai import ChatOpenAI
from idss_agent.state import VehicleSearchState


def format_vehicles_for_llm(vehicles: List[Dict[str, Any]], limit: int = 10) -> str:
    """
    Format vehicle list for LLM consumption.

    Args:
        vehicles: List of vehicle dictionaries
        limit: Maximum number of vehicles to format

    Returns:
        Formatted string with vehicle details
    """
    if not vehicles:
        return "No vehicles in current list."

    formatted = []
    for i, vehicle in enumerate(vehicles[:limit], 1):
        year = vehicle.get('year', 'N/A')
        make = vehicle.get('make', 'N/A')
        model = vehicle.get('model', 'N/A')
        price = vehicle.get('price', vehicle.get('retailListing', {}).get('price', 'N/A'))
        miles = vehicle.get('miles', vehicle.get('retailListing', {}).get('miles', 'N/A'))
        location = vehicle.get('location', vehicle.get('retailListing', {}).get('city', 'N/A'))

        if isinstance(price, (int, float)):
            price_str = f"${price:,}"
        else:
            price_str = str(price)

        if isinstance(miles, (int, float)):
            miles_str = f"{miles:,} miles"
        else:
            miles_str = str(miles)

        vehicle_line = f"{i}. {year} {make} {model} - {price_str} | {miles_str}"
        if location != 'N/A':
            vehicle_line += f" | {location}"

        formatted.append(vehicle_line)

    return "\n".join(formatted)


def discovery_response_generator(state: VehicleSearchState) -> VehicleSearchState:
    """
    Generate full discovery response using LLM:
    1. Acknowledge user preferences
    2. Summarize current listings (show actual vehicles, highlight pros, recommend)
    3. Ask 2-3 strategic elicitation questions

    All in one natural, conversational response.

    Args:
        state: Current vehicle search state

    Returns:
        Updated state with ai_response
    """

    filters = state['explicit_filters']
    implicit = state['implicit_preferences']
    vehicles = state['recommended_vehicles']
    already_asked = state.get('questions_asked', [])

    # Format vehicles for LLM
    vehicles_summary = format_vehicles_for_llm(vehicles, limit=10)

    # Build conversational prompt
    prompt = f"""
You're a helpful friend helping someone find their perfect car. Be casual, friendly, and conversational.

**User's Current Preferences:**
{json.dumps(filters, indent=2)}

**Current Listings ({len(vehicles)} vehicles found):**
{vehicles_summary}

**Topics Already Asked About:** {already_asked}

**Your Task:**
Write a short, friendly response (1 paragraph max) that:
1. Acknowledges what they're looking for
2. Mentions 1-2 interesting options from the listings
3. Asks 1-2 NEW questions to help narrow things down

**IMPORTANT:** Do NOT ask about preferences they've already provided! Look at their current filters and only ask about missing information like:
- Body style (if not specified)
- Features/priorities (if not mentioned)
- Timeline for purchase
- Location/zip code (if not given)

Be like a knowledgeable friend who knows cars - not too formal, not too salesy. Keep it under 100 words and make it feel like a real conversation.

Generate your response:
"""

    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.7)
    response = llm.invoke(prompt)

    state['ai_response'] = response.content.strip()

    # Extract and track which topics were asked about
    state = extract_questions_asked(state, response.content)

    return state


def extract_questions_asked(state: VehicleSearchState, ai_response: str) -> VehicleSearchState:
    """
    Use LLM to extract which topics were asked about in the response.

    This allows us to avoid repeating questions in future turns.

    Args:
        state: Current vehicle search state
        ai_response: The assistant's response text

    Returns:
        Updated state with questions_asked list
    """

    extraction_prompt = f"""
Given this assistant response, identify which topics were asked about in the questions.

Response:
"{ai_response}"

Possible topics:
- budget (asking about price range or budget)
- location (asking about zip code, city, or location)
- usage (asking about how they'll use the vehicle, purpose, driving patterns)
- priorities (asking what matters most, what they value)
- mileage (asking about mileage preferences)
- vehicle_type (asking about SUV, sedan, truck, body style)
- features (asking about specific features needed)
- timeline (asking when they need the vehicle)

Return ONLY a JSON array of topics that were asked about, e.g.:
["budget", "location", "usage"]

If no questions were asked, return an empty array: []
"""

    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
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
