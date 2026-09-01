from datetime import datetime

import pytest
from robofleet import fleet_check

_MIN_ISO_LEN = len("YYYY-MM-DDTHH:MM:SS")


def test_fleet_check_epoch_exists() -> None:
    assert hasattr(fleet_check, "FLEET_CHECK_EPOCH")
    assert isinstance(fleet_check.FLEET_CHECK_EPOCH, str)


def test_fleet_check_epoch_is_valid_iso8601() -> None:
    epoch = fleet_check.FLEET_CHECK_EPOCH
    # Basic format check (starts with year, has T separator)
    assert len(epoch) >= _MIN_ISO_LEN
    assert "T" in epoch

    # Handle 'Z' suffix safely for all Python versions
    clean_epoch = epoch.replace("Z", "+00:00") if epoch.endswith("Z") else epoch

    try:
        dt = datetime.fromisoformat(clean_epoch)
        assert dt is not None
    except ValueError as e:
        pytest.fail(f"FLEET_CHECK_EPOCH '{epoch}' is not a valid ISO 8601 format: {e}")
