from flask import Flask, request, render_template_string, Response
import requests
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

app = Flask(__name__)

API_URL = "https://examapi.biharboardonline.org/result"
CACHE = {}
SUBJECT_LIST = ["HINDI", "SANSKRIT", "MATHEMATICS", "SCIENCE", "SOCIAL SCIENCE", "ENGLISH"]

# ---------------- FETCH FUNCTION ----------------
def fetch_result(roll_code, roll_no):
    params = {"roll_code": roll_code, "roll_no": roll_no}
    headers = {"User-Agent": "Mozilla/5.0"}

    for attempt in range(5):  # retry 5 times
        try:
            response = requests.get(API_URL, params=params, headers=headers, timeout=10)
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

# ---------------- HTML ----------------
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
<title>BSEB Auto Dashboard</title>
<style>
body { background:#0f0f1a; color:white; font-family:sans-serif; margin:0; }
.center { display:flex; justify-content:center; align-items:center; height:100vh; }
.card { background:#1e1e2e; padding:30px; border-radius:12px; width:350px; text-align:center; }
input,button { width:100%; padding:10px; margin:10px 0; border:none; border-radius:6px; }
input { background:#2d2d3f; color:white; }
button { background:#667eea; color:white; cursor:pointer; }

table { width:100%; border-collapse:collapse; margin-top:20px; }
td,th { padding:8px; border-bottom:1px solid #333; text-align:center; }
</style>
</head>

<body>

{% if page == 'home' %}
<div class="center">
<div class="card">
<h2>BSEB Auto Fetch</h2>
<form action="/view">
<input name="rollcode" placeholder="Enter Roll Code" required>
<button>Fetch Full School</button>
</form>
</div>
</div>

{% else %}

<div style="padding:20px">
<h2>Results ({{ results|length }})</h2>

<p>Top Score: {{ stats.top_score }} | Pass %: {{ stats.pass_pct }}%</p>

<a href="/download/csv"><button>Download CSV</button></a>

<table>
<tr>
<th>Roll</th>
<th>Name</th>
<th>Total</th>
<th>Division</th>
</tr>

{% for r in results %}
<tr>
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
    return render_template_string(HTML_TEMPLATE, page="home")

@app.route("/view")
def view():
    rollcode = request.args.get("rollcode")

    START_ROLL = 2600001
    MAX_FAILS = 5
    MAX_LIMIT = 300

    results = []
    current_roll = START_ROLL
    fail_count = 0

    with ThreadPoolExecutor(max_workers=100) as executor:
        futures = []

        while fail_count < MAX_FAILS and current_roll < START_ROLL + MAX_LIMIT:
            futures.append(executor.submit(fetch_result, rollcode, str(current_roll)))
            current_roll += 1

        for future in as_completed(futures):
            res = future.result()
            results.append(res)

            if res["status"] == "Failed":
                fail_count += 1
            else:
                fail_count = 0

    results.sort(key=lambda x: int(x["roll_no"]))

    valid = [r for r in results if r["status"] == "Success"]

    top_score = max([r["total"] for r in valid]) if valid else 0
    passed = len([r for r in valid if "FAIL" not in r["division"].upper()])
    pass_pct = round((passed / len(results)) * 100, 1) if results else 0

    stats = {
        "top_score": top_score,
        "pass_pct": pass_pct
    }

    CACHE["last_results"] = results

    return render_template_string(
        HTML_TEMPLATE,
        page="view",
        results=results,
        stats=stats
    )

@app.route("/download/csv")
def download_csv():
    data = CACHE.get("last_results", [])

    def generate():
        yield "Roll,Name,Total,Division\n"
        for r in data:
            yield f"{r['roll_no']},{r['name']},{r['total']},{r['division']}\n"

    return Response(generate(),
                    mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=results.csv"})

# ---------------- RUN ----------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
