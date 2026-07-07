"""Entrypoint for running the MCP server directly: `python -m server`."""

import os

import uvicorn

from server.general import mcp

if __name__ == "__main__":
    uvicorn.run(mcp.streamable_http_app(), host="0.0.0.0", port=int(os.getenv("PORT", "8080")))
