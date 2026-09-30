from flask import Flask, render_template, request, jsonify
import pandas as pd
import os

app = Flask(__name__)

EXCEL_FILE = os.path.join(os.path.dirname(__file__), "Location Site(3).xlsx")

# Load Site Base data once when the application starts.
def load_sites():
    if not os.path.exists(EXCEL_FILE):
        raise FileNotFoundError(f"ไม่พบไฟล์ {EXCEL_FILE}")

    df = pd.read_excel(EXCEL_FILE)

    required = [
        "SITE_CODE",
        "LOCATION_NAME_EN",
        "TUMBOL",
        "AMPHUR",
        "PROVINCE",
        "LATITUDE_RF",
        "LONGITUDE_RF",
    ]

    for col in required:
        if col not in df.columns:
            df[col] = ""

    df["LATITUDE_RF"] = pd.to_numeric(df["LATITUDE_RF"], errors="coerce")
    df["LONGITUDE_RF"] = pd.to_numeric(df["LONGITUDE_RF"], errors="coerce")
    df = df.dropna(subset=["LATITUDE_RF", "LONGITUDE_RF"]).copy()

    df = df.fillna("")

    records = []
    for _, row in df.iterrows():
        records.append({
            "site_code": str(row["SITE_CODE"]),
            "name": str(row["LOCATION_NAME_EN"]),
            "tumbol": str(row["TUMBOL"]),
            "amphur": str(row["AMPHUR"]),
            "province": str(row["PROVINCE"]),
            "lat": float(row["LATITUDE_RF"]),
            "lon": float(row["LONGITUDE_RF"]),
        })

    return records


SITES = load_sites()


@app.route("/")
def index():
    return render_template("index.html", site_count=len(SITES))


@app.route("/api/sites")
def api_sites():
    return jsonify(SITES)


@app.route("/api/search")
def api_search():
    q = request.args.get("q", "").strip().lower()

    if not q:
        return jsonify([])

    results = []
    for site in SITES:
        haystack = " ".join([
            site["site_code"],
            site["name"],
            site["tumbol"],
            site["amphur"],
            site["province"],
        ]).lower()

        if q in haystack:
            results.append(site)

        if len(results) >= 50:
            break

    return jsonify(results)


if __name__ == "__main__":
    print("=" * 60)
    print("Flood Site Base Map")
    print(f"Site Base: {len(SITES):,} จุด")
    print("เปิดเว็บ: http://127.0.0.1:5000")
    print("=" * 60)

    app.run(host="0.0.0.0", port=5000, debug=True)
