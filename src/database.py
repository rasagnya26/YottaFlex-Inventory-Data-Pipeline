import sqlite3
from pathlib import Path

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS products (
    product_id TEXT PRIMARY KEY,
    product_name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS warehouses (
    warehouse_id TEXT PRIMARY KEY,
    warehouse_name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS inventory_events (
    event_id TEXT PRIMARY KEY,
    product_id TEXT NOT NULL,
    event_type TEXT NOT NULL CHECK(event_type IN ('RECEIPT','ISSUE','TRANSFER','ADJUSTMENT')),
    quantity REAL NOT NULL,
    event_timestamp TEXT NOT NULL,
    warehouse_id TEXT,
    from_warehouse_id TEXT,
    to_warehouse_id TEXT,
    source_file TEXT NOT NULL,
    run_id TEXT NOT NULL,
    ingested_at TEXT NOT NULL,
    FOREIGN KEY(product_id) REFERENCES products(product_id),
    FOREIGN KEY(warehouse_id) REFERENCES warehouses(warehouse_id),
    FOREIGN KEY(from_warehouse_id) REFERENCES warehouses(warehouse_id),
    FOREIGN KEY(to_warehouse_id) REFERENCES warehouses(warehouse_id)
);

CREATE INDEX IF NOT EXISTS idx_events_product_date
ON inventory_events(product_id, event_timestamp);

CREATE INDEX IF NOT EXISTS idx_events_warehouse_date
ON inventory_events(warehouse_id, event_timestamp);

CREATE TABLE IF NOT EXISTS rejected_records (
    reject_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    source_file TEXT NOT NULL,
    source_row_number INTEGER NOT NULL,
    event_id TEXT,
    reason TEXT NOT NULL,
    raw_record TEXT NOT NULL,
    rejected_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS pipeline_runs (
    run_id TEXT PRIMARY KEY,
    source_file TEXT NOT NULL,
    file_hash TEXT,
    status TEXT NOT NULL,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    input_count INTEGER NOT NULL DEFAULT 0,
    inserted_count INTEGER NOT NULL DEFAULT 0,
    skipped_count INTEGER NOT NULL DEFAULT 0,
    rejected_count INTEGER NOT NULL DEFAULT 0,
    error_message TEXT,
    duration_seconds REAL
);

CREATE TABLE IF NOT EXISTS daily_inventory (
    business_date TEXT NOT NULL,
    product_id TEXT NOT NULL,
    warehouse_id TEXT NOT NULL,
    opening_quantity REAL NOT NULL,
    receipts REAL NOT NULL,
    issues REAL NOT NULL,
    transfers_in REAL NOT NULL,
    transfers_out REAL NOT NULL,
    adjustments REAL NOT NULL,
    closing_quantity REAL NOT NULL,
    last_rebuilt_at TEXT NOT NULL,
    PRIMARY KEY(business_date, product_id, warehouse_id),
    FOREIGN KEY(product_id) REFERENCES products(product_id),
    FOREIGN KEY(warehouse_id) REFERENCES warehouses(warehouse_id)
);

CREATE TABLE IF NOT EXISTS reconciliation_reports (
    report_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    checked_at TEXT NOT NULL,
    movement_rows INTEGER NOT NULL,
    ledger_net_movement REAL NOT NULL,
    daily_net_movement REAL NOT NULL,
    difference REAL NOT NULL,
    passed INTEGER NOT NULL,
    details TEXT NOT NULL
);
"""

def connect(db_path):
    conn = sqlite3.connect(str(db_path), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn

def init_db(db_path):
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    with connect(db_path) as conn:
        conn.executescript(SCHEMA)
        conn.executemany(
            "INSERT OR IGNORE INTO products(product_id, product_name) VALUES (?, ?)",
            [("PROD001", "Laptop"), ("PROD002", "Monitor"), ("PROD003", "Keyboard")]
        )
        conn.executemany(
            "INSERT OR IGNORE INTO warehouses(warehouse_id, warehouse_name) VALUES (?, ?)",
            [("WH001", "Hyderabad Central"), ("WH002", "Bengaluru Hub"), ("WH003", "Chennai Hub")]
        )
