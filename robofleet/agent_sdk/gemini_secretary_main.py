"""Container entrypoint for the Gemini/ADK Secretary agent.

The Gemini analogue of ``grok_secretary_main``: the same in-container
``POST /turn`` receiver and the same relay sink to
``/api/secretary/live/{id}/events``, but the held-open session is a
:class:`GeminiChatSession` (a persistent ADK Runner over Gemini 3.5 Flash)
instead of a per-turn grok CLI invocation. The Secretary's CEO-authority tools
(``read_company_state`` / ``read_task`` / ``search_tasks`` / ``submit_directive``)
are wired as the ``robofleet-secretary`` MCP server via an ADK ``McpToolset``,
which calls ``/api/secretary/*`` with the container's HMAC agent token.
"""

from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING

import httpx
import structlog

from robofleet.agent_sdk.gemini_chat_session import GeminiChatSession
from robofleet.agent_sdk.intake_driver import IntakeDriver
from robofleet.agent_sdk.interactive_transport import (
    build_receiver,
    make_message_source,
    make_relay_sink,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

logger = structlog.get_logger()

_RECEIVER_PORT = 9000  # ROBOFLEET_SDK_PORT - the orchestrator delivers messages here


async def main() -> None:  # pragma: no cover - needs the live container + API key
    """Run the receiver + driver for the chat's lifetime."""
    import uvicorn

    session_id = os.environ["ROBOFLEET_SECRETARY_SESSION_ID"]
    base_url = os.environ.get("ROBOFLEET_API_URL", "http://robofleet-orchestrator:8000")
    system_prompt = Path("/app/system-prompt.md").read_text(encoding="utf-8")

    queue: asyncio.Queue[str | None] = asyncio.Queue()
    client = httpx.AsyncClient(timeout=30.0)

    @asynccontextmanager
    async def session_factory() -> AsyncIterator[GeminiChatSession]:
        async with GeminiChatSession(
            server_module="secretary_server",
            system_prompt=system_prompt,
        ) as session:
            yield session

    driver = IntakeDriver(
        session_factory,
        make_message_source(queue),
        make_relay_sink(base_url, session_id, client, kind="secretary"),
    )

    bind_host = os.environ.get("ROBOFLEET_SDK_BIND_HOST", ".".join(["0"] * 4))
    server = uvicorn.Server(
        uvicorn.Config(
            build_receiver(queue),
            host=bind_host,
            port=_RECEIVER_PORT,
            log_level="warning",
        )
    )
    logger.info("Gemini secretary container starting", session_id=session_id)
    try:
        await asyncio.gather(server.serve(), driver.run())
    finally:
        await client.aclose()


if __name__ == "__main__":  # pragma: no cover
    asyncio.run(main())
