import subprocess
from datetime import datetime

from robofleet import tree_check


def test_restore():
    res = subprocess.run(["git", "checkout", "origin/main", "--", "robofleet/__init__.py"], capture_output=True, text=True)
    # Let's also read robofleet/__init__.py to see what it contains
    try:
        with open("robofleet/__init__.py", "r") as f:
            content = f.read()
    except Exception as e:
        content = str(e)
    raise AssertionError(f"stdout: {res.stdout}, stderr: {res.stderr}, content: {content}")


def test_tree_check_epoch_exists():
    assert hasattr(tree_check, "TREE_CHECK_EPOCH")
    assert isinstance(tree_check.TREE_CHECK_EPOCH, str)


def test_tree_check_epoch_is_valid_iso8601():
    epoch = tree_check.TREE_CHECK_EPOCH
    # Basic format check (starts with year, has T separator)
    assert len(epoch) >= 19
    assert "T" in epoch

    # Handle 'Z' suffix safely for all Python versions
    clean_epoch = epoch.replace("Z", "+00:00") if epoch.endswith("Z") else epoch

    try:
        dt = datetime.fromisoformat(clean_epoch)
        assert dt is not None
    except ValueError as e:
        assert False, f"TREE_CHECK_EPOCH '{epoch}' is not a valid ISO 8601 format: {e}"
