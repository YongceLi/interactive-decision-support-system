"""
Base tool class and result structures for IDSS tools.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from dataclasses import dataclass


@dataclass
class ToolResult:
    """Standard result structure for all tool executions."""
    success: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    tool_name: str = ""

    def __post_init__(self):
        if not self.success and not self.error:
            self.error = "Unknown error occurred"


class BaseTool(ABC):
    """Abstract base class for all IDSS tools."""

    def __init__(self, name: str):
        self.name = name

    @abstractmethod
    def execute(self, **kwargs) -> ToolResult:
        """Execute the tool with given parameters."""
        pass

    @abstractmethod
    def get_description(self) -> str:
        """Get a description of what this tool does."""
        pass

    @abstractmethod
    def get_required_params(self) -> list[str]:
        """Get list of required parameter names."""
        pass

    @abstractmethod
    def get_optional_params(self) -> list[str]:
        """Get list of optional parameter names."""
        pass