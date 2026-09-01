"""
GitHub App Route Helpers

Route-glue helpers backing robofleet/api/routes/github_app.py.
"""

from robofleet.api.deps import CurrentAgentContext, require_ceo_role


def require_ceo(agent: CurrentAgentContext) -> None:
    require_ceo_role(agent.role, action="manage the GitHub App integration")
