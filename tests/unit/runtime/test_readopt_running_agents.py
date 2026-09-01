"""Startup re-adoption of still-running agent containers into ``_instances``.

An orchestrator restart loses the in-memory ``_instances`` registry while the
agent containers keep running. The reaper has a Docker-liveness fallback for
that (``_assignee_container_running``), but the spawn gate's ``_is_agent_active``
does not, so after a restart it sees a live agent as inactive and can
double-spawn it onto work its forgotten-but-running container is already doing.
``_readopt_running_agents`` probes each known agent slug's container and
re-registers a minimal ACTIVE instance for any that is running, so both the
reaper's live-skip and the spawn gate see the live agent immediately. A running
container whose slug no longer holds a live (non-terminal) claim is a zombie
left over after a prior orchestrator released the claim. It is NOT registered,
so it can't block the spawn gate from re-dispatching that slug (#72).

The readopt scans ``AGENT_IMAGES`` for local persistent-container slugs. Leg D1
stripped the delivery fleet's specialized images (delivery agents are ADK
Cloud Run Jobs now), so ``AGENT_IMAGES`` holds only the interactive persistent
containers (intake/secretary). These tests target those two surviving slugs
instead of the removed delivery slugs (be-dev-1, fe-pm).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from robofleet.runtime.orchestrator import (
    INTAKE_AGENT_ID,
    SECRETARY_AGENT_ID,
    AgentOrchestrator,
    AgentState,
)

_EXPECTED_READOPTED = 2  # both intake-1 and secretary-1 are running


def _orch() -> Any:
    orch = AgentOrchestrator.__new__(AgentOrchestrator)  # bypass __init__
    orch._instances = {}
    return orch


@pytest.mark.asyncio
async def test_readopts_running_containers_as_active() -> None:
    orch = _orch()
    running = {INTAKE_AGENT_ID, SECRETARY_AGENT_ID}

    async def inspect(name: str) -> tuple[bool, int | None]:
        slug = name.removeprefix("robofleet-agent-")
        return (slug in running, 0)

    orch._inspect_container_state = AsyncMock(side_effect=inspect)
    orch._agent_holds_live_claim = AsyncMock(return_value=True)  # mid-task -> live

    n = await orch._readopt_running_agents()

    assert n == _EXPECTED_READOPTED
    assert orch._instances[INTAKE_AGENT_ID].state == AgentState.ACTIVE
    assert orch._instances[INTAKE_AGENT_ID].agent_id == INTAKE_AGENT_ID
    assert orch._instances[SECRETARY_AGENT_ID].state == AgentState.ACTIVE


@pytest.mark.asyncio
async def test_readopt_leaves_already_tracked_instance_untouched() -> None:
    orch = _orch()
    sentinel = MagicMock()
    orch._instances = {INTAKE_AGENT_ID: sentinel}
    orch._inspect_container_state = AsyncMock(return_value=(True, 0))

    await orch._readopt_running_agents()

    assert orch._instances[INTAKE_AGENT_ID] is sentinel  # not re-adopted over


@pytest.mark.asyncio
async def test_readopt_inert_when_nothing_running() -> None:
    orch = _orch()
    orch._inspect_container_state = AsyncMock(return_value=(False, None))

    n = await orch._readopt_running_agents()

    assert n == 0
    assert orch._instances == {}


@pytest.mark.asyncio
async def test_readopt_swallows_probe_errors() -> None:
    orch = _orch()
    orch._inspect_container_state = AsyncMock(side_effect=RuntimeError("no docker"))

    n = await orch._readopt_running_agents()

    assert n == 0  # best-effort: a probe failure never raises into startup


@pytest.mark.asyncio
async def test_readopt_records_container_id_so_health_check_can_see_exit() -> None:
    # Re-adopt must capture the real container id; a None container_id is skipped
    # by _check_health, stranding the task under a phantom ACTIVE instance.
    orch = _orch()
    orch._inspect_container_state = AsyncMock(return_value=(True, 0))
    orch._resolve_container_id = AsyncMock(return_value="deadbeef1234")
    orch._agent_holds_live_claim = AsyncMock(return_value=True)  # live claim

    await orch._readopt_running_agents()

    inst = orch._instances[next(iter(orch._instances))]
    assert inst.container_id == "deadbeef1234"
    assert inst.state == AgentState.ACTIVE


# ---------------------------------------------------------------------------
# #72: a running container whose slug holds NO live claim is a zombie left
# over after a prior orchestrator released the claim. It must NOT be
# registered ACTIVE, or it blocks the spawn gate from re-dispatching that slug
# until the stale container is eventually noticed.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_readopt_skips_zombie_container_with_no_live_claim() -> None:
    """#72: a running container that owns no non-terminal task is a zombie.
    Registering it ACTIVE would block re-dispatch of its slug; skip it instead."""
    orch = _orch()
    orch._inspect_container_state = AsyncMock(return_value=(True, 0))
    orch._resolve_container_id = AsyncMock(return_value="deadbeef1234")
    orch._agent_holds_live_claim = AsyncMock(return_value=False)  # claim released

    n = await orch._readopt_running_agents()

    assert n == 0  # zombie not re-adopted
    assert orch._instances == {}  # spawn gate free to dispatch the slug fresh


@pytest.mark.asyncio
async def test_readopt_failopen_registers_on_claim_lookup_error() -> None:
    """#72: a DB error in the live-claim lookup is indeterminate. Fall back to
    today's register behaviour so a startup DB hiccup can't regress the
    cold-start double-spawn protection the readopt exists to provide."""
    orch = _orch()
    running = {INTAKE_AGENT_ID}

    async def inspect(name: str) -> tuple[bool, int | None]:
        return (name.removeprefix("robofleet-agent-") in running, 0)

    orch._inspect_container_state = AsyncMock(side_effect=inspect)
    orch._resolve_container_id = AsyncMock(return_value="deadbeef1234")
    orch._agent_holds_live_claim = AsyncMock(return_value=None)  # lookup failed

    n = await orch._readopt_running_agents()

    assert n == 1  # fail-open: register rather than risk a double-spawn
    inst = orch._instances[next(iter(orch._instances))]
    assert inst.state == AgentState.ACTIVE
