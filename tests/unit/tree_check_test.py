import subprocess
import sys
from datetime import datetime

from robofleet import tree_check


def test_tree_check_epoch_exists():
    assert hasattr(tree_check, "TREE_CHECK_EPOCH")
    assert isinstance(tree_check.TREE_CHECK_EPOCH, str)


# An ISO-8601 timestamp with calendar date, seconds precision and a zone offset is
# at minimum "YYYY-MM-DDTHH:MM:SS+HH:MM" (19 chars) before the zone offset.
_MIN_ISO8601_LEN = 19


def test_tree_check_epoch_is_valid_iso8601():
    epoch = tree_check.TREE_CHECK_EPOCH
    # Basic format check (starts with year, has T separator)
    assert len(epoch) >= _MIN_ISO8601_LEN
    assert "T" in epoch

    # Handle 'Z' suffix safely for all Python versions
    clean_epoch = epoch.replace("Z", "+00:00") if epoch.endswith("Z") else epoch

    try:
        dt = datetime.fromisoformat(clean_epoch)
    except ValueError as e:
        msg = f"TREE_CHECK_EPOCH '{epoch}' is not a valid ISO 8601 format: {e}"
        raise AssertionError(msg) from e
    assert dt is not None


def test_tree_check_cli_direct(capsys):
    """Test calling the main() function directly and capturing stdout."""
    tree_check.main()
    captured = capsys.readouterr()
    assert captured.out.strip() == tree_check.TREE_CHECK_EPOCH


def test_tree_check_cli_subprocess():
    """Test calling the module as a CLI using subprocess."""
    result = subprocess.run(
        [sys.executable, "-m", "robofleet.tree_check"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.strip() == tree_check.TREE_CHECK_EPOCH
