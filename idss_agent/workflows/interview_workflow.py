"""
Interview workflow - asks questions to understand user needs before making recommendations.

This workflow runs until the interview is complete (threshold reached or user requests vehicles).
"""
import os
import json
import re
from typing import Any
from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import create_react_agent
from idss_agent.logger import get_logger
from idss_agent.state import (
    VehicleSearchState,
    get_latest_user_message,
    VehicleFiltersPydantic,
    ImplicitPreferencesPydantic
)
from idss_agent.components.semantic_parser import semantic_parser_node
from idss_agent.components.recommendation import update_recommendation_list
from langchain_tavily import TavilySearch

logger = get_logger("workflows.interview")

# Structured output schema for interview mode
class InterviewResponse(BaseModel):
    """Structured response from interview agent."""
    response: str = Field(description="Your conversational response to the user")
    should_end: bool = Field(description="True if interview mode should end, false to continue")


# Structured output schema for extraction
class ExtractionResult(BaseModel):
    """Structured extraction from interview conversation."""
    explicit_filters: VehicleFiltersPydantic = Field(
        default_factory=VehicleFiltersPydantic,
        description="Explicit vehicle filters with specific fields"
    )
    implicit_preferences: ImplicitPreferencesPydantic = Field(
        default_factory=ImplicitPreferencesPydantic,
        description="Implicit preferences with specific fields"
    )


# Structured output schema for make/model discovery
class MakeModelRecommendation(BaseModel):
    """Recommended make/model from web research."""
    make: str = Field(description="Single vehicle make, e.g., 'Toyota'")
    model: str = Field(description="Single vehicle model, e.g., 'RAV4'")
    reasoning: str = Field(description="A brief explanation of why this vehicle matches the criteria. Imagine you are the car salesperson, use friendly, persuasive, conversational tone and language")


# System prompt for interviewer
INTERVIEW_SYSTEM_PROMPT = """
You are a friendly, knowledgeable, human-like car salesperson.

Your job is to have a natural conversation to understand the customer's situation, needs, and preferences before making any vehicle recommendations.

Follow these principles:
- Be warm, empathetic, and conversational.
- Ask one or two questions at a time—never a long survey.
- Adapt your questions based on the user's previous answers.
- Use intuitive, lifestyle-oriented questions (not just specs).
- Discover necessary information and practical needs (zipcode, new/used, budget, size, usage).
- Discover emotional drivers (status, fun, safety, efficiency).
- DO NOT repeat questions already answered.

Conversational stages to cover:
1. Warm welcome / motivation: Why now? What's happening in their life?
2. Practical constraints: Location(zipcode), budget range, new vs used, body type preferences.
3. Use case & lifestyle: Daily driving? Family? Travel? Commute? Hobbies?
4. Emotional priorities: Safety, efficiency, performance, style, comfort.
5. Context: Location, climate, parking, EV charging, brand feelings.

Your task for each turn:
1. Respond naturally and empathetically to the user's message.
2. Ask 1-2 thoughtful follow-up questions that move the conversation forward.
3. If a stage has already been covered, move to the next relevant stage.
4. Review the conversation history to avoid repeating questions.

When to end the interview (set should_end=true):
- User explicitly asks to see vehicles ("show me", "let's see", "what do you have", "recommendations", etc.)
- You have enough information to make good recommendations
- User seems impatient or ready to move forward

Think like a real human salesperson who builds trust before suggesting options.

Output format:
- response: Your conversational response to the user (IMPORTANT: If setting should_end=true, leave response EMPTY - the system will generate the vehicle recommendation)
- should_end: true if interview should end, false to continue
"""


def should_end_interview(state: VehicleSearchState) -> bool:
    """
    Check if interview should end based on LLM's decision or max turns.

    Returns True if:
    - LLM set should_end=True in last response OR
    - Hit max conversation exchanges (safety limit)
    """
    # Check if LLM decided to end
    if state.get("_interview_should_end", False):
        return True

    # Safety limit - max turns
    max_questions = int(os.getenv("MAX_EXPLORATION_QUESTIONS", "8"))
    conversation = state.get("conversation_history", [])
    turn_count = len([msg for msg in conversation if msg.__class__.__name__ == 'HumanMessage'])

    if turn_count >= max_questions:
        logger.info(f"Hit max turns ({max_questions}), ending interview")
        return True

    return False


def interview_node(state: VehicleSearchState) -> VehicleSearchState:
    """
    Interview node that asks questions like a salesperson.

    Uses structured output with conversation history as user input for optimal prompt caching.

    Args:
        state: Current state

    Returns:
        Updated state with AI response and should_end flag
    """
    user_input = get_latest_user_message(state)

    if not user_input:
        # First turn - greeting
        state["ai_response"] = "Hi there! Welcome. What brings you in today? Are you looking to replace a current vehicle or is this your first car?"
        state["_interview_should_end"] = False
        return state

    # Create LLM with structured output
    llm = ChatOpenAI(model="gpt-4o", temperature=0.7)
    structured_llm = llm.with_structured_output(InterviewResponse)

    messages = [SystemMessage(content=INTERVIEW_SYSTEM_PROMPT)]
    messages.extend(state["conversation_history"])

    # Get structured response
    response: InterviewResponse = structured_llm.invoke(messages)

    # Store decision
    state["_interview_should_end"] = response.should_end

    if response.should_end:
        logger.info("LLM decided to end interview")
        state["ai_response"] = ""
    else:
        # Normal conversation - set the response
        state["ai_response"] = response.response

    return state


def get_recommendations_with_explanation(state: VehicleSearchState) -> VehicleSearchState:
    """
    Use ReAct agent with web search to get vehicle recommendation and reasoning.

    Flow:
    1. Always use ReAct agent with web search
    2. If make/model specified: agent uses them and provides reasoning
    3. If make/model NOT specified: agent discovers them via research
    4. Listing search

    Args:
        state: Current state with filters and preferences

    Returns:
        Updated state with make/model and personalized reasoning
    """
    filters = state['explicit_filters']
    preferences = state['implicit_preferences']

    # Check if make/model are specified
    has_make = filters.get('make') is not None and filters.get('make') != ''
    has_model = filters.get('model') is not None and filters.get('model') != ''

    # Build prompt for ReAct agent
    if has_make and has_model:
        # User specified make/model - get reasoning
        logger.info(f"Make/model specified: {filters.get('make')} {filters.get('model')}. Using web search for reasoning...")
        web_search_prompt = f"""
You are a vehicle research specialist. The customer has chosen a specific vehicle: {filters.get('make')} {filters.get('model')}.

CUSTOMER PREFERENCES:
{json.dumps(preferences, indent=2)}

CUSTOMER FILTERS:
{json.dumps(filters, indent=2)}

YOUR TASK:
1. Use the tavily_search tool to research why the {filters.get('make')} {filters.get('model')} is a great choice
2. Search for reviews, expert opinions, and how it matches their priorities and lifestyle
3. Analyze the search results carefully
4. Provide personalized reasoning

IMPORTANT: You MUST use the exact make and model the customer specified. Output in this EXACT JSON format:
{{
  "make": "{filters.get('make')}",
  "model": "{filters.get('model')}",
  "reasoning": "[a brief paragraph of specific reasons based on research that match customer needs]"
}}

The reasoning should be friendly, persuasive, and conversational - imagine you're a car salesperson explaining why THIS SPECIFIC vehicle is perfect for the customer based on research.
"""
    else:
        # Discover make/model via web search
        logger.info("Make/model not specified. Using web search to discover best vehicle...")
        web_search_prompt = f"""
You are a vehicle research specialist. The customer needs ONE specific vehicle recommendation.

CUSTOMER PREFERENCES:
{json.dumps(preferences, indent=2)}

CUSTOMER FILTERS:
{json.dumps(filters, indent=2)}

YOUR TASK:
1. Use the tavily_search tool to research the best vehicle matching these criteria
2. Search for current expert recommendations based on their priorities, lifestyle, and requirements
3. Analyze the search results carefully
4. Recommend ONE specific vehicle (single make and model, be very specific, do NOT contain hyphens)
5. Output your final recommendation as JSON

Think step by step:
- What are the customer's top priorities?
- What vehicle type matches their lifestyle and needs?
- Use web search to find the #1 expert recommendation
- Pick the SINGLE BEST vehicle that matches their criteria

IMPORTANT: After your research, output your final recommendation in this EXACT JSON format:
{{
  "make": "Toyota",
  "model": "RAV4",
  "reasoning": "Based on research, the Toyota RAV4 excels in [specific reasons matching customer needs]"
}}

The reasoning should be friendly, persuasive, and conversational - imagine you're a car salesperson explaining why THIS SPECIFIC vehicle is perfect for the customer.
"""

    # Create ReAct agent with Tavily search tool
    tavily_search_tool = TavilySearch(max_results=5)
    tools = [tavily_search_tool]
    llm = ChatOpenAI(model="gpt-4o", temperature=0.2)

    # Create agent
    agent = create_react_agent(llm, tools)

    logger.info("Running ReAct agent...")

    # Run agent
    result = agent.invoke({"messages": [HumanMessage(content=web_search_prompt)]})

    # Get final response from agent
    final_message = result['messages'][-1].content
    logger.info(f"Agent research complete")

    # Parse JSON directly from agent's response
    try:
        # Try to find JSON in the response
        content = final_message.strip()

        # Strip markdown if present
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()

        # Find JSON object in the content (in case there's extra text)
        json_match = re.search(r'\{[^{}]*"make"[^{}]*"model"[^{}]*"reasoning"[^{}]*\}', content, re.DOTALL)
        if json_match:
            content = json_match.group(0)

        # Parse JSON
        recommendation_dict = json.loads(content)

        # Validate with Pydantic
        recommendation = MakeModelRecommendation(**recommendation_dict)

    except (json.JSONDecodeError, ValueError) as e:
        logger.error(f"Failed to parse JSON from agent response: {e}")
        logger.error(f"Agent response: {final_message}")
        raise ValueError(f"Could not parse vehicle recommendation from web search. Agent response: {final_message[:200]}")

    # Populate filters with recommendation
    state['explicit_filters']['make'] = recommendation.make
    state['explicit_filters']['model'] = recommendation.model

    # Store reasoning for AI response
    reasoning = recommendation.reasoning

    logger.info(f"Recommendation - Make: {recommendation.make}, Model: {recommendation.model}")

    # Search for vehicle listings with current filters (using existing recommendation component)
    state = update_recommendation_list(state)

    # Set AI response with reasoning
    state['ai_response'] = reasoning

    return state


def make_initial_recommendation(state: VehicleSearchState) -> VehicleSearchState:
    """
    Called once at the end of interview to:
    1. Parse entire interview conversation for filters/preferences using structured output
    2. Generate initial vehicle recommendations with explanation
    3. Mark interview as complete

    Args:
        state: Current state

    Returns:
        Updated state with interviewed=True and initial recommendations
    """
    logger.info("Interview complete! Extracting preferences and generating recommendations...")

    # Step 1: Extract filters/preferences using structured output
    # Get entire interview conversation
    interview_conversation = "\n".join([
        f"{'Customer' if msg.__class__.__name__ == 'HumanMessage' else 'Salesperson'}: {msg.content}"
        for msg in state.get("conversation_history", [])
    ])

    # Create LLM with structured output
    llm = ChatOpenAI(model="gpt-4o", temperature=0)
    structured_llm = llm.with_structured_output(ExtractionResult)

    extraction_system_prompt = f"""
Analyze this car dealership conversation and extract comprehensive vehicle search criteria.

Extract ALL explicit filters and implicit preferences from this conversation.

Explicit filters are clear, stated requirements:
- Make, model, year, price range, mileage, body style, transmission, colors, features, location, etc.
- Use comma-separated for multiple options: "Toyota,Honda"
- Use ranges for year/price/miles: "2018-2020", "20000-30000"

Implicit preferences are inferred needs and priorities:
- priorities: List of what matters most (safety, fuel efficiency, reliability, performance, etc.)
- lifestyle: Family-oriented, outdoorsy, urban commuter, etc.
- budget_sensitivity: budget-conscious, moderate, luxury-focused
- usage_patterns: Daily commute, weekend trips, family road trips, etc.
- concerns: List of concerns (maintenance costs, resale value, insurance, etc.)
- notes: Any other important context

Be comprehensive - extract EVERYTHING mentioned or clearly implied.
"""

    extraction_prompt = f"""
CONVERSATION:
{interview_conversation}
"""
    messages = [
        SystemMessage(content=extraction_system_prompt),
        HumanMessage(content=extraction_prompt)
    ]

    result: ExtractionResult = structured_llm.invoke(messages)

    state["explicit_filters"] = {**state["explicit_filters"], **result.explicit_filters.model_dump(exclude_none=True)}
    state["implicit_preferences"] = {**state["implicit_preferences"], **result.implicit_preferences.model_dump(exclude_none=True)}

    logger.info(f"Extracted filters: {state['explicit_filters']}")
    logger.info(f"Extracted preferences: {state['implicit_preferences']}")

    # Step 2: Get recommendations with explanation
    state = get_recommendations_with_explanation(state)

    # Step 3: Mark interview complete
    state["interviewed"] = True

    # Clean up temporary flag
    if "_interview_should_end" in state:
        del state["_interview_should_end"]

    return state


def decide_next_step(state: VehicleSearchState) -> str:
    """Router to decide if interview should continue or make recommendations."""
    if should_end_interview(state):
        return "make_recommendation"
    return END


# Create LangGraph StateGraph for interview workflow
def create_interview_graph():
    """Create the interview workflow graph."""
    workflow = StateGraph(VehicleSearchState)

    # Add nodes
    workflow.add_node("semantic_parser", semantic_parser_node)
    workflow.add_node("interview", interview_node)
    workflow.add_node("make_recommendation", make_initial_recommendation)

    # Add edges
    workflow.set_entry_point("semantic_parser")
    workflow.add_edge("semantic_parser", "interview")
    workflow.add_conditional_edges(
        "interview",
        decide_next_step,
        {
            "make_recommendation": "make_recommendation",
            END: END
        }
    )
    workflow.add_edge("make_recommendation", END)

    return workflow.compile()


# Create the compiled graph (singleton)
_interview_graph = None

def get_interview_graph():
    """Get or create the interview workflow graph."""
    global _interview_graph
    if _interview_graph is None:
        _interview_graph = create_interview_graph()
    return _interview_graph


def run_interview_workflow(user_input: str, state: VehicleSearchState) -> VehicleSearchState:
    """
    Main interview workflow entry point.

    Args:
        user_input: User's message
        state: Current state

    Returns:
        Updated state
    """
    graph = get_interview_graph()
    result = graph.invoke(state)
    return result
