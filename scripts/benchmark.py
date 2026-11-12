import argparse
import tempfile
import time
from pathlib import Path
from src.generator import generate
from src.pipeline import process_csv

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--rows", type=int, default=100000)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as tmp:
        csv = Path(tmp) / "benchmark.csv"
        db = Path(tmp) / "benchmark.db"
        generate(csv, rows=args.rows, seed=42, include_edge_cases=True)
        start = time.perf_counter()
        result = process_csv(csv, db)
        elapsed = time.perf_counter() - start
        print({
            "requested_rows": args.rows,
            "input_rows_including_edge_cases": result["input_count"],
            "inserted": result["inserted_count"],
            "rejected": result["rejected_count"],
            "elapsed_seconds": round(elapsed, 3),
            "rows_per_second": round(result["input_count"] / elapsed, 2),
            "status": result["status"]
        })

if __name__ == "__main__":
    main()
