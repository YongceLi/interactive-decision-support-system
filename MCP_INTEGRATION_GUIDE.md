# MCP Integration Guide

## Overview

The agent is now connected to an MCP (Model Context Protocol) server for product-agnostic API access. This allows the system to seamlessly switch between different product types (vehicles, PCs, electronics) based on user queries.

## Architecture

### 1. MCP Server (`mcp_server.py`)
- Standalone MCP server implementing the Model Context Protocol
- Exposes tools: `search_vehicles`, `search_pcs`
- Can be used independently by MCP clients (e.g., Claude Desktop)
- Currently uses direct API calls internally

### 2. MCP Tools (`idss_agent/components/mcp_tools.py`)
- LangChain tools that wrap MCP server calls
- Currently fall back to direct API calls for efficiency
- Provides a clean interface for the agent

### 3. Product API Manager (`idss_agent/components/product_api_manager.py`)
- Detects product type from user queries
- Routes API calls to appropriate tools
- Currently supports: vehicles (working), PCs (placeholder)

### 4. Integration Points
- **agent.py**: Detects product type on every user message
- **recommendation.py**: Uses MCP tools for searching
- **state.py**: Tracks current product type

## How It Works

1. **User sends a message** → Agent detects product type (vehicle/PC/electronics)
2. **Product type set** → Product API Manager configured for that type
3. **Agent needs to search** → Uses MCP tools for that product type
4. **MCP tools** → Route to appropriate API endpoints
5. **Results returned** → Displayed to user

## Current Status

✅ **Vehicles**: Fully working with AutoDev API
⏳ **PCs**: Infrastructure ready, needs PC API endpoint
⏳ **Electronics**: Infrastructure ready, needs electronics API endpoint

## Adding a PC API

When you have the PC API ready:

1. **Update `mcp_server.py`** - Implement `search_pcs()` function:
```python
async def search_pcs(...) -> str:
    api_key = _get_pc_api_key()
    url = "https://your-pc-api.com/search"
    # Make API call
    return response.text
```

2. **Update `idss_agent/components/mcp_tools.py`** - Update the fallback:
```python
if tool_name == "search_pcs":
    from idss_agent.components.pc_apis import search_pc_listings
    return search_pc_listings.invoke(arguments)
```

3. **The system will automatically**:
   - Detect when users ask about PCs
   - Route to PC MCP tools
   - Use the PC API

## Benefits

- **Product-agnostic**: Single codebase handles multiple product types
- **Extensible**: Easy to add new product types
- **Standardized**: Uses MCP protocol for consistent API access
- **Independent**: MCP server can be used by other clients
- **Maintainable**: Centralized API management

## Testing

The agent will automatically detect product type and use the appropriate API tools. No manual configuration needed!

Example queries:
- "Find me a Toyota Camry" → Uses vehicle API
- "Show me gaming PCs" → Will use PC API (when implemented)
- "Looking for phones" → Will use electronics API (when implemented)


