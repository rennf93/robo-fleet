"""Secret Manager accessor (Task 4.4).

``access_secret(name, prefix=..., project=...)`` wraps
``google-cloud-secret-manager``, accessing version ``latest`` of
``{prefix}-{name}`` and decoding the payload. The client is lazy so a bare
``from roboco.infra import secretmanager`` never constructs a client and never
needs GCP credentials at load time.
"""

from __future__ import annotations

from typing import Any

from roboco.config import settings


def _SecretManagerServiceClient() -> Any:
    """Lazy construction of ``google.cloud.secretmanager.SecretManagerServiceClient``.

    Indirected so tests can monkeypatch the client without importing the
    google package.
    """
    from google.cloud import secretmanager as _sm  # lazy import

    return _sm.SecretManagerServiceClient()


def access_secret(
    name: str, *, prefix: str | None = None, project: str | None = None
) -> str:
    """Read version ``latest`` of ``{prefix}-{name}`` from Secret Manager.

    ``prefix`` defaults to ``settings.gcp_secret_manager_prefix``; ``project``
    defaults to ``settings.gcp_project_id``. Returns the decoded payload string.
    """
    client = _SecretManagerServiceClient()
    eff_prefix = prefix if prefix is not None else settings.gcp_secret_manager_prefix
    eff_project = project if project is not None else settings.gcp_project_id
    secret_id = f"{eff_prefix}-{name}" if eff_prefix else name
    full_name = (
        f"projects/{eff_project}/secrets/{secret_id}/versions/latest"
        if eff_project
        else f"{secret_id}/versions/latest"
    )
    response = client.access_secret_version(request={"name": full_name})
    data: str = response.payload.data.decode()
    return data
