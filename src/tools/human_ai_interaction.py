"""Human and AI interaction tools for the agent."""

from functools import lru_cache
from typing import Optional

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI


PRESENT_TO_HUMAN_SYSTEM = """
You are the presentation layer for an automotive purchase decision support agent.
You have access to the plan of the agent, the current subtask and the information retrieved from useful tool calls.
Summarize the provided context and communicate with the user in a clear, friendly tone.
Avoid repeating the raw tool output verbatim; focus on clarity and usefulness.
""".strip()

PRESENT_TO_HUMAN_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", PRESENT_TO_HUMAN_SYSTEM),
        (
            "human",
            "Here is the latest planning/execution context to relay to the user:\n{context}",
        ),
    ]
)


@lru_cache(maxsize=1)
def _present_to_human_llm(model: Optional[str] = None, temperature: float = 0.3) -> ChatOpenAI:
    """Return a cached LLM instance for presentation responses."""

    llm_kwargs = {"model": model or "gpt-4o-mini", "temperature": temperature}
    return ChatOpenAI(**llm_kwargs)


@tool
def ask_human(question: str) -> str:
    """Ask a question to the human user and wait for their response.

    Use this tool when you need information from the user that you don't have.
    For example: their preferences, budget, location, specific requirements, etc.

    Args:
        question: The question to ask the user

    Returns:
        The user's response
    """
    # Print the question and get input directly
    # This is a simple synchronous approach that works with the plan-execute pattern
    print(f"\nAgent: {question}\n")
    user_response = input("You: ").strip()

    # Handle exit/quit commands
    if user_response.lower() in ["exit", "quit", "/quit"]:
        print("\n[cyan]Goodbye! 👋[/cyan]\n")
        import sys
        sys.exit(0)

    # Signal that user wants to end this line of questioning
    if not user_response or user_response.lower() in ["no", "no thanks", "i'm good", "done"]:
        return "No, I don't need additional information. Thank you."

    return user_response


@tool
def present_to_human(context: str, *, model: Optional[str] = None) -> str:
    """Summarize the latest progress and present it to the user.

    Use this tool when you have completed a significant task or gathered important
    information that should be shared with the user. This creates a polished,
    user-friendly summary of your findings.

    Args:
        context: A textual description of the current plan step, tool outputs, and
            any other state for contextual knowledge.
        model: Optional override for the OpenAI chat model used to synthesize the
            response.

    Returns:
        Confirmation that the information was presented to the user.
    """

    if not context or not context.strip():
        raise ValueError("present_to_human requires non-empty context")

    llm = _present_to_human_llm(model)
    messages = PRESENT_TO_HUMAN_PROMPT.format_prompt(context=context).to_messages()
    response = llm.invoke(messages)
    presentation = getattr(response, 'content', str(response))

    # Display the presentation
    print(f"📊 Agent Update:")
    print(f"\n{presentation}\n")

    return f"Successfully presented information to user: {presentation[:100]}..."
