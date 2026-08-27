# Tree Check Module

The `robofleet.tree_check` module is a small, lightweight module designed to expose marker constants for validating tree structure alignment and hierarchical consistency checks.

## Purpose

To ensure that various nodes, components, and services across the fleet are aligned with the same baseline hierarchical validation epoch, this module provides an easily importable timestamp constant. System validation scripts and health endpoints can query this module to verify the current deployed epoch of the backend tree check services.

## Constants

### `TREE_CHECK_EPOCH`

- **Type**: `str`
- **Format**: ISO 8601 UTC string (e.g., `"2026-08-27T00:00:00Z"`)
- **Description**: The specific UTC timestamp serving as the active baseline tree check execution epoch identifier.

## Usage

### Importing and Reading the Epoch

You can import the module and access the constant directly in your application or testing scripts:

```python
from robofleet import tree_check

# Access the epoch constant
epoch = tree_check.TREE_CHECK_EPOCH
print(f"Active Tree Check Epoch: {epoch}")
```

### Parsing the Epoch in Python

The constant can be parsed into a standard `datetime` object. For safe compatibility across different Python versions (especially regarding the `Z` suffix), you can handle the timezone parsing as follows:

```python
from datetime import datetime
from robofleet import tree_check

epoch_str = tree_check.TREE_CHECK_EPOCH

# Replace 'Z' with UTC offset '+00:00' if necessary
clean_epoch = epoch_str.replace("Z", "+00:00") if epoch_str.endswith("Z") else epoch_str

try:
    dt = datetime.fromisoformat(clean_epoch)
    print(f"Parsed datetime: {dt}")
except ValueError as e:
    print(f"Invalid ISO 8601 format: {e}")
```

## Testing

The integrity of this module is verified via unit tests located under `tests/unit/tree_check_test.py`.

The unit tests assert that:
1. `TREE_CHECK_EPOCH` exists and is a non-empty string.
2. The epoch string is a valid ISO 8601 format and can be correctly parsed using `datetime.fromisoformat`.

To run the unit tests, execute:
```bash
pytest tests/unit/tree_check_test.py
```
