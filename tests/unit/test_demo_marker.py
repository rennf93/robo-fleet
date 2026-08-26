from datetime import datetime

import pytest
from robofleet import demo_marker


def test_demo_run_epoch_exists():
    assert hasattr(demo_marker, "DEMO_RUN_EPOCH")
    assert isinstance(demo_marker.DEMO_RUN_EPOCH, str)


_MIN_ISO_LEN = len("2026-01-01T00:00:00")


def test_demo_run_epoch_is_valid_iso8601():
    epoch = demo_marker.DEMO_RUN_EPOCH
    # Basic format check (starts with year, has T separator)
    assert len(epoch) >= _MIN_ISO_LEN
    assert "T" in epoch

    # Handle 'Z' suffix safely for all Python versions
    clean_epoch = epoch.replace("Z", "+00:00") if epoch.endswith("Z") else epoch

    try:
        dt = datetime.fromisoformat(clean_epoch)
    except ValueError as err:
        pytest.fail(f"DEMO_RUN_EPOCH '{epoch}' is not a valid ISO 8601 format: {err}")
    assert dt is not None
