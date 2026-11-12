from datetime import datetime, timezone
from collections import defaultdict

def rebuild_daily_inventory(conn):
    """
    Deterministically rebuild daily balances from immutable event history.
    Rebuilding all dates is intentionally simple and safe for this challenge;
    a production optimization would rebuild only affected product/warehouse/date ranges.
    """
    events = conn.execute("""
        SELECT event_id, product_id, event_type, quantity, event_timestamp,
               warehouse_id, from_warehouse_id, to_warehouse_id
        FROM inventory_events
        ORDER BY event_timestamp, event_id
    """).fetchall()

    daily = defaultdict(lambda: {
        "receipts": 0.0, "issues": 0.0, "transfers_in": 0.0,
        "transfers_out": 0.0, "adjustments": 0.0
    })
    keys = set()

    for e in events:
        date = e["event_timestamp"][:10]
        product = e["product_id"]
        typ = e["event_type"]
        qty = float(e["quantity"])
        if typ == "RECEIPT":
            key = (date, product, e["warehouse_id"])
            daily[key]["receipts"] += qty
            keys.add((product, e["warehouse_id"]))
        elif typ == "ISSUE":
            key = (date, product, e["warehouse_id"])
            daily[key]["issues"] += qty
            keys.add((product, e["warehouse_id"]))
        elif typ == "ADJUSTMENT":
            key = (date, product, e["warehouse_id"])
            daily[key]["adjustments"] += qty
            keys.add((product, e["warehouse_id"]))
        elif typ == "TRANSFER":
            out_key = (date, product, e["from_warehouse_id"])
            in_key = (date, product, e["to_warehouse_id"])
            daily[out_key]["transfers_out"] += qty
            daily[in_key]["transfers_in"] += qty
            keys.add((product, e["from_warehouse_id"]))
            keys.add((product, e["to_warehouse_id"]))

    by_product_warehouse = defaultdict(list)
    for (date, product, warehouse), movements in daily.items():
        by_product_warehouse[(product, warehouse)].append((date, movements))

    rows = []
    rebuilt_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    for (product, warehouse), days in by_product_warehouse.items():
        running = 0.0
        for date, m in sorted(days, key=lambda x: x[0]):
            opening = running
            net = (m["receipts"] - m["issues"] + m["transfers_in"]
                   - m["transfers_out"] + m["adjustments"])
            running = opening + net
            rows.append((date, product, warehouse, opening, m["receipts"], m["issues"],
                         m["transfers_in"], m["transfers_out"], m["adjustments"],
                         running, rebuilt_at))

    conn.execute("DELETE FROM daily_inventory")
    conn.executemany("""
        INSERT INTO daily_inventory(
            business_date, product_id, warehouse_id, opening_quantity, receipts, issues,
            transfers_in, transfers_out, adjustments, closing_quantity, last_rebuilt_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, rows)
    return len(rows)
