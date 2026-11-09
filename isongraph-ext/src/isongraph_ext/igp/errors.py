"""The one exception type IGP/1 raises (21 §4.1)."""

from __future__ import annotations


class IGPError(Exception):
    def __init__(self, code: str, field: str, detail: str, step: str) -> None:
        super().__init__(f"{step} {code} {field}: {detail}")
        self.code = code
        self.field = field
        self.detail = detail
        self.step = step
