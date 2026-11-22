# isongraph-ext/src/isongraph_ext/igar/errors.py
"""The one exception type IGAR/1 raises (25 §3). Verification errors of igx/igdm/igdc are recorded INSIDE receipts, never raised by issue()."""
from __future__ import annotations


class IGARError(Exception):
    def __init__(self, code: str, field: str, detail: str, step: str) -> None:
        super().__init__(f"{step} {code} {field}: {detail}")
        self.code, self.field, self.detail, self.step = code, field, detail, step
