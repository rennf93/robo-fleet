"""Tests for the ModelProvider enum in roboco.models.base."""


def test_adk_cloud_run_provider_value() -> None:
    from roboco.models.base import ModelProvider

    assert ModelProvider.ADK_CLOUD_RUN.value == "adk_cloud_run"
