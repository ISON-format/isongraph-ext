"""The one exception type IGX/1 raises. Admission denials are results, not exceptions (17 §3)."""

from __future__ import annotations


class IGXError(Exception):
    """A verification failure: deterministic code, offending field, human detail, and the step that fired."""

    def __init__(self, code: str, field: str, detail: str, step: str) -> None:
        super().__init__(f"{step} {code} {field}: {detail}")
        self.code = code
        self.field = field
        self.detail = detail
        self.step = step
