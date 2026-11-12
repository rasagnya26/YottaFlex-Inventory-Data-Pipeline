import pandas as pd
from src.pipeline import process_csv
from src.database import connect

COLS = ["event_id","product_id","event_type","quantity","event_timestamp",
        "warehouse_id","from_warehouse_id","to_warehouse_id"]

def write_csv(path, rows, columns=COLS):
    pd.DataFrame(rows, columns=columns).to_csv(path, index=False)

def row(eid, typ, qty, date="2026-11-10T10:00:00Z", wh="WH001",
        src="", dst="", product="PROD001"):
    return [eid, product, typ, qty, date, wh, src, dst]

def test_receipt_issue_transfer_and_reconciliation(tmp_path, db_path):
    csv = tmp_path / "happy.csv"
    write_csv(csv, [
        row("E1","RECEIPT",100),
        row("E2","ISSUE",20),
        row("E3","TRANSFER",30,wh="",src="WH001",dst="WH002"),
    ])
    result = process_csv(csv, db_path)
    assert result["status"] == "SUCCESS"
    assert result["reconciliation"]["passed"]
    with connect(db_path) as conn:
        a = conn.execute("SELECT closing_quantity FROM daily_inventory WHERE warehouse_id='WH001'").fetchone()[0]
        b = conn.execute("SELECT closing_quantity FROM daily_inventory WHERE warehouse_id='WH002'").fetchone()[0]
    assert a == 50
    assert b == 30

def test_empty_input(tmp_path, db_path):
    csv = tmp_path / "empty.csv"
    write_csv(csv, [])
    result = process_csv(csv, db_path)
    assert result["input_count"] == 0
    assert result["status"] == "SUCCESS"

def test_malformed_and_missing_required_field_quarantined(tmp_path, db_path):
    csv = tmp_path / "bad.csv"
    write_csv(csv, [
        row("E1","RECEIPT",-2),
        row("E2","RECEIPT",4,product=""),
    ])
    result = process_csv(csv, db_path)
    assert result["rejected_count"] == 2

def test_duplicate_event_within_file_rejected(tmp_path, db_path):
    csv = tmp_path / "dupe.csv"
    r = row("E1","RECEIPT",10)
    write_csv(csv, [r, r])
    result = process_csv(csv, db_path)
    assert result["inserted_count"] == 1
    assert result["rejected_count"] == 1

def test_same_file_rerun_is_idempotent(tmp_path, db_path):
    csv = tmp_path / "rerun.csv"
    write_csv(csv, [row("E1","RECEIPT",10)])
    first = process_csv(csv, db_path)
    second = process_csv(csv, db_path)
    assert first["inserted_count"] == 1
    assert second["inserted_count"] == 0
    assert second["skipped_count"] == 1
    with connect(db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM inventory_events").fetchone()[0] == 1

def test_unknown_reference_rejected(tmp_path, db_path):
    csv = tmp_path / "ref.csv"
    write_csv(csv, [row("E1","RECEIPT",10,wh="WH999")])
    result = process_csv(csv, db_path)
    assert result["rejected_count"] == 1

def test_backdated_event_rebuilds_following_days(tmp_path, db_path):
    csv1 = tmp_path / "first.csv"
    write_csv(csv1, [
        row("E1","RECEIPT",100,"2026-11-10T10:00:00Z"),
        row("E2","ISSUE",20,"2026-11-12T10:00:00Z"),
    ])
    process_csv(csv1, db_path)
    csv2 = tmp_path / "late.csv"
    write_csv(csv2, [row("E3","RECEIPT",10,"2026-11-11T10:00:00Z")])
    process_csv(csv2, db_path)
    with connect(db_path) as conn:
        nov12 = conn.execute("SELECT closing_quantity FROM daily_inventory WHERE business_date='2026-11-12' AND warehouse_id='WH001'").fetchone()[0]
    assert nov12 == 90

def test_unexpected_schema_change_fails_batch_and_is_logged(tmp_path, db_path):
    csv = tmp_path / "schema.csv"
    write_csv(csv, [row("E1","RECEIPT",10) + ["unexpected"]], columns=COLS + ["surprise_column"])
    result = process_csv(csv, db_path)
    assert result["rejected_count"] == 1
    with connect(db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM rejected_records").fetchone()[0] == 1

def test_adjustment_can_be_negative(tmp_path, db_path):
    csv = tmp_path / "adjust.csv"
    write_csv(csv, [row("E1","RECEIPT",10), row("E2","ADJUSTMENT",-3)])
    process_csv(csv, db_path)
    with connect(db_path) as conn:
        closing = conn.execute("SELECT closing_quantity FROM daily_inventory WHERE warehouse_id='WH001'").fetchone()[0]
    assert closing == 7


def test_partial_batch_and_retry(tmp_path, db_path):
    csv = tmp_path / "partial.csv"
    write_csv(csv, [
        row("GOOD-1","RECEIPT",25),
        row("BAD-1","RECEIPT",10,wh="WH404"),
    ])
    first = process_csv(csv, db_path)
    assert first["inserted_count"] == 1
    assert first["rejected_count"] == 1

    # After correcting the invalid reference, retry the batch: accepted event is skipped,
    # and a corrected event with a new stable ID can be ingested.
    corrected = tmp_path / "retry.csv"
    write_csv(corrected, [
        row("GOOD-1","RECEIPT",25),
        row("FIXED-1","RECEIPT",10,wh="WH002"),
    ])
    second = process_csv(corrected, db_path)
    assert second["inserted_count"] == 1
    assert second["skipped_count"] == 1
    with connect(db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM inventory_events").fetchone()[0] == 2
