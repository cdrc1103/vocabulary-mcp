"""Heisig hanzi MCP tools and input models.

Registers the add_hanzi tool against a FastMCP instance. General-purpose
vocabulary tools live in server.py.
"""

import httpx
from pydantic import BaseModel, Field


class HanziInput(BaseModel):
    """Validated input for one Heisig hanzi card arriving from chat (MCP boundary).

    Attributes:
        hanzi: The hanzi character.
        keyword: Single Heisig keyword (meaning only).
        pinyin: Pinyin with tone mark.
        tone: Tone number 1-5 (5 = neutral).
        definition: Meaning/usage for a new card; ignored on enrich. NOT for pinyin.
        example: Optional usage sentence for a new card.
    """

    hanzi: str = Field(min_length=1)
    keyword: str = Field(min_length=1)
    pinyin: str = Field(min_length=1)
    tone: int = Field(ge=1, le=5)
    definition: str | None = None
    example: str | None = None


def register_tools(
    mcp,
    http_client: httpx.AsyncClient,
    vocab_api_url: str,
    vocab_api_key: str,
):
    """Register Heisig MCP tools with the provided FastMCP instance.

    Args:
        mcp: FastMCP server instance to register tools on.
        http_client: Shared async HTTP client.
        vocab_api_url: Base URL of the vocabulary backend API.
        vocab_api_key: API key for backend authentication.

    Returns:
        The add_hanzi tool function, for direct access in tests.
    """

    @mcp.tool(
        description=(
            "Add or enrich Heisig hanzi study cards (max 50). Each card needs the hanzi, a single "
            "English keyword (meaning only), pinyin with tone mark, and the tone number 1-5. "
            "Re-calling on a character that already exists enriches it in place and preserves "
            "its review schedule. Pass session_name to group NEW cards; existing cards keep their session."
        )
    )
    async def add_hanzi(cards: list[HanziInput], session_name: str | None = None) -> str:
        """Create or enrich Heisig hanzi cards via the backend upsert endpoint.

        Validates every card against HanziInput before sending. Maps the 'hanzi' field to
        the backend 'word' field. Returns a create/enrich/unchanged breakdown.

        Args:
            cards: List of HanziInput cards (1-50).
            session_name: Optional session for newly created cards only.

        Returns:
            A summary message with created/enriched/unchanged counts, or an error message.
        """
        try:
            validated = [HanziInput.model_validate(c) for c in cards]
        except Exception as e:
            return f"Invalid hanzi input, nothing was saved: {e}"

        payload_cards = []
        for c in validated:
            d = c.model_dump()
            d["word"] = d.pop("hanzi")
            payload_cards.append(d)

        try:
            response = await http_client.post(
                f"{vocab_api_url}/vocabulary/hanzi/bulk",
                json={"cards": payload_cards, "session_name": session_name},
                headers={"X-API-Key": vocab_api_key},
                timeout=30.0,
            )
            response.raise_for_status()
            data = response.json()
            return (
                f"Enriched {data['enriched']} existing · created {data['created']} new · "
                f"{data['unchanged']} unchanged."
            )
        except httpx.HTTPStatusError as e:
            return f"Failed to save hanzi: HTTP {e.response.status_code} — {e.response.text}"
        except Exception as e:
            return f"Failed to save hanzi: {e}"

    return add_hanzi
