"""
MCP Client for connecting the agent to the MCP server.

This client manages the connection to the MCP server and provides
methods to call tools exposed by the server.
"""

import asyncio
import json
import os
from typing import Dict, Any, List, Optional
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from idss_agent.logger import get_logger

logger = get_logger("components.mcp_client")


class MCPClientManager:
    """Manages connection to MCP server."""
    
    def __init__(self):
        self.session: Optional[ClientSession] = None
        self.server_params: Optional[StdioServerParameters] = None
        self._lock = asyncio.Lock()
        self._loop = None
    
    def _get_loop(self):
        """Get or create event loop."""
        if self._loop is None:
            try:
                self._loop = asyncio.get_event_loop()
            except RuntimeError:
                self._loop = asyncio.new_event_loop()
                asyncio.set_event_loop(self._loop)
        return self._loop
    
    def _run_async(self, coro):
        """Run async function synchronously."""
        loop = self._get_loop()
        if loop.is_running():
            # If loop is already running, we need to use a different approach
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, coro)
                return future.result()
        else:
            return loop.run_until_complete(coro)
    
    def connect(self):
        """Connect to the MCP server (synchronous wrapper)."""
        self._run_async(self._connect_async())
    
    async def _connect_async(self):
        """Connect to the MCP server (async implementation)."""
        if self.session is not None:
            return
        
        try:
            # Get the path to mcp_server.py
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            mcp_server_path = os.path.join(project_root, "mcp_server.py")
            
            # Create server parameters
            self.server_params = StdioServerParameters(
                command="python",
                args=[mcp_server_path],
                env=os.environ.copy()
            )
            
            # Connect to the server
            async with stdio_client(self.server_params) as (read, write):
                async with ClientSession(read, write) as session:
                    self.session = session
                    # Initialize the session
                    await session.initialize()
                    logger.info("Connected to MCP server")
                    
        except Exception as e:
            logger.error(f"Failed to connect to MCP server: {e}")
            raise
    
    def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        """Call a tool on the MCP server (synchronous wrapper)."""
        return self._run_async(self._call_tool_async(tool_name, arguments))
    
    async def _call_tool_async(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        """Call a tool on the MCP server (async implementation)."""
        if self.session is None:
            await self._connect_async()
        
        try:
            result = await self.session.call_tool(tool_name, arguments)
            
            # Extract text content from result
            if result.content and len(result.content) > 0:
                content = result.content[0]
                if hasattr(content, 'text'):
                    return content.text
                elif isinstance(content, dict) and 'text' in content:
                    return content['text']
            
            return json.dumps({"error": "No content returned from tool"})
            
        except Exception as e:
            logger.error(f"Error calling tool {tool_name}: {e}")
            return json.dumps({"error": str(e)})
    
    def list_tools(self) -> List[Dict[str, Any]]:
        """List available tools from the MCP server (synchronous wrapper)."""
        return self._run_async(self._list_tools_async())
    
    async def _list_tools_async(self) -> List[Dict[str, Any]]:
        """List available tools from the MCP server (async implementation)."""
        if self.session is None:
            await self._connect_async()
        
        try:
            result = await self.session.list_tools()
            return [tool.model_dump() if hasattr(tool, 'model_dump') else tool for tool in result.tools]
        except Exception as e:
            logger.error(f"Error listing tools: {e}")
            return []


# Global instance
_mcp_client_manager = None


def get_mcp_client_manager() -> MCPClientManager:
    """Get the global MCP client manager instance."""
    global _mcp_client_manager
    if _mcp_client_manager is None:
        _mcp_client_manager = MCPClientManager()
    return _mcp_client_manager


def call_mcp_tool(tool_name: str, arguments: Dict[str, Any]) -> str:
    """Convenience function to call MCP tools (synchronous)."""
    manager = get_mcp_client_manager()
    return manager.call_tool(tool_name, arguments)

