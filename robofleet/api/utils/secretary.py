"""
Secretary Route Helpers

Route-glue helpers backing robofleet/api/routes/secretary.py.
"""

from fastapi import HTTPException, status

from robofleet.api.deps import CurrentAgentContext
from robofleet.models import AgentRole

SECRETARY_OR_CEO = frozenset({AgentRole.SECRETARY, AgentRole.CEO})


def require(agent: CurrentAgentContext, allowed: frozenset[AgentRole]) -> None:
    if agent.role not in allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"role '{agent.role}' not permitted on the Secretary surface",
        )
