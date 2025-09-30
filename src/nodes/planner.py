"""
Dynamic Planner Node for Interactive Decision Support System.

This node creates and adjusts plans based on goal changes while respecting
completed work and maintaining the next task pointer.
"""

from typing import Dict, Any, List
from langchain_openai import ChatOpenAI

from ..core.state import AgentState


class DynamicPlanner:
    """Node responsible for creating and adjusting execution plans."""

    def __init__(self, model_name: str = "gpt-4o-mini"):
        self.llm = ChatOpenAI(model=model_name, temperature=0)

    def __call__(self, state: AgentState) -> Dict[str, Any]:
        """
        Create or adjust the execution plan based on goal changes.

        Args:
            state: Current agent state

        Returns:
            Updated state dictionary with new/adjusted plan
        """
        current_goal = state.get("current_goal")
        previous_goal = state.get("previous_goal")
        current_information = state.get("information")

        previous_plan = state.get("active_plan", [])
        next_task_index = state.get("next_task_index", 0)

        # Check if we need to replan due to no results
        retrieved_data = state.get("retrieved_data", {})
        should_replan = self._should_replan_for_no_results(retrieved_data, next_task_index)

        # Determine if this is first round, plan adjustment, or replanning
        if not previous_plan:
            # First round: Create new plan
            new_plan = self._create_initial_plan(current_goal, current_information)
            new_next_task_index = 0
        elif should_replan:
            # Replanning due to no results: Create new plan to gather more info
            new_plan = self._create_replan_for_no_results(current_goal, current_information, retrieved_data)
            new_next_task_index = next_task_index  # Continue from current position
        else:
            # Subsequent round: Adjust existing plan
            new_plan = self._adjust_plan(
                current_goal, previous_goal, previous_plan, next_task_index
            )
            new_next_task_index = next_task_index  # Keep the same pointer

        # Update state with new plan
        updated_state = self._update_state(state, new_plan, new_next_task_index)

        return updated_state

    def _create_initial_plan(self, current_goal: str, current_information: str = None) -> List[tuple[str, str, str]]:
        """Create a new plan from scratch for the current goal."""

        prompt = f"""
        You are creating an execution plan for automotive decision support.

        User Goal: "{current_goal}"

        Current Information: "{current_information}"

        Create a step-by-step plan to achieve this goal. Break it down into subtasks.

        Available action types (You should only choose from these):
        - "ask_user": Ask user for missing information ONLY. Do NOT ask for confirmation of information already provided.
        - "call_tool": Call an automotive API/tool
        - "synthesize": Generate final response/recommendation

        Available automotive tools you can reference:

        1. vin_decode
           - Purpose: Decode a VIN to get detailed vehicle specifications
           - REQUIRED: vin (17-character Vehicle Identification Number)
           - Use when: You have a specific VIN and need detailed vehicle specs

        2. search_vehicle_listings
           - Purpose: Find vehicles based on search criteria
           - OPTIONAL parameters: make, model, year_min, year_max, price_min, price_max, mileage_max, zip_code, radius, body_style, fuel_type, transmission, limit
           - Use when: You need to find vehicles matching user criteria
           - Note: Can work with ANY combination of parameters, no required parameters

        3. get_vehicle_photos
           - Purpose: Get photos for a specific vehicle
           - REQUIRED: vin (17-character Vehicle Identification Number)
           - OPTIONAL: angle, limit, resolution
           - Use when: You have a VIN and need to show vehicle photos

        Respond with ONLY a Python list of tuples in this exact format:
        [
            ("action_type", "tool_name" or "", "description"),
            ...
        ]

        IMPORTANT PLANNING RULES:
        - If the user has already provided information (make, model, budget, etc.), do NOT ask for it again
        - Only ask for truly missing information that is essential for the tools
        - Avoid confirmation questions like "confirm your budget" if they already stated it
        - For vin_decode and get_vehicle_photos: You MUST have a VIN to use these tools
        - For search_vehicle_listings: Can work with any criteria, no required parameters
        """

        try:
            response = self.llm.invoke(prompt)
            response_text = response.content.strip()

            # Try to parse as Python list using eval (safe for list of tuples)
            import ast
            tasks = ast.literal_eval(response_text)

            # Validate it's a list of tuples with 3 elements each
            if isinstance(tasks, list) and all(
                isinstance(task, tuple) and len(task) == 3 for task in tasks
            ):
                return tasks
            else:
                raise ValueError("Invalid format returned")

        except Exception as e:
            # Fallback: Create a simple default plan
            return []

    def _adjust_plan(self, current_goal: str, previous_goal: str,
                    previous_plan: List[tuple[str, str, str]], next_task_index: int) -> List[tuple[str, str, str]]:
        """Adjust existing plan based on goal changes."""

        # If goals are the same, no adjustment needed
        if current_goal == previous_goal:
            return previous_plan

        prompt = f"""
        You need to adjust an existing execution plan based on a goal change.

        Previous Goal: "{previous_goal}"
        Current Goal: "{current_goal}"

        Current Plan (tasks {next_task_index} onwards can be modified):
        """

        for i, (action_type, tool_name, description) in enumerate(previous_plan):
            if i >= next_task_index:
                prompt += f"{i}. {description} | {action_type} | {tool_name}\n"

        prompt += f"""

        ONLY generate NEW tasks for positions {next_task_index} onwards to replace the modifiable part of the plan.
        Adjust based on what changed from "{previous_goal}" to "{current_goal}".

        Respond with ONLY a Python list of tuples for the NEW tasks:
        [
            ("action_type", "tool_name", "description"),
            ("action_type", "tool_name", "description"),
            ...
        ]

        Available automotive tools you can reference:

        1. vin_decode
           - Purpose: Decode a VIN to get detailed vehicle specifications
           - REQUIRED: vin (17-character Vehicle Identification Number)
           - Use when: You have a specific VIN and need detailed vehicle specs

        2. search_vehicle_listings
           - Purpose: Find vehicles based on search criteria
           - OPTIONAL parameters: make, model, year_min, year_max, price_min, price_max, mileage_max, zip_code, radius, body_style, fuel_type, transmission, limit
           - Use when: You need to find vehicles matching user criteria
           - Note: Can work with ANY combination of parameters, no required parameters

        3. get_vehicle_photos
           - Purpose: Get photos for a specific vehicle
           - REQUIRED: vin (17-character Vehicle Identification Number)
           - OPTIONAL: angle, limit, resolution
           - Use when: You have a VIN and need to show vehicle photos

        IMPORTANT: Do NOT ask for confirmation of information already provided by the current goal.
        """

        try:
            response = self.llm.invoke(prompt)
            response_text = response.content.strip()

            # Try to parse as Python list using ast.literal_eval
            import ast
            new_tasks_for_adjustment = ast.literal_eval(response_text)

            # Validate it's a list of tuples with 3 elements each
            if isinstance(new_tasks_for_adjustment, list) and all(
                isinstance(task, tuple) and len(task) == 3 for task in new_tasks_for_adjustment
            ):
                # Combine: original plan up to next_task_index + adjusted remainder
                final_plan = previous_plan[:next_task_index] + new_tasks_for_adjustment
                return final_plan
            else:
                raise ValueError("Invalid format returned")

        except Exception as e:
            # Fallback: Keep existing plan unchanged
            return previous_plan

    def _update_state(self, state: AgentState, new_plan: List[tuple[str, str, str]],
                     next_task_index: int) -> Dict[str, Any]:
        """Update the agent state with the new plan."""

        # Create a copy of the state to modify
        new_state = dict(state)

        # Update plan and task index directly in state
        new_state["active_plan"] = new_plan
        new_state["next_task_index"] = next_task_index

        return new_state

    def _should_replan_for_no_results(self, retrieved_data: Dict[str, Any], next_task_index: int) -> bool:
        """Check if we should replan due to no results from recent tool execution."""
        if not retrieved_data:
            return False

        # Check the most recent tool execution for empty results
        latest_step_key = f"step_{next_task_index - 1}"
        for key, data in retrieved_data.items():
            if key.startswith(latest_step_key):
                if isinstance(data, dict):
                    listings = data.get("listings", [])
                    if isinstance(listings, list) and len(listings) == 0:
                        return True
        return False

    def _create_replan_for_no_results(self, current_goal: str, current_information: str, retrieved_data: Dict[str, Any]) -> List[tuple[str, str, str]]:
        """Create a new plan when previous search returned no results."""

        prompt = f"""
        You need to create a NEW plan because the previous vehicle search returned no results.

        User Goal: "{current_goal}"
        Current Information: "{current_information or 'Limited information'}"

        The previous search failed to find vehicles. This means we need to gather MORE information from the user to make a successful search.

        Create a new plan to gather more specific information and try again:

        Available action types:
        - "ask_user": Ask user for missing information
        - "call_tool": Call an automotive API/tool
        - "synthesize": Generate final response/recommendation

        Available tools:
        1. vin_decode (REQUIRES: vin) - Decode VIN for detailed specifications
        2. search_vehicle_listings (NO REQUIRED params) - Find vehicles by criteria
        3. get_vehicle_photos (REQUIRES: vin) - Get photos for specific vehicle

        IMPORTANT: Only ask for information that is NOT already provided in the current information.
        Look at what information we already have and only ask for what's missing.

        Common missing information that helps with vehicle searches:
        - Budget range (if not provided)
        - Location/zip code (usually missing and very important for search)
        - Year preferences (if not specified)
        - Mileage requirements
        - Any specific features needed

        Respond with ONLY a Python list of tuples:
        [
            ("ask_user", "", "Ask for location/zip code"),
            ("call_tool", "search_vehicle_listings", "Search with location and updated criteria"),
            ("synthesize", "", "Provide recommendations")
        ]
        """

        try:
            response = self.llm.invoke(prompt)
            response_text = response.content.strip()

            import ast
            tasks = ast.literal_eval(response_text)

            if isinstance(tasks, list) and all(
                isinstance(task, tuple) and len(task) == 3 for task in tasks
            ):
                return tasks
            else:
                raise ValueError("Invalid format returned")

        except Exception as e:
            # Fallback: Ask for location (most commonly missing) and try again
            return [
                ("ask_user", "", "Ask for location/zip code"),
                ("call_tool", "search_vehicle_listings", "Search with more specific criteria"),
                ("synthesize", "", "Provide recommendations")
            ]


# Create the node function for LangGraph
def planner_node(state: AgentState) -> AgentState:
    """LangGraph node function for dynamic planning."""
    node = DynamicPlanner()
    return node(state)