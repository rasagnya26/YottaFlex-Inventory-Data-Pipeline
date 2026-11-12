# Design and Trade-off Note

1. **SQLite over a cloud warehouse:** removes credential and infrastructure risk in a 72-hour take-home challenge while remaining reproducible locally.
2. **Pandas ingestion:** concise CSV parsing and data normalization; business rules remain explicit Python code.
3. **Immutable event ledger:** preserves event history and makes corrections auditable.
4. **Full daily rebuild:** simplest deterministic backfill strategy. It is intentionally chosen over incremental complexity for correctness at the target experience level.
5. **Event ID idempotency:** the primary key prevents duplicate accepted events; replays are counted as skipped.
6. **Quarantine rather than silent dropping:** each rejected row retains source file, row number, raw values, and reason.
7. **Global movement reconciliation:** validates aggregate movement arithmetic; transfer movements net to zero globally. Additional per-warehouse controls are a sensible next step.
8. **Flask dashboard:** gives reviewers a simple way to trigger ingestion and inspect outcomes without adding a heavy frontend.
