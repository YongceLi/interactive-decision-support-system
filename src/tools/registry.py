"""
Tool registry for managing available tools in IDSS.
"""

from typing import Dict, Optional
from .base import BaseTool, ToolResult


class ToolRegistry:
    """Registry for managing and accessing tools."""

    def __init__(self):
        self._tools: Dict[str, BaseTool] = {}

    def register_tool(self, tool: BaseTool) -> None:
        """Register a tool in the registry."""
        self._tools[tool.name] = tool

    def get_tool(self, name: str) -> Optional[BaseTool]:
        """Get a tool by name."""
        return self._tools.get(name)

    def list_tools(self) -> list[str]:
        """Get list of all registered tool names."""
        return list(self._tools.keys())

    def get_tool_description(self, name: str) -> Optional[str]:
        """Get description of a specific tool."""
        tool = self.get_tool(name)
        return tool.get_description() if tool else None

    def execute_tool(self, name: str, **kwargs) -> ToolResult:
        """Execute a tool by name with given parameters."""
        tool = self.get_tool(name)
        if not tool:
            return ToolResult(
                success=False,
                error=f"Tool '{name}' not found in registry",
                tool_name=name
            )

        try:
            result = tool.execute(**kwargs)
            result.tool_name = name
            return result
        except Exception as e:
            return ToolResult(
                success=False,
                error=f"Error executing tool '{name}': {str(e)}",
                tool_name=name
            )