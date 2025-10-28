# MCP Server for Product Search

This directory contains a full implementation of a Model Context Protocol (MCP) server for product-agnostic search capabilities.

## What is MCP?

Model Context Protocol (MCP) is a standardized protocol developed by Anthropic that enables AI assistants to access external tools and resources. This MCP server exposes product search capabilities for vehicles, PCs, and electronics.

## Installation

The MCP package is already installed in the virtual environment. If you need to reinstall:

```bash
pip install mcp
```

## Running the MCP Server

### Standalone (for testing)

```bash
python mcp_server.py
```

The server will communicate via stdio (standard input/output).

### Integration with Claude Desktop

To use this MCP server with Claude Desktop, add it to your Claude configuration:

**macOS/Linux:**
Edit `~/Library/Application Support/Claude/claude_desktop_config.json`

**Windows:**
Edit `%APPDATA%\Claude\claude_desktop_config.json`

Add this configuration:

```json
{
  "mcpServers": {
    "product-search": {
      "command": "python",
      "args": ["/path/to/interactive-decision-support-system/mcp_server.py"],
      "env": {
        "AUTODEV_API_KEY": "your-autodev-api-key-here"
      }
    }
  }
}
```

### Integration with Other MCP Clients

This server implements the MCP protocol over stdio, so it can be used with any MCP-compatible client that supports stdio transport.

## Available Tools

### 1. `search_vehicles`

Search for vehicle listings using the AutoDev API.

**Parameters:**
- `make` (string): Vehicle manufacturer (e.g., "Toyota", "Ford")
- `model` (string): Vehicle model (e.g., "Camry", "F-150")
- `year` (string): Vehicle year or range (e.g., "2022-2026")
- `price` (string): Price range (e.g., "10000-30000")
- `state` (string): State code (e.g., "CA", "NY")
- `miles` (string): Mileage range (e.g., "0-50000")
- `page` (integer): Page number (default: 1)
- `limit` (integer): Results per page (default: 20)

**Example:**
```json
{
  "name": "search_vehicles",
  "arguments": {
    "make": "Toyota",
    "model": "Camry",
    "price": "10000-30000",
    "state": "CA"
  }
}
```

### 2. `search_pcs`

Search for PC listings (placeholder - needs PC API implementation).

**Parameters:**
- `cpu` (string): CPU specification
- `gpu` (string): GPU specification
- `ram` (string): RAM specification
- `storage` (string): Storage specification
- `price_min` (integer): Minimum price
- `price_max` (integer): Maximum price
- `page` (integer): Page number (default: 1)
- `limit` (integer): Results per page (default: 20)

## Adding a PC API

When you have the PC API ready, update the `search_pcs` function in `mcp_server.py`:

```python
async def search_pcs(...) -> str:
    """Search for PC listings."""
    # Replace this with actual PC API call
    api_key = _get_pc_api_key()  # Add this function
    url = "https://your-pc-api.com/search"
    # ... implement API call
    return response.text
```

## Testing

You can test the MCP server using the MCP Inspector or by running it directly:

```bash
python mcp_server.py
```

Then send JSON-RPC messages to test the tools.

## Architecture

- **Transport**: Stdio (standard input/output)
- **Protocol**: JSON-RPC 2.0
- **Tools**: Vehicle search (working), PC search (placeholder)
- **Resources**: None currently
- **Prompts**: None currently

## Future Enhancements

1. Add PC API integration
2. Add electronics API integration
3. Add resources for product metadata
4. Add prompts for common searches
5. Add caching layer for performance
6. Add authentication and rate limiting


