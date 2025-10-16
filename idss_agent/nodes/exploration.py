"""
Exploration node that acts like a real dealership salesperson.

This node asks human-like questions about use cases, lifestyle, current situation,
and builds up both filters and insights before making recommendations.
"""
import os
import json
from typing import Dict, Any, List
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from idss_agent.state import VehicleSearchState, get_latest_user_message


# Exploration salesperson prompt
EXPLORATION_PROMPT = """
You are a friendly and knowledgeable car salesperson. Your goal is to understand the customer's needs through natural conversation before showing them vehicles.

Act like a real human salesperson would - ask about their life, their needs, their current situation, and what they're looking for. Don't just ask about hard specs (like "what make/model?"), but explore their USE CASES and LIFESTYLE.

**IMPORTANT: You can ask at most {max_questions} questions total. You've asked {questions_count} so far. Make each question count!**

Current conversation context:
{conversation_history}

Current insights gathered:
{exploration_insights}

Questions you've already asked about:
{questions_asked}

User's latest message:
{user_message}

Explicit filters we have so far:
{explicit_filters}

Implicit preferences we've inferred:
{implicit_preferences}

Your task:
1. Respond naturally to what the user just said
2. Extract any insights about their use cases, lifestyle, or situation
3. Ask 1-2 follow-up questions to learn more (don't ask about topics you've already covered)
4. If the user explicitly asks to see recommendations or vehicles, acknowledge and prepare to show them
5. **If you're close to the question limit ({questions_count}/{max_questions}), prioritize the most important missing information**

Output JSON format:
{{
  "response": "Your conversational response with 1-2 questions",
  "insights": {{
    "use_cases": ["daily commute", "family trips"],  // how they'll use the vehicle
    "current_situation": "Replacing 10-year-old sedan, needs more space",
    "lifestyle_notes": "Family of 4, active lifestyle, weekend camping trips",
    "pain_points": ["current car too small", "bad fuel economy"],
    "must_haves": ["good safety ratings", "cargo space"],
    "nice_to_haves": ["sunroof", "navigation"]
  }},
  "questions_asked": ["use_cases", "family_situation"]  // topics you asked about this turn
}}

Guidelines:
- Be warm and conversational, like a real salesperson
- Ask open-ended questions to get the user talking
- Don't ask about topics already covered (check questions_asked)
- Extract insights even from brief responses (e.g., "I have kids" → family_oriented lifestyle)
- If user gives explicit filters (make, model, price), acknowledge them but keep exploring their needs
- If user says "show me cars" or similar, acknowledge and say you'll pull up some options

Output ONLY valid JSON, no other text.
"""


# Readiness evaluation prompt
READINESS_EVALUATION_PROMPT = """
You are an experienced car dealership sales manager evaluating whether your salesperson has gathered enough information to make good vehicle recommendations.

Review the conversation between the salesperson and customer, and decide if the salesperson knows enough to confidently show the customer vehicles that match their needs.

**IMPORTANT: Be CONSERVATIVE. A real salesperson would have 5-7 minutes of conversation (at least 4-5 exchanges) before pulling up vehicles.**

A good salesperson should understand:
1. **Budget/Price Range** - Specific range, not just "not expensive"
2. **Use Case** - Detailed understanding (daily commute distance? how many passengers regularly? what kind of trips?)
3. **Lifestyle Context** - Family size, kids' ages, pets, hobbies, living situation (city/suburban/rural)
4. **Key Priorities** - At least 2-3 specific priorities ranked
5. **Current Situation** - What do they drive now? What do they like/dislike about it?
6. **Deal-breakers** - What must they have? What are they avoiding?

**Minimum conversation depth required:**
- At least 3-4 back-and-forth exchanges
- At least 3 different topic areas covered (budget, use case, priorities, current vehicle, lifestyle)
- User has given thoughtful, detailed responses (not just one-word answers)

**When to proceed immediately:**
- User explicitly says "show me cars", "I want to see what you have", "let's look at some options"
- User gives very detailed initial requirements with make/model/budget/location all specified

Conversation so far:
{conversation_history}

Insights gathered:
{exploration_insights}

Explicit filters:
{explicit_filters}

Implicit preferences:
{implicit_preferences}

Questions asked:
{questions_asked}

User's latest message:
{user_message}

Evaluate and respond in JSON:
{{
  "ready_to_recommend": false,  // true ONLY if criteria above met
  "confidence": 35,  // 0-100, how confident are you in making recommendations
  "reasoning": "We only have budget and basic use case. Need to understand their current situation, specific priorities, and lifestyle better. Only 2 exchanges so far - too early.",
  "missing_info": ["Current vehicle situation", "Specific priorities beyond budget", "Family situation", "Daily commute details"],
  "recommendation": "explore_more"  // "proceed" ONLY if ready, otherwise "explore_more"
}}

**BE STRICT:**
- 1-2 exchanges = NEVER ready (always explore_more)
- 3 exchanges = Ready ONLY if user explicitly asks to see vehicles
- 4-5 exchanges = Ready if we have budget + 2-3 detailed insights
- 6+ exchanges = Can be ready if we have comprehensive understanding

Output ONLY valid JSON, no other text.
"""


def exploration_node(state: VehicleSearchState) -> VehicleSearchState:
    """
    Exploration node that asks salesperson-style questions.

    This node:
    1. Asks human-like questions about use cases and lifestyle
    2. Extracts insights from user responses
    3. Builds up both filters and understanding
    4. Determines when enough info has been gathered

    Args:
        state: Current vehicle search state

    Returns:
        Updated state with exploration insights and response
    """
    user_input = get_latest_user_message(state)

    if not user_input:
        return state

    llm = ChatOpenAI(model="gpt-4o", temperature=0.7)  # Higher temp for more natural conversation

    # Build conversation history
    history_context = "\n".join([
        f"{'Customer' if msg.__class__.__name__ == 'HumanMessage' else 'Salesperson'}: {msg.content}"
        for msg in state.get("conversation_history", [])[-8:]  # Last 8 messages
    ])

    # Get max questions from environment
    max_questions = int(os.getenv("MAX_EXPLORATION_QUESTIONS", "6"))
    questions_count = len(state.get("exploration_questions_asked", []))

    # Format the prompt
    prompt_content = EXPLORATION_PROMPT.format(
        conversation_history=history_context,
        exploration_insights=json.dumps(state.get("exploration_insights", {}), indent=2),
        questions_asked=state.get("exploration_questions_asked", []),
        user_message=user_input,
        explicit_filters=json.dumps(state.get("explicit_filters", {}), indent=2),
        implicit_preferences=json.dumps(state.get("implicit_preferences", {}), indent=2),
        max_questions=max_questions,
        questions_count=questions_count
    )

    messages = [
        SystemMessage(content=prompt_content),
        HumanMessage(content="Generate your response as JSON.")
    ]

    response = llm.invoke(messages)

    try:
        # Parse JSON response
        content = response.content.strip()
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()

        parsed = json.loads(content)

        # Update state with exploration data
        state["ai_response"] = parsed.get("response", "")

        # Merge insights
        current_insights = state.get("exploration_insights", {})
        new_insights = parsed.get("insights", {})
        merged_insights = {**current_insights, **new_insights}
        state["exploration_insights"] = merged_insights

        # Add new questions to the list
        new_questions = parsed.get("questions_asked", [])
        current_questions = state.get("exploration_questions_asked", [])
        state["exploration_questions_asked"] = list(set(current_questions + new_questions))

    except json.JSONDecodeError as e:
        print(f"Warning: Failed to parse exploration response: {e}")
        print(f"Response: {response.content}")
        # Fallback response
        state["ai_response"] = "I'd love to help you find the perfect vehicle! Can you tell me a bit about what you're looking for?"

    return state


def evaluate_readiness(state: VehicleSearchState) -> Dict[str, Any]:
    """
    Use an LLM to evaluate if we have enough information to make recommendations.

    This simulates an experienced sales manager reviewing the conversation
    to decide if the salesperson should move to showing vehicles.

    Args:
        state: Current vehicle search state

    Returns:
        Dict with ready_to_recommend (bool), confidence (int), reasoning (str), recommendation (str)
    """
    user_input = get_latest_user_message(state)

    llm = ChatOpenAI(model="gpt-4o", temperature=0)  # Low temp for consistent evaluation

    # Build conversation history
    history_context = "\n".join([
        f"{'Customer' if msg.__class__.__name__ == 'HumanMessage' else 'Salesperson'}: {msg.content}"
        for msg in state.get("conversation_history", [])
    ])

    # Format the evaluation prompt
    prompt_content = READINESS_EVALUATION_PROMPT.format(
        conversation_history=history_context,
        exploration_insights=json.dumps(state.get("exploration_insights", {}), indent=2),
        explicit_filters=json.dumps(state.get("explicit_filters", {}), indent=2),
        implicit_preferences=json.dumps(state.get("implicit_preferences", {}), indent=2),
        questions_asked=state.get("exploration_questions_asked", []),
        user_message=user_input or ""
    )

    messages = [
        SystemMessage(content=prompt_content),
        HumanMessage(content="Evaluate the readiness and respond in JSON format.")
    ]

    response = llm.invoke(messages)

    try:
        # Parse JSON response
        content = response.content.strip()
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()

        evaluation = json.loads(content)
        return evaluation

    except json.JSONDecodeError as e:
        print(f"Warning: Failed to parse readiness evaluation: {e}")
        print(f"Response: {response.content}")
        # Conservative fallback - keep exploring
        return {
            "ready_to_recommend": False,
            "confidence": 30,
            "reasoning": "Unable to evaluate, continuing exploration",
            "missing_info": [],
            "recommendation": "explore_more"
        }
