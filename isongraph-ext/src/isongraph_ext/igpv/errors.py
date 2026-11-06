"""The one exception type IGPV/1 raises (18 §5.3). Admission denials are the binding's results, not exceptions."""

from __future__ import annotations


class IGPVError(Exception):
    """A verification failure: deterministic code, offending field, human detail, and the step that fired."""

    def __init__(self, code: str, field: str, detail: str, step: str) -> None:
        super().__init__(f"{step} {code} {field}: {detail}")
        self.code = code
        self.field = field
        self.detail = detail
        self.step = step
