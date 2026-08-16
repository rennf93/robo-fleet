"""Shared session-cookie resolution.

One implementation, used by both the HTTP dual-path
(``robofleet.api.deps.get_agent_context``) and the WS panel-token gate
(``robofleet.api.websocket._require_panel_token``), so cookie validation can't
drift between the two call sites.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi_users_db_sqlalchemy import SQLAlchemyUserDatabase

from robofleet.api.auth.backend import get_jwt_strategy
from robofleet.api.auth.manager import UserManager
from robofleet.db.tables import UserTable

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


async def resolve_session_user(token: str | None, db: AsyncSession) -> UserTable | None:
    """Validate a cloud-auth session cookie; return the CEO user, or None."""
    if not token:
        return None
    manager = UserManager(SQLAlchemyUserDatabase(db, UserTable))
    return await get_jwt_strategy().read_token(token, manager)
