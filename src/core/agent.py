"""
Main agent runner interface for Interactive Decision Support System.

This module provides the primary interface for interacting with the IDSS agent,
managing conversation state and providing a clean API for external integration.
"""

from typing import Tuple
from .graph import IDSSAgent as _IDSSAgent
from .state import AgentState, create_initial_state


class IDSSAgent:
    """
    Main agent runner interface for the Interactive Decision Support System.
    
    This class provides session management and a clean API for external integration
    while wrapping the internal LangGraph workflow.
    """
    
    def __init__(self):
        self._internal_agent = _IDSSAgent()
    
    def chat(self, user_id: str, message: str, state: AgentState = None) -> Tuple[str, AgentState]:
        """
        Process one conversation turn.

        Args:
            user_id: Identifier for the user session
            message: User's input message
            state: Current conversation state (creates new if None)

        Returns:
            Tuple of (response_message, updated_state)
        """
        return self._internal_agent.chat(user_id, message, state)
    
    def create_session(self) -> AgentState:
        """Create a fresh state for a new conversation session."""
        return create_initial_state()
    
    def process_message(self, user_message: str, state: AgentState = None) -> AgentState:
        """
        Process a single user message and return updated state.
        
        Args:
            user_message: User's input message
            state: Current state (creates new if None)
            
        Returns:
            Updated agent state
        """
        return self._internal_agent.process_message(user_message, state)