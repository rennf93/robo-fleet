"""
Telegram Route Helpers

Side-effect-free helper backing robofleet/api/routes/telegram.py.
"""

from __future__ import annotations

from robofleet.api.deps import CurrentAgentContext, require_ceo_role


def _require_ceo(agent: CurrentAgentContext) -> None:
    require_ceo_role(agent.role, action="manage Telegram credentials")
