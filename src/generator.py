import argparse
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path
import pandas as pd

COLUMNS = ["event_id", "product_id", "event_type", "quantity", "event_timestamp",
           "warehouse_id", "from_warehouse_id", "to_warehouse_id"]

def generate(path, rows=1000, seed=42, include_edge_cases=True):
    rng = random.Random(seed)
    products = ["PROD001", "PROD002", "PROD003"]
    warehouses = ["WH001", "WH002", "WH003"]
    types = ["RECEIPT", "ISSUE", "TRANSFER", "ADJUSTMENT"]
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    records = []
    for i in range(rows):
        typ = rng.choice(types)
        record = {
            "event_id": f"EVT{i+1:08d}", "product_id": rng.choice(products),
            "event_type": typ, "quantity": rng.randint(1, 25),
            "event_timestamp": (start + timedelta(minutes=rng.randint(0, 60*24*90))).isoformat().replace("+00:00", "Z"),
            "warehouse_id": "", "from_warehouse_id": "", "to_warehouse_id": ""
        }
        if typ == "TRANSFER":
            source, dest = rng.sample(warehouses, 2)
            record["from_warehouse_id"], record["to_warehouse_id"] = source, dest
        else:
            record["warehouse_id"] = rng.choice(warehouses)
            if typ == "ADJUSTMENT" and rng.random() < 0.5:
                record["quantity"] = -record["quantity"]
        records.append(record)

    # Add labelled edge-case records separately from the expected-answer file.
    labels = []
    if include_edge_cases:
        bad = [
            {**records[0], "event_id": "INVALID-MISSING-PRODUCT", "product_id": ""},
            {**records[0], "event_id": "INVALID-UNKNOWN-WH", "warehouse_id": "WH999",
             "event_type": "RECEIPT", "from_warehouse_id": "", "to_warehouse_id": ""},
            {**records[0], "event_id": "INVALID-NEG-RECEIPT", "event_type": "RECEIPT",
             "quantity": -5, "warehouse_id": "WH001", "from_warehouse_id": "", "to_warehouse_id": ""},
        ]
        for item in bad:
            records.append(item)
            labels.append({"event_id": item["event_id"], "expected": "REJECT", "reason": "deliberate generator edge case"})
        duplicate = dict(records[1])
        duplicate["event_id"] = records[1]["event_id"]
        records.append(duplicate)
        labels.append({"event_id": duplicate["event_id"], "expected": "DUPLICATE_REJECT", "reason": "duplicate within file"})
        # Backdated event is appended last to exercise out-of-order arrival.
        late = dict(records[2])
        late["event_id"] = "LATE-BACKDATED-001"
        late["event_timestamp"] = "2026-01-02T09:00:00Z"
        records.append(late)
        labels.append({"event_id": late["event_id"], "expected": "ACCEPT_AND_BACKFILL", "reason": "late-arriving event"})
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(records, columns=COLUMNS).to_csv(path, index=False)
    labels_path = Path(path).with_name(Path(path).stem + "_expected_labels.json")
    labels_path.write_text(__import__("json").dumps(labels, indent=2))
    return path, labels_path

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--rows", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", default="data/generated_transactions.csv")
    args = parser.parse_args()
    out, labels = generate(args.output, args.rows, args.seed)
    print(f"Generated {out}; expected labels: {labels}")
