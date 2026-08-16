"""Coverage for GCP-port config additions."""

from __future__ import annotations


def test_local_llm_base_url_allow_external(monkeypatch):
    monkeypatch.setenv("ROBOCO_LOCAL_LLM_BASE_URL", "https://us-central1-aiplatform.googleapis.com/v1")
    monkeypatch.setenv("ROBOCO_LOCAL_LLM_BASE_URL_ALLOW_EXTERNAL", "true")
    from roboco.config import Settings
    s = Settings()
    assert s.local_llm_base_url == "https://us-central1-aiplatform.googleapis.com/v1"


def test_gcp_settings_defaults(monkeypatch):
    monkeypatch.setenv("ROBOCO_GCP_PROJECT_ID", "my-proj")
    monkeypatch.setenv("ROBOCO_GCP_REGION", "europe-west1")
    from roboco.config import Settings
    s = Settings()
    assert s.gcp_project_id == "my-proj"
    assert s.gcp_region == "europe-west1"
    assert s.gcp_memorystore_port == 6379