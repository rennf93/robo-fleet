from datetime import datetime

import build_marker


def test_build_marker_exists():
    assert hasattr(build_marker, "BUILD_MARKER")
    assert isinstance(build_marker.BUILD_MARKER, str)

def test_build_marker_is_valid_iso8601():
    marker = build_marker.BUILD_MARKER
    # Basic format check (starts with year, has T separator)
    assert len(marker) >= 19
    assert "T" in marker
    
    # Handle 'Z' suffix safely for all Python versions
    clean_marker = marker.replace("Z", "+00:00") if marker.endswith("Z") else marker
    
    try:
        dt = datetime.fromisoformat(clean_marker)
        assert dt is not None
    except ValueError as e:
        assert False, f"BUILD_MARKER '{marker}' is not a valid ISO 8601 format: {e}"
