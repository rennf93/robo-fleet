"""
Pest Control Route Helpers

Route-glue helpers backing robofleet/api/routes/pest_control.py.
"""

from typing import TYPE_CHECKING

from robofleet.api.deps import CurrentAgentContext, require_ceo_role
from robofleet.api.schemas.pest_control import (
    PestHuntCycleResponse,
    PestHuntItemResponse,
)
from robofleet.foundation.policy.content import markers

if TYPE_CHECKING:
    from robofleet.db.tables import TaskTable


def require_ceo(agent: CurrentAgentContext) -> None:
    require_ceo_role(agent.role, action="view or act on the pest-control queue")


def status_value(task: "TaskTable") -> str:
    raw = task.status
    return raw.value if hasattr(raw, "value") else str(raw)


def to_response(task: "TaskTable") -> PestHuntCycleResponse:
    payload = markers.get_pest_hunt(task) or {}
    items = [PestHuntItemResponse(**item) for item in payload.get("items", [])]
    return PestHuntCycleResponse(
        task_id=str(task.id),
        title=task.title,
        status=status_value(task),
        items=items,
    )
