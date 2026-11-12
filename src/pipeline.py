import hashlib
import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd

from src.database import connect, init_db
from src.validation import validate_frame, raw_json
from src.inventory_calculation import rebuild_daily_inventory
from src.reconciliation import reconcile

def utc_now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

def process_csv(csv_path, db_path):
    csv_path = Path(csv_path)
    run_id = "RUN-" + uuid.uuid4().hex[:12].upper()
    started = time.perf_counter()
    started_at = utc_now()
    source_file = csv_path.name

    init_db(db_path)
    file_hash = hashlib.sha256(csv_path.read_bytes()).hexdigest()

    with connect(db_path) as conn:
        conn.execute("""
            INSERT INTO pipeline_runs(run_id, source_file, file_hash, status, started_at)
            VALUES (?, ?, ?, 'RUNNING', ?)
        """, (run_id, source_file, file_hash, started_at))

    try:
        frame = pd.read_csv(csv_path, dtype=str, keep_default_na=False)
        accepted, rejected = validate_frame(frame)
        inserted = skipped = rejected_count = 0

        with connect(db_path) as conn:
            for item in accepted:
                data = item["data"]
                # Already committed event IDs are treated as idempotent skips, not new rejects.
                exists = conn.execute(
                    "SELECT 1 FROM inventory_events WHERE event_id = ?", (data["event_id"],)
                ).fetchone()
                if exists:
                    skipped += 1
                    continue

                # Referential integrity is checked explicitly so the source row is quarantined.
                refs_ok = conn.execute("SELECT 1 FROM products WHERE product_id = ?",
                                       (data["product_id"],)).fetchone()
                if data["event_type"] == "TRANSFER":
                    refs_ok = refs_ok and conn.execute(
                        "SELECT 1 FROM warehouses WHERE warehouse_id = ?", (data["from_warehouse_id"],)
                    ).fetchone() and conn.execute(
                        "SELECT 1 FROM warehouses WHERE warehouse_id = ?", (data["to_warehouse_id"],)
                    ).fetchone()
                else:
                    refs_ok = refs_ok and conn.execute(
                        "SELECT 1 FROM warehouses WHERE warehouse_id = ?", (data["warehouse_id"],)
                    ).fetchone()

                if not refs_ok:
                    rejected.append({
                        "row_number": item["row_number"], "event_id": data["event_id"],
                        "reason": "unknown product_id or warehouse reference", "raw": item["raw"]
                    })
                    continue

                conn.execute("""
                    INSERT INTO inventory_events(
                        event_id, product_id, event_type, quantity, event_timestamp,
                        warehouse_id, from_warehouse_id, to_warehouse_id,
                        source_file, run_id, ingested_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (data["event_id"], data["product_id"], data["event_type"], data["quantity"],
                      data["event_timestamp"], data["warehouse_id"], data["from_warehouse_id"],
                      data["to_warehouse_id"], source_file, run_id, utc_now()))
                inserted += 1

            for item in rejected:
                conn.execute("""
                    INSERT INTO rejected_records(
                        run_id, source_file, source_row_number, event_id, reason, raw_record, rejected_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (run_id, source_file, item["row_number"], item.get("event_id"),
                      item["reason"], raw_json(item["raw"]), utc_now()))
            rejected_count = len(rejected)

            # Rebuild from full event history: late/backdated records update all subsequent balances.
            rebuild_daily_inventory(conn)
            report = reconcile(conn, run_id)

            status = "SUCCESS" if rejected_count == 0 else "SUCCESS_WITH_REJECTS"
            if not report["passed"]:
                status = "FAILED"
            duration = time.perf_counter() - started
            conn.execute("""
                UPDATE pipeline_runs
                SET status=?, ended_at=?, input_count=?, inserted_count=?, skipped_count=?,
                    rejected_count=?, error_message=?, duration_seconds=?
                WHERE run_id=?
            """, (status, utc_now(), len(frame), inserted, skipped, rejected_count,
                  None if report["passed"] else report["details"], duration, run_id))

        return {
            "run_id": run_id, "status": status, "input_count": len(frame),
            "inserted_count": inserted, "skipped_count": skipped,
            "rejected_count": rejected_count, "duration_seconds": round(duration, 4),
            "reconciliation": report
        }
    except Exception as exc:
        duration = time.perf_counter() - started
        with connect(db_path) as conn:
            conn.execute("""
                UPDATE pipeline_runs SET status='FAILED', ended_at=?, error_message=?,
                    duration_seconds=? WHERE run_id=?
            """, (utc_now(), str(exc), duration, run_id))
        raise
