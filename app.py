from flask import Flask, request, render_template_string, Response
import requests
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

app = Flask(__name__)

API_URL = "https://resultapi.biharboardonline.org/result"
CACHE = {}
SUBJECT_LIST = ["HINDI", "SANSKRIT", "MATHEMATICS", "SCIENCE", "SOCIAL SCIENCE", "ENGLISH"]

# ---------------- FETCH FUNCTION ----------------
def fetch_result(roll_code, roll_no):
    params = {"roll_code": roll_code, "roll_no": roll_no}
    headers = {"User-Agent": "Mozilla/5.0"}

    for attempt in range(2):
        try:
            response = requests.get(API_URL, params=params, headers=headers, timeout=12)
            if response.status_code == 200:
                json_data = response.json()

                if json_data.get("success") and json_data.get("data"):
                    d = json_data["data"]
                    sub_map = {s["sub_name"]: s["sub_total"] for s in d.get("subjects", [])}

                    return {
                        "name": d.get("name"),
                        "father": d.get("father_name"),
                        "roll_no": str(d.get("roll_no")),
                        "school": d.get("school_name"),
                        "total": int(d.get("total") or 0),
                        "division": d.get("division"),
                        "subjects": sub_map,
                        "status": "Success"
                    }
                else:
                    break
        except Exception:
            time.sleep(0.3)

    return {
        "name": "NOT FOUND",
        "roll_no": str(roll_no),
        "total": 0,
        "division": "FAIL",
        "subjects": {},
        "status": "Failed"
    }

# ---------------- HTML TEMPLATE ----------------
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>BSEB Analytics Dashboard</title>
<style>
:root { --primary:#764ba2; --secondary:#667eea; --accent:#00d2ff; --bg:#0f0f1a; --card:#1e1e2e; }
body { margin:0; font-family:'Inter', sans-serif; background:var(--bg); color:white; }
.hero { height:100vh; display:flex; align-items:center; justify-content:center; background:radial-gradient(circle at top right,#1a1a3a,#0f0f1a); }
.glass-card { background:rgba(30,30,46,0.8); backdrop-filter:blur(10px); padding:40px; border-radius:20px; width:400px; text-align:center; }
.dashboard { padding:20px 50px; }
.stats-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(200px,1fr)); gap:20px; margin-bottom:30px; }
.stat-box { background:var(--card); padding:20px; border-radius:15px; border-left:5px solid var(--accent); }
table { width:100%; border-collapse:collapse; font-size:14px; }
th { background:#252538; padding:15px; color:var(--accent); }
td { padding:12px; text-align:center; border-bottom:1px solid #2d2d3f; }
.topper-row { background:rgba(255,215,0,0.1)!important; border-left:4px solid gold; }
input,button { width:100%; padding:12px; margin:10px 0; border-radius:8px; border:none; }
input { background:#2d2d3f; color:white; }
button { background:linear-gradient(to right,var(--secondary),var(--primary)); color:white; font-weight:bold; cursor:pointer; }
</style>
</head>

<body>
{% if page == 'home' %}
<div class="hero">
<div class="glass-card">
<h1 style="color:var(--accent)">BSEB Pro</h1>
<p>Advanced Result Analytics Portal</p>
<form action="/view" method="get">
<input name="rollcode" placeholder="Roll Code" required>
<button type="submit">GENERATE DASHBOARD</button>
</form>
</div>
</div>

{% else %}
<div class="dashboard">
<h2>School Analysis Dashboard</h2>
<p>Batch: {{ rollcode }} | Results: {{ results|length }}</p>

<div class="stats-grid">
<div class="stat-box"><h4>Total Students</h4><p>{{ results|length }}</p></div>
<div class="stat-box"><h4>Pass %</h4><p>{{ stats.pass_pct }}%</p></div>
<div class="stat-box"><h4>Highest Score</h4><p>{{ stats.top_score }}</p></div>
<div class="stat-box"><h4>1st Divisions</h4><p>{{ stats.div1 }}</p></div>
</div>

<a href="/download/csv"><button>Download CSV</button></a>

<table>
<tr>
<th>Roll</th>
<th>Name</th>
<th>Total</th>
<th>Division</th>
</tr>

{% for r in results %}
<tr class="{% if r.total == stats.top_score and r.total > 0 %}topper-row{% endif %}">
<td>{{ r.roll_no }}</td>
<td>{{ r.name }}</td>
<td>{{ r.total }}</td>
<td>{{ r.division }}</td>
</tr>
{% endfor %}
</table>
</div>
{% endif %}
</body>
</html>
"""

# ---------------- ROUTES ----------------
@app.route("/")
def home():
    return render_template_string(HTML_TEMPLATE, page='home')

@app.route("/view")
def view():
    rollcode = request.args.get("rollcode")

    START_ROLL = 2600001
    MAX_FAILS = 5
    MAX_LIMIT = 500
    BATCH_SIZE = 100

    results = []
    fail_count = 0
    current_roll = START_ROLL

    with ThreadPoolExecutor(max_workers=100) as executor:

        while fail_count < MAX_FAILS and current_roll < START_ROLL + MAX_LIMIT:

            batch_futures = {}

            # 🔹 Submit batch
            for _ in range(BATCH_SIZE):
                if current_roll >= START_ROLL + MAX_LIMIT:
                    break

                rn = str(current_roll)
                future = executor.submit(fetch_result, rollcode, rn)
                batch_futures[future] = rn
                current_roll += 1

            # 🔹 Collect results
            batch_results = []
            for future in as_completed(batch_futures):
                batch_results.append(future.result())

            # 🔹 Sort for true sequential fail detection
            batch_results.sort(key=lambda x: int(x["roll_no"]))

            for res in batch_results:
                results.append(res)

                if res["status"] == "Failed":
                    fail_count += 1
                else:
                    fail_count = 0

                # 🚀 Stop early
                if fail_count >= MAX_FAILS:
                    break

            if fail_count >= MAX_FAILS:
                break

    # ---------------- STATS ----------------
    results.sort(key=lambda x: int(x["roll_no"]))

    valid_results = [r for r in results if r['status'] == 'Success']
    top_score = max([r['total'] for r in valid_results]) if valid_results else 0
    passed = len([r for r in valid_results if "FAIL" not in r['division'].upper()])
    div1 = len([r for r in valid_results if "1ST" in r['division'].upper()])
    pass_pct = round((passed / len(results)) * 100, 1) if results else 0

    stats = {
        "top_score": top_score,
        "pass_pct": pass_pct,
        "div1": div1
    }

    CACHE["last_results"] = results

    return render_template_string(
        HTML_TEMPLATE,
        page='view',
        results=results,
        subjects=SUBJECT_LIST,
        rollcode=rollcode,
        stats=stats
    )

@app.route("/download/csv")
def download_csv():
    data = CACHE.get("last_results", [])

    def generate():
        yield "Roll,Name,Total,Division\n"
        for r in data:
            yield f"{r['roll_no']},{r['name']},{r['total']},{r['division']}\n"

    return Response(
        generate(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=analysis.csv"}
    )

# ---------------- RUN ----------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
