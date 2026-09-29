
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
import sqlite3, os, math, re
from pathlib import Path
from werkzeug.utils import secure_filename
import pandas as pd
import requests
from datetime import datetime, timezone

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "data" / "bangkok_metropolitan_flood_analyzer.db"
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

try:
    from dotenv import load_dotenv
    load_dotenv(BASE_DIR / ".env")
except Exception:
    pass

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "bangkok-metropolitan-flood-analyzer")
HTTP_TIMEOUT = float(os.getenv("HTTP_TIMEOUT_SECONDS", "12"))

GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "")
GOOGLE_ELEVATION_URL = os.getenv(
    "GOOGLE_ELEVATION_URL",
    "https://maps.googleapis.com/maps/api/elevation/json"
)
GOOGLE_ROUTES_URL = os.getenv(
    "GOOGLE_ROUTES_URL",
    "https://routes.googleapis.com/directions/v2:computeRoutes"
)

FLOOD_BANGKOK_API_URL = os.getenv("FLOOD_BANGKOK_API_URL", "")
FLOOD_BANGKOK_API_TOKEN = os.getenv("FLOOD_BANGKOK_API_TOKEN", "")
TRAFFY_API_URL = os.getenv("TRAFFY_API_URL", "")
TRAFFY_API_TOKEN = os.getenv("TRAFFY_API_TOKEN", "")

CAR_PASS_CM = float(os.getenv("CAR_PASS_CM", "10"))
CAR_CAUTION_CM = float(os.getenv("CAR_CAUTION_CM", "20"))
CAR_AVOID_CM = float(os.getenv("CAR_AVOID_CM", "24"))
CAR_BLOCK_CM = float(os.getenv("CAR_BLOCK_CM", "25"))
NEARBY_FLOOD_KM = float(os.getenv("NEARBY_FLOOD_KM", "3"))
NEARBY_TRAFFY_KM = float(os.getenv("NEARBY_TRAFFY_KM", "2"))

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def distinct_values(column):
    conn = get_db()
    sql = f'''SELECT DISTINCT "{column}" AS value
              FROM job_monitor
              WHERE "{column}" IS NOT NULL AND TRIM("{column}") <> ''
              ORDER BY "{column}"'''
    rows = conn.execute(sql).fetchall()
    conn.close()
    return [r["value"] for r in rows]

def build_filters():
    fields = {
        "sub_system": 'jm."Sub System"',
        "zone": 'jm."Zone"',
        "priority": 'jm."Priority"',
        "status": 'jm."Status"',
        "province": 'jm."Province Name"',
    }
    where, params = [], []
    for key, col in fields.items():
        value = request.args.get(key, "").strip()
        if value:
            where.append(f"{col} = ?")
            params.append(value)
    q = request.args.get("q", "").strip()
    if q:
        where.append('''(
            jm."Job ID" LIKE ? OR jm."Site Name" LIKE ? OR
            jm."Job Title" LIKE ? OR jm."Assign to" LIKE ?
        )''')
        like = f"%{q}%"
        params.extend([like] * 4)
    return (" WHERE " + " AND ".join(where)) if where else "", params

def haversine_km(lat1, lon1, lat2, lon2):
    r = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2-lat1), math.radians(lon2-lon1)
    a = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2*r*math.asin(math.sqrt(a))

def safe_json(resp):
    try:
        return resp.json()
    except Exception:
        return {"status": "HTTP_ERROR", "http_status": resp.status_code, "text": resp.text[:1000]}

def auth_headers(token):
    h = {"Accept": "application/json"}
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h

def google_elevation(lat, lng):
    if not GOOGLE_MAPS_API_KEY:
        return {"available": False, "source": "Google Elevation API",
                "reason": "GOOGLE_MAPS_API_KEY is not configured"}
    try:
        r = requests.get(GOOGLE_ELEVATION_URL,
            params={"locations": f"{lat},{lng}", "key": GOOGLE_MAPS_API_KEY},
            timeout=HTTP_TIMEOUT)
        data = safe_json(r)
        if r.ok and data.get("status") == "OK" and data.get("results"):
            x = data["results"][0]
            return {"available": True, "source": "Google Elevation API",
                    "elevation_m": x.get("elevation"),
                    "resolution_m": x.get("resolution")}
        return {"available": False, "source": "Google Elevation API",
                "reason": data.get("error_message") or data.get("status") or f"HTTP {r.status_code}"}
    except Exception as e:
        return {"available": False, "source": "Google Elevation API", "reason": str(e)}

def google_route(origin_lat, origin_lng, dest_lat, dest_lng):
    if not GOOGLE_MAPS_API_KEY:
        return {"available": False, "source": "Google Routes API",
                "reason": "GOOGLE_MAPS_API_KEY is not configured"}
    body = {
        "origin": {"location": {"latLng": {"latitude": origin_lat, "longitude": origin_lng}}},
        "destination": {"location": {"latLng": {"latitude": dest_lat, "longitude": dest_lng}}},
        "travelMode": "DRIVE",
        "routingPreference": "TRAFFIC_AWARE",
        "units": "METRIC"
    }
    fields = "routes.distanceMeters,routes.duration,routes.polyline.encodedPolyline"
    try:
        r = requests.post(GOOGLE_ROUTES_URL, headers={
            "Content-Type": "application/json",
            "X-Goog-Api-Key": GOOGLE_MAPS_API_KEY,
            "X-Goog-FieldMask": fields
        }, json=body, timeout=HTTP_TIMEOUT)
        data = safe_json(r)
        if not r.ok or not data.get("routes"):
            err = data.get("error", {})
            return {"available": False, "source": "Google Routes API",
                    "reason": err.get("message") if isinstance(err, dict) else f"HTTP {r.status_code}"}
        x = data["routes"][0]
        return {"available": True, "source": "Google Routes API",
                "distance_m": x.get("distanceMeters"),
                "duration": x.get("duration"),
                "polyline": x.get("polyline", {}).get("encodedPolyline")}
    except Exception as e:
        return {"available": False, "source": "Google Routes API", "reason": str(e)}

def external_api(url, token, lat, lng, radius_km, name):
    if not url:
        return {"available": False, "source": name, "reason": f"{name} endpoint is not configured"}
    try:
        params = {"lat": lat, "lng": lng, "latitude": lat, "longitude": lng,
                  "radius_km": radius_km, "radius": radius_km * 1000}
        r = requests.get(url, params=params, headers=auth_headers(token), timeout=HTTP_TIMEOUT)
        data = safe_json(r)
        if not r.ok:
            return {"available": False, "source": name, "reason": f"HTTP {r.status_code}", "raw": data}
        return {"available": True, "source": name, "raw": data}
    except Exception as e:
        return {"available": False, "source": name, "reason": str(e)}

def list_candidates(raw, keys):
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        for k in keys:
            if isinstance(raw.get(k), list):
                return raw[k]
    return []

def normalize_flood(result, lat, lng):
    if not result.get("available"):
        return []
    out = []
    for item in list_candidates(result.get("raw"), ["stations","data","results","items","features"]):
        if not isinstance(item, dict): continue
        prop = item.get("properties") if isinstance(item.get("properties"), dict) else {}
        s = {**item, **prop}
        la, lo = s.get("lat", s.get("latitude")), s.get("lng", s.get("lon", s.get("longitude")))
        try: la, lo = float(la), float(lo)
        except Exception: continue
        water = None
        for k in ["water_level_cm","waterLevelCm","water_level","waterLevel","level_cm","level","height_cm"]:
            if s.get(k) is not None:
                try: water = float(s[k]); break
                except Exception: pass
        if water is None: continue
        out.append({
            "name": s.get("name") or s.get("station_name") or s.get("stationName") or "Flood station",
            "lat": la, "lng": lo, "distance_km": round(haversine_km(lat,lng,la,lo),3),
            "water_level_cm": water,
            "updated_at": s.get("updated_at") or s.get("updatedAt") or s.get("timestamp")
        })
    return sorted(out, key=lambda x:x["distance_km"])

def normalize_traffy(result, lat, lng):
    if not result.get("available"):
        return []
    out = []
    for item in list_candidates(result.get("raw"), ["tickets","data","results","items","features"]):
        if not isinstance(item, dict): continue
        prop = item.get("properties") if isinstance(item.get("properties"), dict) else {}
        s = {**item, **prop}
        la, lo = s.get("lat", s.get("latitude")), s.get("lng", s.get("lon", s.get("longitude")))
        try: la, lo = float(la), float(lo)
        except Exception: continue
        title = s.get("problem") or s.get("title") or s.get("subject") or s.get("description") or ""
        cat = s.get("type") or s.get("category") or ""
        text = f"{title} {cat}".lower()
        flood_related = any(k in text for k in ["น้ำท่วม","น้ำขัง","ท่วมขัง","ระบายน้ำ","flood","water"])
        out.append({
            "ticket_id": s.get("ticketID") or s.get("ticket_id") or s.get("id"),
            "title": title[:180], "category": cat, "status": s.get("status"),
            "lat": la, "lng": lo, "distance_km": round(haversine_km(lat,lng,la,lo),3),
            "created_at": s.get("timestamp") or s.get("created_at") or s.get("createdAt"),
            "flood_related": flood_related
        })
    return sorted(out, key=lambda x:x["distance_km"])

def classify(max_water, traffy, elevation):
    evidence, score = [], 0
    if max_water is not None:
        if max_water >= CAR_BLOCK_CM:
            score += 80
        elif max_water > CAR_CAUTION_CM:
            score += 55
        elif max_water > CAR_PASS_CM:
            score += 30
        evidence.append(f"ระดับน้ำ {max_water:.1f} ซม.")
    flood_reports = [x for x in traffy if x["flood_related"]]
    if flood_reports:
        score += min(30, len(flood_reports)*10)
        evidence.append(f"Traffy พบรายงานเกี่ยวกับน้ำ {len(flood_reports)} รายการ")
    if elevation is not None:
        evidence.append(f"Elevation {elevation:.2f} ม.")
    if max_water is None and not flood_reports:
        return {"level":"UNKNOWN","label":"ข้อมูลไม่เพียงพอ","score":None,"evidence":evidence}
    level = "HIGH" if score >= 70 else "MEDIUM" if score >= 35 else "LOW"
    return {"level":level,"label":{"HIGH":"เสี่ยงสูง","MEDIUM":"เสี่ยงปานกลาง","LOW":"เสี่ยงต่ำ"}[level],
            "score":score,"evidence":evidence}

def small_car(max_water, traffy, risk_level):
    if max_water is not None:
        if max_water >= CAR_BLOCK_CM:
            return {"decision":"ไม่ควรผ่าน","reason":f"ระดับน้ำ {max_water:.1f} ซม. ≥ {CAR_BLOCK_CM:.0f} ซม."}
        if max_water > CAR_AVOID_CM:
            return {"decision":"หลีกเลี่ยง","reason":f"ระดับน้ำ {max_water:.1f} ซม. > {CAR_AVOID_CM:.0f} ซม."}
        if max_water > CAR_PASS_CM:
            return {"decision":"ต้องระวัง","reason":f"ระดับน้ำ {max_water:.1f} ซม. > {CAR_PASS_CM:.0f} ซม."}
        return {"decision":"ผ่านได้ตามข้อมูลน้ำ","reason":f"ระดับน้ำ {max_water:.1f} ซม. ≤ {CAR_PASS_CM:.0f} ซม."}
    if risk_level == "HIGH":
        return {"decision":"หลีกเลี่ยง","reason":"มีหลักฐานความเสี่ยงสูง แต่ไม่มีระดับน้ำยืนยันโดยตรง"}
    if risk_level == "MEDIUM" or any(x["flood_related"] for x in traffy):
        return {"decision":"ต้องระวัง","reason":"พบหลักฐานน้ำท่วมใกล้จุด แต่ยังไม่มีระดับน้ำยืนยัน"}
    return {"decision":"ยังสรุปไม่ได้","reason":"ไม่มีข้อมูลน้ำที่เพียงพอ"}

def analyze_job(job, dest_lat=None, dest_lng=None):
    lat, lng = job["Job_Lat"], job["Job_Long"]
    if lat is None or lng is None:
        return {"ok":False,"error":"Job นี้ไม่มีพิกัด","job":dict(job)}
    elevation = google_elevation(lat,lng)
    flood_api = external_api(FLOOD_BANGKOK_API_URL,FLOOD_BANGKOK_API_TOKEN,lat,lng,NEARBY_FLOOD_KM,"Flood Bangkok")
    traffy_api = external_api(TRAFFY_API_URL,TRAFFY_API_TOKEN,lat,lng,NEARBY_TRAFFY_KM,"Traffy Fondue")
    stations = normalize_flood(flood_api,lat,lng)
    reports = normalize_traffy(traffy_api,lat,lng)
    max_water = max([x["water_level_cm"] for x in stations if x["distance_km"] <= NEARBY_FLOOD_KM], default=None)
    if dest_lat is not None and dest_lng is not None:
        route = google_route(lat,lng,dest_lat,dest_lng)
    else:
        route = {"available":False,"source":"Google Routes API","reason":"ยังไม่ได้ระบุปลายทาง"}
    risk = classify(max_water,reports,elevation.get("elevation_m") if elevation.get("available") else None)
    car = small_car(max_water,reports,risk["level"])
    sources = [
        {"name":"Flood Bangkok","available":flood_api["available"],"reason":flood_api.get("reason")},
        {"name":"Google Elevation","available":elevation["available"],"reason":elevation.get("reason")},
        {"name":"Traffy Fondue","available":traffy_api["available"],"reason":traffy_api.get("reason")},
        {"name":"Google Routes","available":route["available"],"reason":route.get("reason")}
    ]
    return {"ok":True,"job":dict(job),"generated_at":datetime.now(timezone.utc).isoformat(),
            "elevation":elevation,"flood":{"stations":stations,"max_water_cm":max_water},
            "traffy":{"reports":reports},"route":route,"risk":risk,"small_car":car,"sources":sources}

@app.route("/")
def index():
    clause,params=build_filters()
    page=max(1,request.args.get("page",1,type=int)); per_page=25; offset=(page-1)*per_page
    conn=get_db()
    total=conn.execute(f"SELECT COUNT(*) FROM job_monitor jm{clause}",params).fetchone()[0]
    jobs=conn.execute(f'''SELECT jm.* FROM job_monitor jm {clause}
        ORDER BY COALESCE(jm."Create Time_dt",jm."Create Time") DESC LIMIT ? OFFSET ?''',
        params+[per_page,offset]).fetchall()
    counts=conn.execute(f'''SELECT COUNT(*) total,
        SUM(CASE WHEN "Priority"='Critical' THEN 1 ELSE 0 END) critical,
        SUM(CASE WHEN "Priority"='Major' THEN 1 ELSE 0 END) major,
        SUM(CASE WHEN "Priority"='Minor' THEN 1 ELSE 0 END) minor,
        SUM(CASE WHEN "Has_Coordinate"=1 THEN 1 ELSE 0 END) mapped
        FROM job_monitor jm {clause}''',params).fetchone()
    conn.close()
    filters={k:request.args.get(k,"") for k in ["sub_system","zone","priority","status","province","q"]}
    pages=max(1,(total+per_page-1)//per_page)
    return render_template("index.html",jobs=jobs,filters=filters,
        sub_systems=distinct_values("Sub System"),zones=distinct_values("Zone"),
        priorities=distinct_values("Priority"),statuses=distinct_values("Status"),
        provinces=distinct_values("Province Name"),counts=counts,page=page,pages=pages,total=total)

@app.route("/job/<path:job_id>")
def job_detail(job_id):
    conn=get_db(); job=conn.execute('SELECT * FROM job_monitor WHERE "Job ID"=?',(job_id,)).fetchone(); conn.close()
    if not job:return "Job not found",404
    return render_template("job_detail.html",job=job)

@app.route("/api/job/<path:job_id>/analysis")
def api_job_analysis(job_id):
    conn=get_db(); job=conn.execute('SELECT * FROM job_monitor WHERE "Job ID"=?',(job_id,)).fetchone(); conn.close()
    if not job:return jsonify({"ok":False,"error":"Job not found"}),404
    return jsonify(analyze_job(job,request.args.get("dest_lat",type=float),request.args.get("dest_lng",type=float)))

@app.route("/api/jobs")
def api_jobs():
    clause,params=build_filters(); conn=get_db()
    sql=f'''SELECT "Job ID" job_id,"Job_Lat" lat,"Job_Long" lng,"Priority" priority,
        "Status" status,"Sub System" sub_system,"Zone" zone,"Site Name" site_name
        FROM job_monitor jm {clause}
        {'AND' if clause else 'WHERE'} "Job_Lat" IS NOT NULL AND "Job_Long" IS NOT NULL
        ORDER BY "Create Time_dt" DESC LIMIT 1000'''
    rows=conn.execute(sql,params).fetchall(); conn.close(); return jsonify([dict(r) for r in rows])

@app.route("/upload",methods=["POST"])
def upload():
    file=request.files.get("file")
    if not file or not file.filename:
        flash("กรุณาเลือกไฟล์ Job Monitor ก่อน","error"); return redirect(url_for("index"))
    if Path(file.filename).suffix.lower() not in {".xlsx",".xls"}:
        flash("รองรับเฉพาะไฟล์ Excel","error"); return redirect(url_for("index"))
    saved=UPLOAD_DIR/secure_filename(file.filename); file.save(saved)
    try:
        df=pd.read_excel(saved); required=["Job ID","Sub System","Priority","Zone"]
        missing=[c for c in required if c not in df.columns]
        if missing: raise ValueError("ไม่พบคอลัมน์: "+", ".join(missing))
        for c in required: df[c]=df[c].astype("string").str.strip()
        def coord(text,idx):
            if pd.isna(text):return None
            m=re.search(r"\(\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*\)",str(text))
            return float(m.group(idx)) if m else None
        if "Job_Lat" not in df.columns:
            s=df["Job Title"] if "Job Title" in df.columns else pd.Series([None]*len(df)); df["Job_Lat"]=s.apply(lambda x:coord(x,1))
        if "Job_Long" not in df.columns:
            s=df["Job Title"] if "Job Title" in df.columns else pd.Series([None]*len(df)); df["Job_Long"]=s.apply(lambda x:coord(x,2))
        for c in ["Create Time_dt","Est Time_dt","Dispatch NextTime_dt"]:
            if c not in df.columns:
                b=c.replace("_dt","")
                if b in df.columns:df[c]=pd.to_datetime(df[b],errors="coerce")
        if "Has_Coordinate" not in df.columns:df["Has_Coordinate"]=df["Job_Lat"].notna()&df["Job_Long"].notna()
        conn=get_db(); df.to_sql("job_monitor",conn,if_exists="replace",index=False)
        for col,idx in [("Job ID","idx_job_monitor_jobid"),("Sub System","idx_job_monitor_subsystem"),
                        ("Zone","idx_job_monitor_zone"),("Priority","idx_job_monitor_priority"),("Status","idx_job_monitor_status")]:
            conn.execute(f'CREATE INDEX IF NOT EXISTS {idx} ON job_monitor("{col}")')
        conn.commit();conn.close();flash(f"Upload สำเร็จ: {len(df):,} งาน","success")
    except Exception as e:flash(f"Upload ไม่สำเร็จ: {e}","error")
    return redirect(url_for("index"))

if __name__=="__main__":
    app.run(host="127.0.0.1",port=5000,debug=True)
