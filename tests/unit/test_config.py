"""Coverage for GCP-port config additions."""

from __future__ import annotations


def test_local_llm_base_url_allow_external(monkeypatch):
    monkeypatch.setenv("ROBOCO_LOCAL_LLM_BASE_URL", "https://us-central1-aiplatform.googleapis.com/v1")
    monkeypatch.setenv("ROBOCO_LOCAL_LLM_BASE_URL_ALLOW_EXTERNAL", "true")
    from roboco.config import Settings
    s = Settings()
    assert s.local_llm_base_url == "https://us-central1-aiplatform.googleapis.com/v1"