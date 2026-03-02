import asyncio
import os
from typing import Any

import httpx
from mcp.server import Server
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

VOCAB_API_URL = os.getenv("VOCAB_API_URL", "http://localhost:8000")
VOCAB_API_KEY = os.getenv("VOCAB_API_KEY", "")
if not VOCAB_API_KEY:
    raise RuntimeError("VOCAB_API_KEY environment variable is not set")

# Module-level client: reuses connection pool and TLS session across calls
_http_client = httpx.AsyncClient()

server = Server("vocabulary")


def _text(message: str) -> list[TextContent]:
    return [TextContent(type="text", text=message)]


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="add_vocabulary",
            description=(
                "Add a vocabulary word to the personal study app. "
                "Use this when the user asks to save a word, or when you've "
                "explained a word and want to offer to save it."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "word": {
                        "type": "string",
                        "description": "The word or phrase to save",
                    },
                    "definition": {
                        "type": "string",
                        "description": "A clear, concise definition in English",
                    },
                    "example": {
                        "type": "string",
                        "description": "An example sentence using the word in context",
                    },
                    "language": {
                        "type": "string",
                        "description": "The language of the word (e.g. French, Spanish, English)",
                    },
                },
                "required": ["word", "definition"],
            },
        )
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    if name != "add_vocabulary":
        raise ValueError(f"Unknown tool: {name}")

    # Only forward the declared fields — never pass arbitrary caller-supplied keys
    payload: dict[str, str] = {
        "word": arguments["word"],
        "definition": arguments["definition"],
    }
    if "example" in arguments:
        payload["example"] = arguments["example"]
    if "language" in arguments:
        payload["language"] = arguments["language"]

    try:
        response = await _http_client.post(
            f"{VOCAB_API_URL}/vocabulary",
            json=payload,
            headers={"X-API-Key": VOCAB_API_KEY},
            timeout=10.0,
        )
        response.raise_for_status()
        word_data = response.json()
        return _text(
            f"Successfully saved '{word_data.get('word', payload['word'])}' to your vocabulary deck. "
            f"It will be due for review on {word_data.get('next_review', 'a future date')}."
        )
    except httpx.HTTPStatusError as e:
        return _text(f"Failed to save word: HTTP {e.response.status_code} — {e.response.text}")
    except Exception as e:
        return _text(f"Failed to save word: {e}")


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="vocabulary",
                server_version="0.1.0",
                capabilities=server.get_capabilities(
                    notification_options=None,
                    experimental_capabilities={},
                ),
            ),
        )
    await _http_client.aclose()


if __name__ == "__main__":
    asyncio.run(main())
