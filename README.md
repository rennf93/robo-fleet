# RoboFleet Backend

RoboFleet is a fleet management and coordination system for autonomous agents. This repository contains the backend services and modules.

## Modules

### Fleet Check (`robofleet.fleet_check`)

A dedicated marker module for pre-demo end-to-end (E2E) testing. It exposes:
- `FLEET_CHECK_EPOCH`: An ISO 8601 UTC timestamp string designating the current active baseline execution epoch.

For full design details, importing instructions, and usage examples, see [Fleet Check Marker Module Documentation](docs/fleet_check.md).

### Tree Check (`robofleet.tree_check`)

A dedicated module for validation of tree structure and hierarchical consistency check. It exposes:
- `TREE_CHECK_EPOCH`: An ISO 8601 UTC timestamp string designating the active baseline tree check execution epoch.
- **CLI Entry Point**: Run `python -m robofleet.tree_check` to print the active epoch directly to standard output.

For full design details, importing instructions, and usage examples, see [Tree Check Module Documentation](docs/tree_check.md).

## Running Tests

To verify package integrity and unit test suite pass rates, run:

```bash
pytest
```

Specific test files can be executed individually:

```bash
pytest tests/unit/test_fleet_check.py
pytest tests/unit/tree_check_test.py
```
