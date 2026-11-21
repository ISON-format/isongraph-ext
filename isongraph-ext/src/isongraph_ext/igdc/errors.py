# isongraph-ext/src/isongraph_ext/igdc/errors.py
"""The one exception type IGDC/1 raises (26 §4). Verification and admission errors of igx/igdm propagate unwrapped."""
from __future__ import annotations


class IGDCError(Exception):
    def __init__(self, code: str, field: str, detail: str, step: str) -> None:
        super().__init__(f"{step} {code} {field}: {detail}")
        self.code, self.field, self.detail, self.step = code, field, detail, step
