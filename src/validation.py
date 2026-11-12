import json
import math
import pandas as pd

REQUIRED_COLUMNS = {
    "event_id", "product_id", "event_type", "quantity", "event_timestamp",
    "warehouse_id", "from_warehouse_id", "to_warehouse_id"
}
ALLOWED_TYPES = {"RECEIPT", "ISSUE", "TRANSFER", "ADJUSTMENT"}

def validate_frame(frame):
    """Return normalized rows and explicit file-level schema errors."""
    missing = REQUIRED_COLUMNS - set(frame.columns)
    unexpected = set(frame.columns) - REQUIRED_COLUMNS
    if missing or unexpected:
        parts = []
        if missing:
            parts.append("Missing required columns: " + ", ".join(sorted(missing)))
        if unexpected:
            parts.append("Unexpected columns: " + ", ".join(sorted(unexpected)))
        return [], [{"row_number": 0, "event_id": None,
                     "reason": "; ".join(parts), "raw": {"columns": list(frame.columns)}}]

    accepted, rejected = [], []
    seen_in_file = set()

    for idx, row in frame.iterrows():
        row_number = int(idx) + 2  # CSV header is row 1
        raw = {k: (None if pd.isna(v) else v) for k, v in row.to_dict().items()}
        event_id = str(raw.get("event_id") or "").strip()
        reason = None

        if not event_id:
            reason = "event_id is required"
        elif event_id in seen_in_file:
            reason = "duplicate event_id within input file"
        else:
            seen_in_file.add(event_id)

        product_id = str(raw.get("product_id") or "").strip()
        event_type = str(raw.get("event_type") or "").strip().upper()
        if reason is None and not product_id:
            reason = "product_id is required"
        if reason is None and event_type not in ALLOWED_TYPES:
            reason = f"event_type must be one of {sorted(ALLOWED_TYPES)}"

        try:
            quantity = float(raw.get("quantity"))
            if not math.isfinite(quantity):
                raise ValueError()
        except (TypeError, ValueError):
            quantity = None
            if reason is None:
                reason = "quantity must be a finite number"

        if reason is None and event_type in {"RECEIPT", "ISSUE", "TRANSFER"} and quantity <= 0:
            reason = f"{event_type} quantity must be greater than zero"
        if reason is None and event_type == "ADJUSTMENT" and quantity == 0:
            reason = "ADJUSTMENT quantity must be non-zero (positive or negative)"

        timestamp = str(raw.get("event_timestamp") or "").strip()
        try:
            parsed = pd.to_datetime(timestamp, errors="raise", utc=True)
            timestamp = parsed.isoformat().replace("+00:00", "Z")
        except Exception:
            if reason is None:
                reason = "event_timestamp must be a valid ISO-8601 timestamp"

        warehouse_id = str(raw.get("warehouse_id") or "").strip() or None
        from_id = str(raw.get("from_warehouse_id") or "").strip() or None
        to_id = str(raw.get("to_warehouse_id") or "").strip() or None

        if reason is None:
            if event_type == "TRANSFER":
                if not from_id or not to_id:
                    reason = "TRANSFER requires from_warehouse_id and to_warehouse_id"
                elif from_id == to_id:
                    reason = "TRANSFER source and destination must differ"
                elif warehouse_id:
                    reason = "TRANSFER must leave warehouse_id blank"
            else:
                if not warehouse_id:
                    reason = f"{event_type} requires warehouse_id"
                elif from_id or to_id:
                    reason = f"{event_type} must not use transfer warehouse fields"

        normalized = {
            "event_id": event_id, "product_id": product_id, "event_type": event_type,
            "quantity": quantity, "event_timestamp": timestamp, "warehouse_id": warehouse_id,
            "from_warehouse_id": from_id, "to_warehouse_id": to_id
        }
        if reason:
            rejected.append({"row_number": row_number, "event_id": event_id or None,
                             "reason": reason, "raw": raw})
        else:
            accepted.append({"row_number": row_number, "data": normalized, "raw": raw})
    return accepted, rejected

def raw_json(value):
    return json.dumps(value, default=str, sort_keys=True)
