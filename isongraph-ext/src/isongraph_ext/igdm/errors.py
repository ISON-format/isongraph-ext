"""The one exception type IGDM/1 raises (19 §3.1). Admission denials are the binding's results, not exceptions."""

from __future__ import annotations


class IGDMError(Exception):
    def __init__(self, code: str, field: str, detail: str, step: str) -> None:
        super().__init__(f"{step} {code} {field}: {detail}")
        self.code = code
        self.field = field
        self.detail = detail
        self.step = step
