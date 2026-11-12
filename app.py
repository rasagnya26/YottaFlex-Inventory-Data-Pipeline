from pathlib import Path
from flask import Flask, request, redirect, url_for, render_template_string, flash
from config import DB_PATH, DATA_DIR, MAX_UPLOAD_BYTES
from src.database import init_db, connect
from src.pipeline import process_csv
from src.generator import generate

app = Flask(__name__)
app.secret_key = "local-development-only-change-me"
init_db(DB_PATH)

PAGE = """
<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Inventory Data Pipeline</title>
<style>
body{font-family:Arial,sans-serif;background:#f4f6fa;color:#182235;margin:0}
header{background:#10233f;color:white;padding:22px 5%}main{max-width:1150px;margin:24px auto;padding:0 18px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:14px}
.card{background:white;border:1px solid #dce2ec;border-radius:12px;padding:17px;margin-bottom:16px}
.metric{font-size:28px;font-weight:bold;color:#087e78}table{width:100%;border-collapse:collapse;background:white}
th,td{text-align:left;padding:10px;border-bottom:1px solid #e6eaf0;font-size:14px}
th{background:#edf2f8}.btn{background:#087e78;color:white;padding:10px 15px;border:0;border-radius:7px;cursor:pointer}
small,.muted{color:#667085}.flash{padding:10px;background:#e8f7f2;border-radius:8px;margin-bottom:12px}
</style></head><body>
<header><h1>Inventory Data Engineering Pipeline</h1><p>Receipts · Issues · Transfers · Adjustments · Reconciliation</p></header>
<main>
{% with messages = get_flashed_messages() %}{% for m in messages %}<div class="flash">{{m}}</div>{% endfor %}{% endwith %}
<div class="grid">
<div class="card"><small>Inventory rows</small><div class="metric">{{counts.inventory}}</div></div>
<div class="card"><small>Accepted events</small><div class="metric">{{counts.events}}</div></div>
<div class="card"><small>Rejected records</small><div class="metric">{{counts.rejects}}</div></div>
<div class="card"><small>Pipeline runs</small><div class="metric">{{counts.runs}}</div></div>
</div>
<div class="card"><h2>Run pipeline</h2>
<form action="/upload" method="post" enctype="multipart/form-data">
<input type="file" name="file" accept=".csv" required> <button class="btn">Upload and process CSV</button></form>
<p><small>Expected columns: event_id, product_id, event_type, quantity, event_timestamp, warehouse_id, from_warehouse_id, to_warehouse_id</small></p>
<form action="/generate" method="post"><label>Generate records: <input type="number" name="rows" value="1000" min="1" max="500000"></label>
<button class="btn">Generate and process synthetic data</button></form></div>
<div class="card"><h2>Daily inventory balances</h2><table><tr><th>Date</th><th>Product</th><th>Warehouse</th><th>Opening</th><th>Receipts</th><th>Issues</th><th>Transfers in</th><th>Transfers out</th><th>Adjustments</th><th>Closing</th></tr>
{% for r in inventory %}<tr>{% for v in r %}<td>{{v}}</td>{% endfor %}</tr>{% endfor %}</table></div>
<div class="card"><h2>Recent pipeline runs</h2><table><tr><th>Run ID</th><th>Source</th><th>Status</th><th>Input</th><th>Inserted</th><th>Skipped</th><th>Rejected</th><th>Duration (s)</th></tr>
{% for r in runs %}<tr>{% for v in r %}<td>{{v}}</td>{% endfor %}</tr>{% endfor %}</table></div>
<div class="card"><h2>Rejected records</h2><table><tr><th>Run</th><th>File</th><th>Row</th><th>Event</th><th>Reason</th></tr>
{% for r in rejects %}<tr>{% for v in r %}<td>{{v}}</td>{% endfor %}</tr>{% endfor %}</table></div>
<div class="card"><h2>Latest reconciliation</h2>{% if reconciliation %}
<p><b>Status:</b> {{ "PASS" if reconciliation[0] else "FAIL" }} · <b>Difference:</b> {{reconciliation[1]}} · <b>Rows:</b> {{reconciliation[2]}}</p>
{% else %}<p class="muted">No reconciliation has run yet.</p>{% endif %}</div>
</main></body></html>
"""

def dashboard_data():
    with connect(DB_PATH) as conn:
        counts = {
            "inventory": conn.execute("SELECT COUNT(*) FROM daily_inventory").fetchone()[0],
            "events": conn.execute("SELECT COUNT(*) FROM inventory_events").fetchone()[0],
            "rejects": conn.execute("SELECT COUNT(*) FROM rejected_records").fetchone()[0],
            "runs": conn.execute("SELECT COUNT(*) FROM pipeline_runs").fetchone()[0],
        }
        inventory = conn.execute("""SELECT business_date,product_id,warehouse_id,
            opening_quantity,receipts,issues,transfers_in,transfers_out,adjustments,closing_quantity
            FROM daily_inventory ORDER BY business_date DESC,product_id,warehouse_id LIMIT 100""").fetchall()
        runs = conn.execute("""SELECT run_id,source_file,status,input_count,inserted_count,
            skipped_count,rejected_count,ROUND(duration_seconds,4) FROM pipeline_runs
            ORDER BY started_at DESC LIMIT 10""").fetchall()
        rejects = conn.execute("""SELECT run_id,source_file,source_row_number,event_id,reason
            FROM rejected_records ORDER BY reject_id DESC LIMIT 20""").fetchall()
        rec = conn.execute("""SELECT passed,difference,movement_rows FROM reconciliation_reports
            ORDER BY report_id DESC LIMIT 1""").fetchone()
        return counts, inventory, runs, rejects, rec

@app.route("/")
def index():
    counts, inventory, runs, rejects, rec = dashboard_data()
    return render_template_string(PAGE, counts=counts, inventory=inventory, runs=runs,
                                  rejects=rejects, reconciliation=rec)

@app.route("/upload", methods=["POST"])
def upload():
    f = request.files.get("file")
    if not f or not f.filename.lower().endswith(".csv"):
        flash("Please choose a CSV file.")
        return redirect(url_for("index"))
    content = f.read()
    if len(content) > MAX_UPLOAD_BYTES:
        flash("Upload exceeds 10 MB. Use the generator or split the input.")
        return redirect(url_for("index"))
    path = DATA_DIR / Path(f.filename).name
    path.write_bytes(content)
    try:
        result = process_csv(path, DB_PATH)
        flash(f"{result['status']}: inserted {result['inserted_count']}, skipped {result['skipped_count']}, rejected {result['rejected_count']}. Run {result['run_id']}")
    except Exception as exc:
        flash(f"Pipeline failed: {exc}")
    return redirect(url_for("index"))

@app.route("/generate", methods=["POST"])
def generate_and_run():
    rows = max(1, min(int(request.form.get("rows", 1000)), 500000))
    path = DATA_DIR / "generated_transactions.csv"
    generate(path, rows=rows, seed=42, include_edge_cases=True)
    try:
        result = process_csv(path, DB_PATH)
        flash(f"{result['status']}: inserted {result['inserted_count']}, skipped {result['skipped_count']}, rejected {result['rejected_count']}. Run {result['run_id']}")
    except Exception as exc:
        flash(f"Pipeline failed: {exc}")
    return redirect(url_for("index"))

if __name__ == "__main__":
    app.run(debug=True, host="127.0.0.1", port=5000)
