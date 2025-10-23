"""
Intent classification component for routing user queries to appropriate modes.

Classifies user intent into:
- buying: User wants to purchase a vehicle and needs guidance
- browsing: Casual exploration without commitment
- research: Analytical questions, comparisons, specific data queries
- general: Greetings, meta questions, off-topic
"""
from typing import List, Literal
from pydantic import BaseModel, Field
from langchain_core.messages import BaseMessage
from langchain_openai import ChatOpenAI
from idss_agent.logger import get_logger

logger = get_logger("intent_classifier")


class UserIntent(BaseModel):
    """User's classified intent with confidence and reasoning."""
    intent: Literal["buying", "browsing", "research", "general"] = Field(
        description="The user's primary intent"
    )
    confidence: float = Field(
        description="Confidence score between 0 and 1",
        ge=0.0,
        le=1.0
    )
    reasoning: str = Field(
        description="Brief explanation of why this intent was chosen"
    )


def classify_intent(conversation_history: List[BaseMessage]) -> UserIntent:
    """
    Classify user intent based on full conversation history.

    Uses GPT-4o-mini for fast, cheap classification with prompt caching.
    Full conversation history is sent to maximize cache hits.

    Args:
        conversation_history: Complete conversation between user and AI

    Returns:
        UserIntent with intent category, confidence, and reasoning
    """

    # Use GPT-4o-mini for fast, cheap classification
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

    # System prompt with intent definitions (cached)
    system_prompt = """You are an intent classifier for a vehicle shopping assistant.

Your task: Classify the user's current intent based on their latest message and conversation context.

Intent Definitions:

1. **buying**: User wants to purchase a vehicle and needs guidance through the process
   - Looking for recommendations and help finding a car
   - Asking for assistance with vehicle selection
   - Discussing budget, needs, preferences with purchase intent
   - Ready to make a purchase decision
   - Examples: "I need a family SUV", "Help me find a reliable car", "What should I buy?", "Looking for a sedan under $25k"

2. **browsing**: User wants to casually explore options without commitment
   - Just looking around to see what's available
   - Wants to see vehicles without buying pressure
   - Exploratory, non-committal questions
   - Not ready to commit to buying process
   - Examples: "Show me sports cars", "What EVs are out there?", "Browse luxury sedans", "Let me see some trucks"

3. **research**: User has specific analytical questions, wants deep comparisons or data
   - Comparing specific vehicles
   - Asking about safety ratings, specs, features, performance
   - Technical or data-driven questions
   - Deep-dive analysis queries
   - Examples: "Compare Honda CR-V vs Toyota RAV4", "What's the safety rating for Camry?", "MPG comparison of hybrids", "Which SUV has the best reliability?"

4. **general**: Greetings, unclear intent, off-topic, or system questions
   - Greetings: "Hello", "Hi there", "Good morning"
   - Meta questions: "What can you do?", "How does this work?", "Help"
   - Thanks/acknowledgments: "Thanks", "Great", "Okay"
   - Off-topic: Unrelated to vehicles
   - Unclear: Not enough context to determine intent
   - Examples: "Hello", "Thanks for the info", "What features do you have?", "How do I use this?"

Classification Guidelines:
- Focus on the user's LATEST message while considering conversation context
- If user is mid-conversation in buying mode (being interviewed), follow-up answers are still "buying"
- If user was buying and asks a specific technical question, it's likely still "buying" context (not research)
- If user has completed buying interview and asks "show me more", that's likely "browsing" (not buying again)
- Research intent is for users who want information WITHOUT buying commitment yet
- If unclear or ambiguous, default to 'general'
- Confidence should reflect certainty (0.0 = not sure at all, 1.0 = very confident)
- Consider conversation flow: follow-up questions usually maintain the same intent

Return JSON with: intent, confidence, reasoning"""

    # Build messages with full conversation history (optimized for caching)
    messages = [
        {"role": "system", "content": system_prompt}
    ]

    # Add full conversation history (cached incrementally)
    for msg in conversation_history:
        role = "user" if msg.type == "human" else "assistant"
        messages.append({"role": role, "content": msg.content})

    # Get structured output
    structured_llm = llm.with_structured_output(UserIntent)

    try:
        result = structured_llm.invoke(messages)
        logger.info(f"Intent classified: {result.intent} (confidence: {result.confidence:.2f}) - {result.reasoning}")
        return result
    except Exception as e:
        logger.error(f"Error classifying intent: {e}")
        # Fallback to general intent
        return UserIntent(
            intent="general",
            confidence=0.5,
            reasoning=f"Error during classification: {str(e)}"
        )
