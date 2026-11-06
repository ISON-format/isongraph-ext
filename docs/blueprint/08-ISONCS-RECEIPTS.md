# ISONCS Receipt Integration

ISONCS is the integrity/canonicalization layer, not a second graph model.

Receipt chains:
- source graph digest + projection policy digest -> result graph digest;
- source graph digest + DAG policy digest -> DAG graph digest;
- base revision digest + delta digest -> result revision digest.

Receipts include spec/runtime version, source identity, policy/extension identity, result identity and explicit status/failure posture.
