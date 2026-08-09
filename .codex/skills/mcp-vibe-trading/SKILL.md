---
name: mcp-vibe-trading
description: "Finance research, market data, alpha exploration, and backtesting through Vibe-Trading 0.1.12. Research-only by default; do not enable live broker actions unless explicitly authorized."
---

# MCP Server: vibe-trading

This MCP server is managed by the Virtual Office MCP Registry.

## Usage

Use this server when the task matches its description:

Finance research, market data, alpha exploration, and backtesting through Vibe-Trading 0.1.12. Research-only by default; do not enable live broker actions unless explicitly authorized.

## Client Registration

Virtual Office registers this MCP server in the native client that owns the assigned agent.
The normalized MCP config is:

```json
{
  "disabled": false,
  "command": "/Users/bytedance/cosh/my-virtual-office/data/mcp/vibe-trading/run-mcp.sh",
  "cwd": "/Users/bytedance/cosh/my-virtual-office/data/mcp/vibe-trading/workspace",
  "include": [
    "*"
  ],
  "timeout": 60,
  "connectTimeout": 30
}
```

If tools are unavailable, ask the user or VO operator to assign this MCP server again from the Skills Library MCP Registry. Do not request or print secrets.
