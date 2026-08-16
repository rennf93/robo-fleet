"""Secret Manager accessor (Task 4.4).

``access_secret(name, prefix=...)`` wraps ``google-cloud-secret-manager``,
accessing version ``latest`` of ``{prefix}-{name}`` and decoding the payload.
The client is lazy so a bare import never needs GCP creds.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
from roboco.infra import secretmanager


def _fake_client(payload: bytes) -> MagicMock:
    response = MagicMock()
    response.payload.data = payload
    client = MagicMock()
    client.access_secret_version.return_value = response
    return client


def _secret_name(call: Any) -> str:
    request = call.args[0] if call.args else call.kwargs.get("request")
    if isinstance(request, dict):
        return str(request["name"])
    return str(request.name)


def test_access_secret_decodes_latest_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _fake_client(b"super-secret-value")

    def _fake_ctor() -> Any:
        return client

    monkeypatch.setattr(secretmanager, "_SecretManagerServiceClient", _fake_ctor)
    val = secretmanager.access_secret("fernet-key", prefix="roboco")
    client.access_secret_version.assert_called_once()
    name = _secret_name(client.access_secret_version.call_args)
    assert "roboco-fernet-key" in name
    assert "latest" in name
    assert val == "super-secret-value"


def test_access_secret_uses_settings_prefix_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _fake_client(b"v")
    monkeypatch.setattr(secretmanager, "_SecretManagerServiceClient", lambda: client)
    monkeypatch.setattr(secretmanager.settings, "gcp_secret_manager_prefix", "rf")
    val = secretmanager.access_secret("agent-auth-secret")
    name = _secret_name(client.access_secret_version.call_args)
    assert "rf-agent-auth-secret" in name
    assert val == "v"


def test_access_secret_uses_explicit_project(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _fake_client(b"v")
    monkeypatch.setattr(secretmanager, "_SecretManagerServiceClient", lambda: client)
    secretmanager.access_secret("x", prefix="roboco", project="my-proj-123")
    # The secret name should embed the project id (projects/my-proj-123/secrets/...).
    name = _secret_name(client.access_secret_version.call_args)
    assert "my-proj-123" in name


def test_secretmanager_imports_clean() -> None:
    from roboco.infra.secretmanager import access_secret  # import-cleanliness check

    assert callable(access_secret)


# --- Wiring: _auth_secret + _get_fernet Secret Manager branches ---


def test_auth_secret_uses_secret_manager_when_prefix_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import roboco.agents_config as ac
    import roboco.infra.secretmanager as sm

    monkeypatch.setattr(ac.settings, "gcp_project_id", "my-proj")
    monkeypatch.setattr(ac.settings, "gcp_secret_manager_prefix", "roboco")
    ac._auth_secret_cache.clear()
    monkeypatch.delenv("ROBOCO_AGENT_AUTH_SECRET", raising=False)
    monkeypatch.setattr(
        sm,
        "access_secret",
        lambda name, **kw: "sm-auth-secret" if name == "agent-auth-secret" else "",
    )
    val = ac._auth_secret()
    assert val == b"sm-auth-secret"


def test_auth_secret_env_path_when_prefix_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import roboco.agents_config as ac

    monkeypatch.setattr(ac.settings, "gcp_project_id", "")
    monkeypatch.setenv("ROBOCO_AGENT_AUTH_SECRET", "env-secret")
    val = ac._auth_secret()
    assert val == b"env-secret"


def test_get_fernet_uses_secret_manager_when_prefix_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import roboco.infra.secretmanager as sm
    from cryptography.fernet import Fernet
    from roboco.utils import crypto

    real_key = Fernet.generate_key().decode()
    monkeypatch.setattr(crypto.settings, "encryption_key", "")
    monkeypatch.setattr(crypto.settings, "gcp_project_id", "my-proj")
    monkeypatch.setattr(crypto.settings, "gcp_secret_manager_prefix", "roboco")

    def _fake_access(name: str, **kw: Any) -> str:
        return real_key if name == "fernet-key" else ""

    monkeypatch.setattr(sm, "access_secret", _fake_access)
    f = crypto._get_fernet()
    assert isinstance(f, Fernet)
