"""
Goal Understanding Node for Interactive Decision Support System.

This node analyzes every user input to intelligently merge goals and update the state.
Simplified version focused on basic goal merging without complex JSON parsing.
"""

from typing import Dict, Any
from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI

from ..core.state import AgentState


class GoalUnderstanding:
    """Node responsible for understanding user goals and merging them intelligently."""

    def __init__(self, model_name: str = "gpt-4o-mini"):
        self.llm = ChatOpenAI(model=model_name, temperature=0)

    def __call__(self, state: AgentState) -> Dict[str, Any]:
        """
        Process user input to merge with current goal.

        Args:
            state: Current agent state

        Returns:
            Updated state dictionary
        """
        # Get the latest user message
        if not state["messages"]:
            return state

        latest_message = state["messages"][-1]
        if not isinstance(latest_message, HumanMessage):
            return state

        user_input = latest_message.content
        current_goal = state.get("current_goal")
        current_information = state.get("information")

        # Analyze the user input to get merged goal and information
        merged_goal = self._merge_goals(user_input, current_goal)
        merged_information = self._merge_information(user_input, current_information)

        # Update state with the new goal and information
        updated_state = self._update_state(state, merged_goal, merged_information)

        return updated_state

    def _merge_goals(self, user_input: str, current_goal: str = None) -> str:
        """Merge user input with current goal to create updated goal string."""

        prompt = f"""
        You are helping with automotive decision support. Your task is to intelligently merge the current goal with new user input.

        Current Goal: "{current_goal or 'None'}"
        User Input: "{user_input}"

        Rules:
        - If current goal is "None" or empty: Create new goal from user input
        - If user input adds NEW information: Merge it with current goal to create a more complete goal
        - If user input is just confirmation (yes, ok, sounds good): Keep current goal unchanged
        - If user input represents a COMPLETELY different request: Replace with new goal
        - The goal should be a natural, readable sentence

        Examples:
        - Current: "I want to find a hybrid SUV" + Input: "My budget is under $40k" → "The user wants to find a hybrid SUV under $40k"
        - Current: "I want to buy a sedan" + Input: "I want an SUV instead" → "The user wants to find an SUV"

        Respond with ONLY the merged goal as a single sentence. No extra text, no explanations.
        """

        try:
            response = self.llm.invoke(prompt)
            merged_goal = response.content.strip()
            return merged_goal
        except Exception as e:
            # Simple fallback: just combine them
            if not current_goal or current_goal == "None":
                return user_input.strip()
            else:
                return f"{current_goal} {user_input.strip()}"

    def _merge_information(self, user_input: str, current_information: str = None) -> str:
        """Merge user input with current information to create updated information string."""

        prompt = f"""
        You are helping with automotive decision support. Your task is to merge new user information with existing information.

        Current Information: "{current_information or 'None'}"
        New User Input: "{user_input}"

        Rules:
        - Extract any factual information from the user input (budget, location, preferences, constraints, etc.)
        - If current information is "None" or empty: Create new information from user input
        - If user input contains NEW factual information: Add it to current information
        - If user input is just conversation (yes, ok, thanks): Keep current information unchanged
        - If user input contradicts existing information: Update with the new information
        - Keep information concise but comprehensive
        - Format as natural sentences, not bullet points

        Examples:
        - Current: "None" + Input: "I want a hybrid SUV under $40k" → "Budget: under $40k, Vehicle type: hybrid SUV"
        - Current: "Budget: under $40k, Vehicle type: hybrid SUV" + Input: "I live in California" → "Budget: under $40k, Vehicle type: hybrid SUV, Location: California"
        - Current: "Budget: under $40k" + Input: "Actually, my budget is $50k" → "Budget: $50k"

        Respond with ONLY the merged information. No extra text, no explanations.
        """

        try:
            response = self.llm.invoke(prompt)
            merged_info = response.content.strip()
            return merged_info if merged_info != "None" else None
        except Exception as e:
            # Simple fallback: just combine them
            if not current_information:
                return user_input.strip()
            else:
                return f"{current_information}. {user_input.strip()}"

    def _update_state(self, state: AgentState, merged_goal: str, merged_information: str) -> Dict[str, Any]:
        """Update the agent state with the new merged goal and information."""

        # Create a copy of the state to modify
        new_state = dict(state)

        # Store current values as previous before updating
        current_goal = state.get("current_goal")
        current_information = state.get("information")
        new_state["previous_goal"] = current_goal
        new_state["previous_information"] = current_information

        # Update current goal and information
        new_state["current_goal"] = merged_goal
        new_state["information"] = merged_information

        # If we were waiting for user input, advance the task index now that user responded
        if state.get("needs_user_input", False):
            current_index = state.get("next_task_index", 0)
            new_state["next_task_index"] = current_index + 1
            new_state["needs_user_input"] = False

        return new_state


# Create the node function for LangGraph
def goal_understanding_node(state: AgentState) -> AgentState:
    """LangGraph node function for goal understanding."""
    node = GoalUnderstanding()
    return node(state)