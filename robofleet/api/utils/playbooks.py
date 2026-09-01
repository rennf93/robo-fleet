"""
Playbooks Route Helpers

Route-glue helpers backing robofleet/api/routes/playbooks.py.
"""

from fastapi import HTTPException, status

from robofleet.api.deps import CurrentAgentContext
from robofleet.models import AgentRole

_CURATOR_ROLES = frozenset({AgentRole.AUDITOR, AgentRole.CEO})


def require_curator(agent: CurrentAgentContext) -> None:
    if agent.role not in _CURATOR_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the Auditor or CEO may curate playbooks",
        )
