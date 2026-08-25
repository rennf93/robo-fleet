"""
RoboFleet Bootstrap Script

Orchestrates system initialization: database, event bus, API server, and agent runtime.
Data constants are in robofleet/seeds/, database operations in robofleet/db/seed.py.
"""

import asyncio
from http import HTTPStatus

import httpx
import structlog
import uvicorn

from robofleet.api.deps import set_orchestrator
from robofleet.api.websocket import broadcast_agent_chunk
from robofleet.api.websocket_bridge import start_websocket_bridge
from robofleet.config import settings
from robofleet.db import bootstrap_database
from robofleet.events import (
    init_event_bus,
    register_default_handlers,
    set_event_context,
)
from robofleet.runtime import AgentOrchestrator, set_reasoning_stream_callback
from robofleet.services.llm import seed_adk_cloud_run_routing
from robofleet.services.notification import NotificationService

logger = structlog.get_logger()


class _BootstrapHolder:
    """Holder for bootstrap singleton instances."""

    orchestrator: AgentOrchestrator | None = None


async def _run_api_server() -> None:
    """Run the uvicorn API server."""
    config = uvicorn.Config(
        "robofleet.api.app:app",
        host=settings.host,
        port=settings.port,
        log_level="info",
        reload=False,  # Don't reload in production/container
        # Cosmetic here — server.serve() (below) never reads Config.loop, it
        # only matters to Server.run()/uvicorn.run(). The real switch is
        # cli.py's asyncio.run(loop_factory=resolve_uvicorn_loop_factory(...)),
        # which picks the loop this whole process (including this server)
        # already runs on. Kept in sync so the two never silently disagree.
        loop=settings.uvicorn_loop,
    )
    server = uvicorn.Server(config)
    await server.serve()


async def _wait_for_api_ready(max_wait: int = 120) -> None:
    """
    Wait for the API server to be ready to accept connections.

    The lifespan does document indexing which can take 30+ seconds,
    so we poll the health endpoint instead of using a fixed sleep.
    """
    api_url = f"http://127.0.0.1:{settings.port}/health"
    waited = 0
    while waited < max_wait:
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                resp = await client.get(api_url)
                if resp.status_code == HTTPStatus.OK:
                    logger.info("API server ready", waited_seconds=waited)
                    return
        except Exception:
            pass
        await asyncio.sleep(2)
        waited += 2
    logger.warning("API server not ready after timeout, starting orchestrator anyway")


async def main(
    skip_db: bool = False,
    skip_orchestrator: bool = False,
    spawn_agents: list[str] | None = None,
) -> None:
    """
    Main bootstrap entry point.

    Args:
        skip_db: Skip database initialization
        skip_orchestrator: Skip starting orchestrator
        spawn_agents: List of agent IDs to spawn immediately
    """
    logger.info("RoboFleet Bootstrap starting...")

    if not skip_db:
        await bootstrap_database()

    # On the GCP deploy the only delivery spawn path is ADK_CLOUD_RUN (Google
    # ADK Runner on Gemini, as Cloud Run Jobs). Seed the GLOBAL routing that
    # points the fleet at it + the provider row migration 094 deliberately
    # left unseeded. Idempotent; a no-op once seeded and on non-GCP boots
    # (gcp_project_id is empty). Best-effort: a seed failure must not block
    # startup (the orchestrator still boots; routing just falls to legacy
    # Anthropic, which fails on GCP at spawn time, not at boot).
    if settings.gcp_project_id:
        try:
            await seed_adk_cloud_run_routing()
        except Exception as e:  # pragma: no cover - best-effort seed
            logger.warning(
                "ADK_CLOUD_RUN routing seed failed; delivery spawns will fall back",
                error=str(e),
            )

    if skip_orchestrator:
        logger.info("Orchestrator skipped, exiting")
        return

    # Initialize event bus (Redis Streams with consumer groups)
    event_bus = await init_event_bus(
        consumer_name=f"orchestrator-{settings.host}:{settings.port}",
        recover_pending=True,  # Recover unacknowledged messages from previous run
    )
    register_default_handlers(event_bus)

    # Register WebSocket bridge handlers (forward stream events to WebSocket clients)
    await start_websocket_bridge()

    await event_bus.start_listening()
    logger.info("Event bus initialized (Redis Streams)")

    # Initialize orchestrator
    orchestrator = AgentOrchestrator()
    _BootstrapHolder.orchestrator = orchestrator

    # Set orchestrator in API routes
    set_orchestrator(orchestrator)

    # Wire up event handler dependencies (dependency injection)
    notification_service = NotificationService()
    set_event_context(
        notification_service=notification_service,
        orchestrator=orchestrator,
    )

    # Wire up agent reasoning stream (dependency injection)
    set_reasoning_stream_callback(broadcast_agent_chunk)

    # Start API server in background task
    api_task = asyncio.create_task(_run_api_server())
    logger.info("API server starting", host=settings.host, port=settings.port)

    # Wait for API to actually be ready (not just a fixed sleep)
    # The lifespan does document indexing which can take 30+ seconds
    await _wait_for_api_ready()

    await orchestrator.start()

    # Spawn requested agents
    if spawn_agents:
        startup_prompt = (
            "You are starting up. Call give_me_work() to receive your next assignment."
        )
        for agent_id in spawn_agents:
            try:
                await orchestrator.spawn_agent(
                    agent_id=agent_id,
                    initial_prompt=startup_prompt,
                    spawned_by="bootstrap",
                )
            except Exception as e:
                logger.error("Failed to spawn agent", agent_id=agent_id, error=str(e))

    try:
        # Wait for API server task (runs forever unless cancelled)
        await api_task
    except asyncio.CancelledError:
        pass
    finally:
        await orchestrator.stop()
        await event_bus.disconnect()
        _BootstrapHolder.orchestrator = None
        logger.info("RoboFleet shutdown complete")


if __name__ == "__main__":
    from robofleet.cli import cli

    cli()
