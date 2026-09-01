"""Git-forge provider seam (Phases 1-2 of the forge-providers spec).

``robofleet/services/git.py`` used to interleave local-git subprocess work with
inline ``httpx`` calls against GitHub's REST API. This package pulls the REST
transport out from under it behind a provider-agnostic contract
(:mod:`robofleet.services.forge.base`) so a future GitLab/Gitea adapter is a new
module here, not a rewrite of ``GitService``.

``base`` is pure contracts, ``github``/``gitea`` are REST transports,
``router`` routes per call from ``RepoRef.host``, and ``registry`` resolves
a project onto its provider and keeps the host→provider map. Nothing here imports
``robofleet.services.*`` — ``GitService`` depends on this package, never the
reverse.
"""

from __future__ import annotations

from robofleet.services.forge.base import GitProvider, RepoRef
from robofleet.services.forge.gitea import GiteaProvider
from robofleet.services.forge.github import GitHubProvider
from robofleet.services.forge.registry import provider_for, register_project_forge
from robofleet.services.forge.router import ForgeRouter

__all__ = [
    "ForgeRouter",
    "GitHubProvider",
    "GitProvider",
    "GiteaProvider",
    "RepoRef",
    "provider_for",
    "register_project_forge",
]
