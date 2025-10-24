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
from idss_agent.config import get_config
from idss_agent.prompt_loader import render_prompt

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
    # Get configuration
    config = get_config()
    model_config = config.get_model_config('intent_classifier')

    # Create LLM with config parameters
    llm = ChatOpenAI(
        model=model_config['name'],
        temperature=model_config['temperature'],
        max_tokens=model_config.get('max_tokens')
    )

    # Load system prompt from template
    system_prompt = render_prompt('intent_classifier.j2')

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
