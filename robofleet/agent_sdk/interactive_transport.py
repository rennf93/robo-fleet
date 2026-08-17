"""Shared transport helpers for the interactive intake/secretary containers.

The in-container HTTP receiver (``POST /turn``), the message source backed by its
queue, and the relay sink that POSTs each ``StreamChunk`` to the orchestrator's
live-events endpoint. Provider-agnostic: the grok mains and the Gemini/ADK mains
both reuse these so only the session class differs.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog
from fastapi import FastAPI
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    import asyncio
    from collections.abc import Awaitable, Callable

    import httpx

    from robofleet.agent_sdk.intake_driver import StreamChunk

logger = structlog.get_logger()


class _Turn(BaseModel):
    text: str = Field(..., min_length=1)


def make_message_source(
    queue: asyncio.Queue[str | None],
) -> Callable[[], Awaitable[str | None]]:
    """A ``MessageSource`` backed by the receiver queue. ``None`` ends the loop."""

    async def _next() -> str | None:
        return await queue.get()

    return _next


def make_relay_sink(
    base_url: str,
    session_id: str,
    client: httpx.AsyncClient,
    *,
    kind: str = "prompter",
) -> Callable[[StreamChunk], Awaitable[None]]:
    """An ``EventSink`` that POSTs each chunk to the orchestrator live relay.

    ``kind`` is the relay path segment: ``prompter`` (intake) or ``secretary``.
    """
    url = f"{base_url}/api/{kind}/live/{session_id}/events"
    label = kind.capitalize()

    async def _emit(chunk: StreamChunk) -> None:
        try:
            await client.post(
                url,
                json={
                    "kind": chunk.kind,
                    "text": chunk.text,
                    "tool": chunk.tool,
                    "data": chunk.data,
                },
            )
        except Exception as exc:
            logger.error(
                f"{label} relay POST failed", session_id=session_id, error=str(exc)
            )

    return _emit


def build_receiver(queue: asyncio.Queue[str | None]) -> FastAPI:
    """The in-container HTTP receiver: `POST /turn` enqueues the human's message."""
    app = FastAPI()

    @app.post("/turn")
    async def turn(body: _Turn) -> dict[str, bool]:
        await queue.put(body.text)
        return {"queued": True}

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app
