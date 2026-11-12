# YottaFlex Inventory Data Engineering Challenge

A local, reproducible inventory movement pipeline for receipts, issues, transfers, and signed adjustments. It validates source CSV data, quarantines invalid records, stores immutable accepted events in SQLite, rebuilds daily balances (including late/backdated events), records operational metrics, and reconciles movement totals.

## Technology
- Python 3.10+
- Pandas for CSV ingestion and normalization
- SQLite for event history, daily aggregates, rejects, and run metadata
- Flask for a lightweight local dashboard/API surface
- Pytest for automated tests

## Quick start (VS Code / terminal)

```bash
python -m venv .venv
# Windows PowerShell:
.venv\\Scripts\\Activate.ps1
# macOS/Linux:
source .venv/bin/activate

pip install -r requirements.txt
python -m src.generator --rows 1000 --seed 42
pytest -q
python app.py
```

Open http://127.0.0.1:5000.

The dashboard can upload a CSV or generate and process synthetic data. Default database is `inventory.db`; override with `DB_PATH`. `DATA_DIR` and `OUTPUT_DIR` can also be configured using environment variables.

## CSV input contract

Required columns (exact names):
`event_id, product_id, event_type, quantity, event_timestamp, warehouse_id, from_warehouse_id, to_warehouse_id`

- `event_id`: stable, globally unique event key.
- `product_id`: must exist in `products`.
- `event_type`: `RECEIPT`, `ISSUE`, `TRANSFER`, or `ADJUSTMENT`.
- `quantity`: positive for receipt/issue/transfer; non-zero signed number for adjustment.
- `event_timestamp`: parseable timestamp; normalized to UTC ISO-8601.
- `warehouse_id`: required for receipt, issue, adjustment; blank for transfer.
- `from_warehouse_id`, `to_warehouse_id`: required only for transfer and must differ.
- Reference data is seeded with PROD001–PROD003 and WH001–WH003. Extend `products` and `warehouses` for your own reference data.

## Movement semantics

| Event | Source warehouse effect | Destination / warehouse effect |
|---|---:|---:|
| RECEIPT | — | `+quantity` at `warehouse_id` |
| ISSUE | `-quantity` at `warehouse_id` | — |
| TRANSFER | `-quantity` at `from_warehouse_id` | `+quantity` at `to_warehouse_id` |
| ADJUSTMENT | signed `quantity` at `warehouse_id` | — |

Daily grain: one row per `business_date × product_id × warehouse_id`. Opening quantity is the prior day's closing balance for that product and warehouse; closing = opening + receipts − issues + transfers_in − transfers_out + adjustments. The first observed movement date starts at zero unless an opening stock is represented by an `ADJUSTMENT` event.

## Architecture

1. Ingest CSV using Pandas.
2. Validate exact schema, required values, event types, numeric quantity, timestamp format, and event-specific warehouse rules.
3. Check product and warehouse reference integrity.
4. Store accepted events once in immutable `inventory_events`; store invalid source rows and reasons in `rejected_records`.
5. Rebuild `daily_inventory` deterministically from the event ledger. This full rebuild naturally handles out-of-order and backdated events.
6. Reconcile ledger net movement against daily net movement; persist report and run metrics.

## Idempotency, retry, and backfill

- `event_id` is the global idempotency key (primary key).
- Reprocessing an already accepted event is counted as `skipped`, not inserted again.
- Duplicate event IDs within the same file are quarantined after the first occurrence.
- Each execution gets a new `run_id`; run status, timestamps, counts, duration, and error message are persisted.
- Row-level invalid data does not prevent valid rows from being processed.
- A malformed file schema is recorded as a rejected batch-level issue; no events from that file are inserted.
- Re-running the same file is safe. For a failed process, fix the source or environment issue and retry; previously committed event IDs are skipped.
- A late event is appended to the immutable ledger, after which the daily aggregate is rebuilt so all subsequent dates reflect the correction.

## Tests

```bash
pytest -q
```

Coverage includes happy path, empty input, invalid quantities, missing required values, duplicate keys, unknown references, unexpected schema, same-file rerun, transfer accounting, negative adjustment, backdated event rebuild, and deterministic generator output.

## Synthetic data and performance

```bash
python -m src.generator --rows 100000 --seed 42
```

The generator writes `data/generated_transactions.csv` and a separate `data/generated_transactions_expected_labels.json` file for deliberately injected edge cases. Labels are not mixed into source input.

For a simple benchmark, run:

```bash
python scripts/benchmark.py --rows 100000
```

The benchmark reports elapsed time, input rows, inserted rows, rejected rows, and throughput. Results depend on local hardware and should be recorded with the submission.

## Reconciliation query

```sql
SELECT
  SUM(receipts - issues + transfers_in - transfers_out + adjustments) AS daily_net_movement
FROM daily_inventory;
```

Compare this with the event ledger global net movement. Transfers contribute zero globally because source-out and destination-in cancel.

## Known limitations and trade-offs

- Full aggregate rebuild is easy to reason about and correct for this challenge, but may become expensive for very large histories. Production optimization: identify earliest affected date and rebuild only impacted product/warehouse partitions.
- The Flask app is a local review dashboard, not production-hardened. Do not expose it publicly without authentication, CSRF protection, upload scanning, and deployment hardening.
- Starter product and warehouse reference data is seeded for reproducibility. Real deployments should ingest governed master data.
- Global reconciliation is complemented by transfer source/destination accounting in the daily aggregate; a production system should add per-event and per-warehouse control totals.
- Quantities use floating point for simple examples. For fractional inventory with strict financial-grade precision, use integer base units or Decimal-backed storage.

## AI usage and authorship

AI tools may be used under the challenge FAQ. Keep a truthful prompt log in `PROMPTS.md`, review all generated code, run the tests, and be prepared to explain every design decision. Update the prompt log with the actual prompts and tools you used.
