"""Coverage for GCP-port config additions."""

from __future__ import annotations

from typing import TYPE_CHECKING

from roboco.config import Settings

if TYPE_CHECKING:
    import pytest

# Default MemoryStore port; matches config.Settings.gcp_memorystore_port.
DEFAULT_MEMORYSTORE_PORT = 6379


def test_local_llm_base_url_allow_external(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "ROBOCO_LOCAL_LLM_BASE_URL", "https://us-central1-aiplatform.googleapis.com/v1"
    )
    monkeypatch.setenv("ROBOCO_LOCAL_LLM_BASE_URL_ALLOW_EXTERNAL", "true")

    s = Settings()
    assert s.local_llm_base_url == "https://us-central1-aiplatform.googleapis.com/v1"


def test_gcp_settings_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ROBOCO_GCP_PROJECT_ID", "my-proj")
    monkeypatch.setenv("ROBOCO_GCP_REGION", "europe-west1")

    s = Settings()
    assert s.gcp_project_id == "my-proj"
    assert s.gcp_region == "europe-west1"
    assert s.gcp_memorystore_port == DEFAULT_MEMORYSTORE_PORT


# --- Task 4.2: Memorystore TLS redis_url ---


def test_redis_url_uses_rediss_when_memorystore_tls(monkeypatch: pytest.MonkeyPatch) -> None:
    """TLS branch: rediss:// + password when gcp_memorystore_tls + host set."""
    monkeypatch.setenv("ROBOCO_GCP_MEMORYSTORE_HOST", "10.0.0.5")
    monkeypatch.setenv("ROBOCO_GCP_MEMORYSTORE_TLS", "true")
    monkeypatch.setenv("ROBOCO_GCP_MEMORYSTORE_PORT", "6379")
    monkeypatch.setenv("ROBOCO_REDIS_PASSWORD", "pw")

    s = Settings()
    assert s.redis_url == "rediss://:pw@10.0.0.5:6379/0"


def test_redis_url_plain_when_memorystore_tls_false(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Non-TLS branch: plain redis:// when gcp_memorystore_tls is False."""
    monkeypatch.setenv("ROBOCO_GCP_MEMORYSTORE_HOST", "10.0.0.5")
    monkeypatch.setenv("ROBOCO_GCP_MEMORYSTORE_TLS", "false")
    monkeypatch.setenv("ROBOCO_REDIS_PASSWORD", "pw")

    s = Settings()
    assert s.redis_url == "redis://:pw@10.0.0.5:6379/0"


def test_redis_url_uses_memorystore_host_over_redis_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """gcp_memorystore_host overrides redis_host when set."""
    monkeypatch.setenv("ROBOCO_GCP_MEMORYSTORE_HOST", "memorystore.example")
    monkeypatch.setenv("ROBOCO_GCP_MEMORYSTORE_TLS", "true")
    monkeypatch.setenv("ROBOCO_REDIS_PASSWORD", "secret")

    s = Settings()
    assert s.redis_url.startswith("rediss://:secret@memorystore.example:")


# --- Task 4.5: Filestore workspaces root ---


def test_workspaces_root_uses_filestore_when_set(monkeypatch: pytest.MonkeyPatch) -> None:
    """gcp_filestore_share overrides workspaces_root when set."""
    monkeypatch.setenv("ROBOCO_GCP_FILESTORE_SHARE", "/mnt/fileshare/workspaces")

    s = Settings()
    assert s.workspaces_root == "/mnt/fileshare/workspaces"


def test_workspaces_root_default_when_filestore_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    """Default /data/workspaces when gcp_filestore_share is empty."""
    monkeypatch.delenv("ROBOCO_GCP_FILESTORE_SHARE", raising=False)

    s = Settings()
    assert s.workspaces_root == "/data/workspaces"
