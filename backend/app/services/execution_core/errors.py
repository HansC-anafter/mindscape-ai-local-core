"""Shared execution-layer error types."""


class RecoverableStepError(Exception):
    """Temporary step failure that should return to pending for retry."""

    def __init__(self, step_id: str, error_type: str, detail: str):
        self.step_id = step_id
        self.error_type = error_type
        self.detail = detail
        super().__init__(
            f"Step {step_id} recoverable error [{error_type}]: {detail}"
        )
