"""
LangGraph workflow definition for Interactive Decision Support System.

This module defines the IDSS LangGraph workflow. Currently implements
goal understanding with placeholders for future nodes (planner, executor, router).
"""

from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage

from .state import AgentState, create_initial_state
from ..nodes.goal_understanding import goal_understanding_node
from ..nodes.planner import planner_node
from ..nodes.executor import executor_node


def should_continue_execution(state: AgentState) -> str:
    """Router that determines whether to continue executing tasks or end."""
    active_plan = state.get("active_plan", [])
    next_task_index = state.get("next_task_index", 0)
    needs_user_input = state.get("needs_user_input", False)

    # If waiting for user input, end workflow (user will continue conversation)
    if needs_user_input:
        return END

    # If there are more tasks to execute, continue to executor
    if active_plan and next_task_index < len(active_plan):
        return "executor"

    # Otherwise, end the workflow
    return END


def should_replan_or_execute(state: AgentState) -> str:
    """Router after planning to determine if we should execute or replan based on results."""
    active_plan = state.get("active_plan", [])
    next_task_index = state.get("next_task_index", 0)
    retrieved_data = state.get("retrieved_data", {})

    # Check if we just completed a tool that returned no results
    if retrieved_data:
        latest_step_key = f"step_{next_task_index - 1}"
        latest_result_key = None
        for key in retrieved_data.keys():
            if key.startswith(latest_step_key):
                latest_result_key = key
                break

        if latest_result_key:
            latest_data = retrieved_data[latest_result_key]
            # Check if search returned no results
            if isinstance(latest_data, dict):
                listings = latest_data.get("listings", [])
                if isinstance(listings, list) and len(listings) == 0:
                    # No results found - should replan to gather more info
                    return "planner"

    # Normal execution flow
    return should_continue_execution(state)


def create_idss_graph() -> StateGraph:
    """Create the IDSS LangGraph workflow with goal understanding, planning, and execution."""

    # Create the state graph
    workflow = StateGraph(AgentState)

    # Add nodes
    workflow.add_node("goal_understanding", goal_understanding_node)
    workflow.add_node("planner", planner_node)
    workflow.add_node("executor", executor_node)

    # Add edges
    workflow.set_entry_point("goal_understanding")
    workflow.add_edge("goal_understanding", "planner")
    workflow.add_conditional_edges(
        "planner",
        should_continue_execution,
        {
            "executor": "executor",
            END: END
        }
    )
    workflow.add_conditional_edges(
        "executor",
        should_replan_or_execute,
        {
            "executor": "executor",
            "planner": "planner",
            END: END
        }
    )

    # Compile the graph
    return workflow.compile()


class IDSSAgent:
    """Interactive Decision Support System Agent."""

    def __init__(self):
        self.graph = create_idss_graph()

    def process_message(self, user_message: str, state: AgentState = None) -> AgentState:
        """
        Process a single user message through the complete workflow.

        Args:
            user_message: User's input message
            state: Current state (creates new if None)

        Returns:
            Updated agent state
        """
        if state is None:
            state = create_initial_state()

        # Add user message to state
        human_msg = HumanMessage(content=user_message)
        state["messages"].append(human_msg)

        # Run through the graph (synchronous)
        result = self.graph.invoke(state)

        return result

    def chat(self, user_id: str, user_message: str, state: AgentState = None) -> tuple[str, AgentState]:
        """
        Chat interface that returns both response and updated state.

        Args:
            user_id: User identifier (for future multi-user support)
            user_message: User's input message
            state: Current state (creates new if None)

        Returns:
            Tuple of (response_message, updated_state)
        """
        updated_state = self.process_message(user_message, state)

        # Extract the latest AI messages from the workflow execution
        messages = updated_state.get("messages", [])
        ai_messages = [msg for msg in messages if msg.__class__.__name__ == "AIMessage"]

        if ai_messages:
            # Return the content of the latest AI message(s)
            latest_responses = [msg.content for msg in ai_messages[-3:]]  # Last 3 AI messages
            response = "\n".join(latest_responses)
        else:
            # Fallback: generate simple status message
            current_goal = updated_state.get("current_goal", "No goal detected")
            response = f"Goal understood: {current_goal}"

        return response, updated_state