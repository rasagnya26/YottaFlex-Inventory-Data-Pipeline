# Architecture / Data Flow

```text
CSV source / deterministic generator
              |
              v
      Pandas ingestion
              |
              v
   Schema + business validation
        /             \
       v               v
accepted rows      rejected_records
       |
       v
Reference integrity + event_id idempotency
       |
       v
Immutable SQLite inventory_events
       |
       v
Daily aggregate rebuild (supports backdated events)
       |
       v
Reconciliation + pipeline_runs metrics
       |
       v
Flask dashboard / SQL analytical consumer
```
