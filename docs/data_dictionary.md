# Data Dictionary

## Source event CSV

| Field | Type | Nullable | Rule |
|---|---|---:|---|
| event_id | string | No | Stable global unique event key |
| product_id | string | No | FK to products |
| event_type | enum | No | RECEIPT / ISSUE / TRANSFER / ADJUSTMENT |
| quantity | real | No | Positive movement; signed non-zero adjustment |
| event_timestamp | ISO-8601 string | No | Normalized to UTC |
| warehouse_id | string | Conditional | Required except transfer |
| from_warehouse_id | string | Conditional | Transfer source only |
| to_warehouse_id | string | Conditional | Transfer destination only |

## Target tables

- `products(product_id PK, product_name)`
- `warehouses(warehouse_id PK, warehouse_name)`
- `inventory_events(event_id PK, product_id FK, event attributes, source_file, run_id, ingested_at)`
- `daily_inventory(business_date, product_id, warehouse_id composite PK, opening/movement/closing quantities)`
- `rejected_records(reject_id PK, run_id, source_file, source_row_number, event_id, reason, raw_record)`
- `pipeline_runs(run_id PK, source_file, hash, status, timestamps, counts, failure reason, duration)`
- `reconciliation_reports(report_id PK, run_id, totals, difference, pass/fail, details)`

Daily grain: business date × product × warehouse. Event grain: one source movement event. Transfer events create two warehouse-side movements in the daily aggregate while remaining one immutable source event.
