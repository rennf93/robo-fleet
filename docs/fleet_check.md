# Fleet Check Marker Module

The `robofleet.fleet_check` module is a small, lightweight module designed to expose marker constants for pre-demo end-to-end (E2E) checking and fleet synchronization validation.

## Purpose

To ensure that various nodes, components, and services across the fleet are aligned with the same baseline execution epoch, this module provides an easily importable timestamp constant. E2E check scripts and health endpoints can query this module to verify the current deployed epoch of the backend services.

## Constants

### `FLEET_CHECK_EPOCH`

- **Type**: `str`
- **Format**: ISO 8601 UTC string (e.g., `"2026-08-27T01:00:00Z"`)
- **Description**: The specific UTC timestamp serving as the pre-demo fleet check epoch identifier.

## Usage

### Importing and Reading the Epoch

You can import the module and access the constant directly in your application or testing scripts:

```python
from robofleet import fleet_check

# Access the epoch constant
epoch = fleet_check.FLEET_CHECK_EPOCH
print(f"Active Fleet Check Epoch: {epoch}")
```

### Parsing the Epoch in Python

The constant can be parsed into a standard `datetime` object. For safe compatibility across different Python versions (especially regarding the `Z` suffix), you can handle the timezone parsing as follows:

```python
from datetime import datetime
from robofleet import fleet_check

epoch_str = fleet_check.FLEET_CHECK_EPOCH

# Replace 'Z' with UTC offset '+00:00' if necessary
clean_epoch = epoch_str.replace("Z", "+00:00") if epoch_str.endswith("Z") else epoch_str

try:
    dt = datetime.fromisoformat(clean_epoch)
    print(f"Parsed datetime: {dt}")
except ValueError as e:
    print(f"Invalid ISO 8601 format: {e}")
```

## Testing

The integrity of this module is verified via unit tests located under `tests/unit/test_fleet_check.py`.

The unit tests assert that:
1. `FLEET_CHECK_EPOCH` exists and is a non-empty string.
2. The epoch string is a valid ISO 8601 format and can be correctly parsed using `datetime.fromisoformat`.

To run the unit tests, execute:
```bash
pytest tests/unit/test_fleet_check.py
```
