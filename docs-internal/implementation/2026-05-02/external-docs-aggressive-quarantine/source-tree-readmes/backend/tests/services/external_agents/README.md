# External Agents Tests

Unit tests for the external agent framework.

## Running Tests

```bash
# Run all external agent tests
pytest backend/tests/services/external_agents/ -v

# Run only unit tests (no OpenClaw required)
pytest backend/tests/services/external_agents/ -v -m "not openclaw_required"
```

## Test Files

- `test_openclaw_adapter.py` - Unit tests for OpenClawAdapter
