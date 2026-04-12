"""Pytest fixtures for MCP server tests.

Provides test client, OAuth provider, and database fixtures for all MCP tests.
"""

import os

os.environ.setdefault("VOCAB_API_KEY", "test-key")
os.environ.setdefault("VOCAB_API_URL", "http://test-backend")
os.environ.setdefault("MCP_SECRET", "test-mcp-secret")
