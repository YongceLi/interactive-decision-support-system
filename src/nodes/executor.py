"""
Executor Node for Interactive Decision Support System.

This node executes the current task in the active plan using the tool registry.
"""

from typing import Dict, Any
from langchain_core.messages import AIMessage
from langchain_openai import ChatOpenAI

from ..core.state import AgentState
from ..tools.registry import ToolRegistry
from ..tools.vin_decode import VinDecodeTool
from ..tools.vehicle_listings import VehicleListingsTool
from ..tools.vehicle_photos import VehiclePhotosTool


class TaskExecutor:
    """Node responsible for executing planned tasks."""

    def __init__(self, model_name: str = "gpt-4o-mini"):
        self.tool_registry = ToolRegistry()
        self.llm = ChatOpenAI(model=model_name, temperature=0)
        self._register_tools()

    def _register_tools(self):
        """Register all available tools in the registry."""
        self.tool_registry.register_tool(VinDecodeTool())
        self.tool_registry.register_tool(VehicleListingsTool())
        self.tool_registry.register_tool(VehiclePhotosTool())

    def __call__(self, state: AgentState) -> Dict[str, Any]:
        """
        Execute the current task in the active plan.

        Args:
            state: Current agent state

        Returns:
            Updated state dictionary with execution results
        """
        active_plan = state.get("active_plan", [])
        next_task_index = state.get("next_task_index", 0)

        # Check if there are tasks to execute
        if not active_plan or next_task_index >= len(active_plan):
            return self._update_state_no_tasks(state)

        # Get current task
        current_task = active_plan[next_task_index]
        action_type, tool_name, description = current_task

        # Execute based on action type
        if action_type == "ask_user":
            return self._execute_ask_user(state, description)
        elif action_type == "call_tool":
            return self._execute_call_tool(state, tool_name, description)
        elif action_type == "synthesize":
            return self._execute_synthesize(state, description)
        else:
            return self._handle_unknown_action(state, action_type)

    def _execute_ask_user(self, state: AgentState, description: str) -> Dict[str, Any]:
        """Execute ask_user action type."""
        current_goal = state.get("current_goal", "")

        # Generate a natural question using LLM
        question = self._generate_user_question(description, current_goal, state)

        new_state = dict(state)

        # Add AI message with the generated question
        ai_message = AIMessage(content=question)
        new_state["messages"].append(ai_message)

        # Set flag that we need user input and DO NOT advance task index
        # The task index will advance only when user provides input and we re-enter the workflow
        new_state["needs_user_input"] = True

        return new_state

    def _generate_user_question(self, description: str, current_goal: str, state: AgentState) -> str:
        """Generate a natural question for the user based on the task description."""

        # Get context from conversation
        messages = state.get("messages", [])
        recent_context = ""
        if messages:
            # Get last few messages for context
            recent_messages = messages[-3:]
            recent_context = "\n".join([
                f"{'User' if msg.__class__.__name__ == 'HumanMessage' else 'Assistant'}: {msg.content}"
                for msg in recent_messages
            ])

        prompt = f"""
        You are an automotive decision support assistant. You need to ask the user for specific information.

        Current Goal: "{current_goal}"

        Task Description: "{description}"

        Recent Conversation Context:
        {recent_context}

        Generate a natural, conversational question to ask the user for this information. The question should:
        - Be friendly and helpful
        - Be specific about what information you need
        - Reference the current goal when relevant
        - Not repeat information already provided by the user

        Respond with ONLY the question, no extra text.

        Examples:
        - Task: "Ask user for their location/zip code" → "What's your zip code or location? I'll use this to find vehicles in your area."
        - Task: "Ask user for budget range" → "What's your budget range for this vehicle?"
        - Task: "Ask user for preferred fuel type" → "Do you have a preference for fuel type - gasoline, hybrid, or electric?"
        - ...
        """

        try:
            response = self.llm.invoke(prompt)
            return response.content.strip()
        except Exception as e:
            # Fallback to a simple question format
            return f"Could you please provide: {description.lower()}?"

    def _execute_call_tool(self, state: AgentState, tool_name: str, description: str) -> Dict[str, Any]:
        """Execute call_tool action type."""
        if not tool_name:
            return self._handle_error(state, "Tool name is empty for call_tool action")

        # Get parameters from state for tool execution
        tool_params = self._extract_tool_params(state, tool_name)

        try:
            # Execute the tool
            result = self.tool_registry.execute_tool(tool_name, **tool_params)

            # Update state with results
            return self._update_state_with_tool_result(state, result, description)

        except Exception as e:
            return self._handle_error(state, f"Error executing tool {tool_name}: {str(e)}")

    def _execute_synthesize(self, state: AgentState, description: str) -> Dict[str, Any]:
        """Execute synthesize action type."""
        # For synthesize, we create a summary/recommendation based on gathered information
        information = state.get("information", "")
        current_goal = state.get("current_goal", "")
        retrieved_data = state.get("retrieved_data", {})

        # Create synthesis message using all available data
        synthesis_content = self._create_synthesis(information, current_goal, description, retrieved_data)

        new_state = dict(state)
        ai_message = AIMessage(content=synthesis_content)
        new_state["messages"].append(ai_message)

        # Move to next task
        return self._advance_to_next_task(new_state)

    def _extract_tool_params(self, state: AgentState, tool_name: str) -> Dict[str, Any]:
        """Extract parameters for tool execution from information string using LLM."""
        current_goal = state.get("current_goal", "")
        information = state.get("information", "")

        # Use LLM to extract parameters from the information string
        prompt = f"""
        Extract parameters for the tool "{tool_name}" from the available information.

        Current Goal: "{current_goal}"
        Available Information: "{information or 'None'}"

        Tool Requirements:
        - vin_decode: Requires "vin" (17-character alphanumeric)
        - search_vehicle_listings: Optional params: make, model, year_min, year_max, price_min, price_max, mileage_max, zip_code, radius, body_style, fuel_type, transmission, limit
        - get_vehicle_photos: Requires "vin" (17-character alphanumeric)

        Extraction Rules:
        1. Look for vehicle makes: Jeep, Toyota, Honda, Ford, etc. → "make": "Jeep"
        2. Look for models: Wrangler, Prius, Accord, etc. → "model": "Wrangler"
        3. Look for budget amounts: "$40k", "40000", "under 40k" → "price_max": 40000
        4. Look for body styles: SUV, sedan, truck, convertible → "body_style": "suv"
        5. Look for fuel types: hybrid, electric, gas → "fuel_type": "hybrid"
        6. Look for year ranges: "2020-2023" → "year_min": 2020, "year_max": 2023
        7. Look for VINs: 17-character codes → "vin": "ABC123..."
        8. Look for locations: zip codes, cities, states → "zip_code": "90210"

        Convert units properly:
        - "40k", "$40k", "40000" → 40000
        - "2 door", "2-door" → may indicate convertible body style for some vehicles

        Return a Python dictionary with only the parameters you can confidently extract.
        Use proper data types (strings for text, integers for numbers).
        Return {{}} if nothing can be extracted.

        RESPOND WITH ONLY THE PYTHON DICTIONARY - NO OTHER TEXT.
        """

        try:
            response = self.llm.invoke(prompt)
            params_str = response.content.strip()

            # Try to parse as Python dictionary
            import ast
            params = ast.literal_eval(params_str)

            # Validate it's a dictionary
            if isinstance(params, dict):
                return params
            else:
                return {}

        except Exception as e:
            # If LLM extraction fails, return empty dict - don't use regex fallback
            print(f"LLM parameter extraction failed: {e}")
            return {}


    def _update_state_with_tool_result(self, state: AgentState, result, description: str) -> Dict[str, Any]:
        """Update state with tool execution results by storing full data in retrieved_data only."""
        new_state = dict(state)

        if result.success:
            # Store full tool result in retrieved_data ONLY
            current_step = state.get("next_task_index", 0)
            step_key = f"step_{current_step}: {description}"

            retrieved_data = dict(state.get("retrieved_data", {}))
            retrieved_data[step_key] = result.data
            new_state["retrieved_data"] = retrieved_data

            # DO NOT modify the information string - it should only contain user-provided information

            # Add AI message about successful execution
            ai_message = AIMessage(content=f"✅ Completed: {description}")
            new_state["messages"].append(ai_message)

            # DEBUG: Add detailed tool result information
            debug_info = self._format_tool_result_debug(result.data, description)
            if debug_info:
                debug_message = AIMessage(content=f"🔍 DEBUG - Tool Result:\n{debug_info}")
                new_state["messages"].append(debug_message)

        else:
            # Handle tool execution error
            error_msg = f"❌ Failed: {description} - {result.error}"
            ai_message = AIMessage(content=error_msg)
            new_state["messages"].append(ai_message)

        # Move to next task
        return self._advance_to_next_task(new_state)

    def _format_tool_result_debug(self, data: Dict[str, Any], description: str) -> str:
        """Format tool result data for debug output."""
        if not data:
            return "No data returned"

        debug_lines = []
        debug_lines.append(f"Task: {description}")

        # Format different types of tool results
        if "listings" in data:
            listings = data.get("listings", [])
            debug_lines.append(f"Found {len(listings)} vehicle listings:")

            for i, listing in enumerate(listings[:5], 1):  # Show first 5
                year = listing.get('year', 'N/A')
                make = listing.get('make', 'N/A')
                model = listing.get('model', 'N/A')
                price = listing.get('price', 'N/A')
                mileage = listing.get('mileage', 'N/A')
                location = listing.get('location', 'N/A')
                debug_lines.append(f"  {i}. {year} {make} {model} - ${price}, {mileage} miles, {location}")

            if len(listings) > 5:
                debug_lines.append(f"  ... and {len(listings) - 5} more")

        elif "vin" in data:
            # VIN decode result
            vin = data.get("vin", "N/A")
            make = data.get("make", "N/A")
            model = data.get("model", "N/A")
            year = data.get("year", "N/A")
            engine = data.get("engine", "N/A")
            body_style = data.get("body_style", "N/A")
            debug_lines.append(f"VIN: {vin}")
            debug_lines.append(f"Vehicle: {year} {make} {model}")
            debug_lines.append(f"Body Style: {body_style}")
            debug_lines.append(f"Engine: {engine}")

        elif "photos" in data:
            # Vehicle photos result
            photos = data.get("photos", [])
            debug_lines.append(f"Found {len(photos)} vehicle photos:")

            for i, photo in enumerate(photos[:3], 1):  # Show first 3
                angle = photo.get('angle', 'N/A')
                url = photo.get('url', 'N/A')
                debug_lines.append(f"  {i}. {angle} view: {url}")

            if len(photos) > 3:
                debug_lines.append(f"  ... and {len(photos) - 3} more")

        else:
            # Generic data formatting
            debug_lines.append("Raw data:")
            for key, value in data.items():
                if key != "raw_response":  # Skip raw response
                    if isinstance(value, (list, dict)):
                        debug_lines.append(f"  {key}: {type(value).__name__} with {len(value)} items")
                    else:
                        debug_lines.append(f"  {key}: {value}")

        return "\n".join(debug_lines)


    def _create_synthesis(self, information: str, goal: str, description: str, retrieved_data: Dict[str, Any]) -> str:
        """Create synthesis/recommendation from gathered information and all retrieved data."""

        # Format all retrieved data for the LLM
        detailed_data = ""
        if retrieved_data:
            detailed_data = "\n\nDetailed Retrieved Data:\n"
            for step_key, data in retrieved_data.items():
                detailed_data += f"\n{step_key}:\n"
                if isinstance(data, dict):
                    # Format dictionary data nicely
                    for key, value in data.items():
                        if key != "raw_response":  # Skip raw response to avoid clutter
                            if isinstance(value, list) and value:
                                detailed_data += f"  {key}: {len(value)} items\n"
                                if key == "listings" and len(value) > 0:
                                    # Show first few listings
                                    for i, listing in enumerate(value[:3], 1):
                                        year = listing.get('year', 'N/A')
                                        make = listing.get('make', 'N/A')
                                        model = listing.get('model', 'N/A')
                                        price = listing.get('price', 'N/A')
                                        mileage = listing.get('mileage', 'N/A')
                                        detailed_data += f"    {i}. {year} {make} {model} - ${price}, {mileage} miles\n"
                                elif key == "photos" and len(value) > 0:
                                    # Show photo info
                                    for i, photo in enumerate(value[:3], 1):
                                        angle = photo.get('angle', 'N/A')
                                        url = photo.get('url', 'N/A')
                                        detailed_data += f"    {i}. {angle} view: {url}\n"
                            else:
                                detailed_data += f"  {key}: {value}\n"
                else:
                    detailed_data += f"  {str(data)[:200]}...\n"

        prompt = f"""
        You are an automotive decision support assistant. Create a comprehensive and helpful summary and recommendations.

        User Goal: "{goal}"
        Summary Information: "{information or 'No specific information gathered yet'}"
        Task: "{description}"
        {detailed_data}

        Based on all the above information, provide a helpful synthesis that:
        - Summarizes what you've learned from all the retrieved data
        - Provides specific, actionable recommendations
        - References specific details from the data (prices, models, features, etc.)
        - Answers the user's original goal/question comprehensively
        - Is conversational and helpful
        - Uses the actual data retrieved to give concrete advice

        Make sure to use the detailed retrieved data to provide specific recommendations with actual vehicle details, pricing, and other relevant information.

        Keep it informative but conversational (3-6 sentences).
        """

        try:
            response = self.llm.invoke(prompt)
            return response.content.strip()
        except Exception as e:
            # Fallback synthesis
            if information:
                return f"📋 {description}\n\nBased on your request for {goal}, here's what I found: {information}"
            else:
                return f"📋 {description}\n\nI'm working on your request for {goal}."

    def _advance_to_next_task(self, state: AgentState) -> Dict[str, Any]:
        """Move to the next task in the plan."""
        new_state = dict(state)

        current_index = state.get("next_task_index", 0)
        new_state["next_task_index"] = current_index + 1
        new_state["needs_user_input"] = False  # Reset flag

        return new_state

    def _update_state_no_tasks(self, state: AgentState) -> Dict[str, Any]:
        """Handle case where there are no more tasks to execute."""
        new_state = dict(state)
        ai_message = AIMessage(content="✅ All planned tasks completed!")
        new_state["messages"].append(ai_message)
        return new_state

    def _handle_unknown_action(self, state: AgentState, action_type: str) -> Dict[str, Any]:
        """Handle unknown action types."""
        return self._handle_error(state, f"Unknown action type: {action_type}")

    def _handle_error(self, state: AgentState, error_message: str) -> Dict[str, Any]:
        """Handle execution errors."""
        new_state = dict(state)

        # Add error message
        ai_message = AIMessage(content=f"Error: {error_message}")
        new_state["messages"].append(ai_message)

        return new_state


# Create the node function for LangGraph
def executor_node(state: AgentState) -> AgentState:
    """LangGraph node function for task execution."""
    node = TaskExecutor()
    return node(state)