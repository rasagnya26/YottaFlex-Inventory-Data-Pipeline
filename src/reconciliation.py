from datetime import datetime, timezone

def reconcile(conn, run_id):
    # Sum of movement ledger and sum of daily net movements must agree globally.
    ledger = conn.execute("""
        SELECT COALESCE(SUM(
            CASE event_type
              WHEN 'RECEIPT' THEN quantity
              WHEN 'ISSUE' THEN -quantity
              WHEN 'ADJUSTMENT' THEN quantity
              WHEN 'TRANSFER' THEN 0
            END
        ), 0) AS net
        FROM inventory_events
    """).fetchone()["net"]

    daily = conn.execute("""
        SELECT COALESCE(SUM(receipts - issues + transfers_in - transfers_out + adjustments), 0) AS net
        FROM daily_inventory
    """).fetchone()["net"]

    rows = conn.execute("SELECT COUNT(*) AS n FROM inventory_events").fetchone()["n"]
    difference = float(ledger) - float(daily)
    passed = abs(difference) < 1e-8
    details = (
        "Global net movement reconciles. Transfers are neutral globally because "
        "each transfer creates equal source-out and destination-in movements."
        if passed else "Global movement totals differ; inspect event ledger and daily aggregation."
    )
    conn.execute("""
        INSERT INTO reconciliation_reports(
            run_id, checked_at, movement_rows, ledger_net_movement,
            daily_net_movement, difference, passed, details
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (run_id, datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
          rows, float(ledger), float(daily), difference, int(passed), details))
    return {"passed": passed, "movement_rows": rows, "ledger_net_movement": float(ledger),
            "daily_net_movement": float(daily), "difference": difference, "details": details}
