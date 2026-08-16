"""Tests for the ModelProvider enum in robofleet.models.base."""

from robofleet.models.base import ModelProvider


def test_adk_cloud_run_provider_value() -> None:
    assert ModelProvider.ADK_CLOUD_RUN.value == "adk_cloud_run"
