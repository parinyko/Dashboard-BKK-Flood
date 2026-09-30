from flask import Flask, render_template, request, jsonify, send_file, Response
import sqlite3
import os
import time
import json
import tempfile
from io import BytesIO
import requests
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment

try:
    from shapely.geometry import Point, shape
    from shapely.strtree import STRtree
except Exception:
    Point = shape = STRtree = None

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "data", "sites.db")
FLOODBOARD_BASE = "https://www.floodboard.org"
FLOODBOARD_ROADS = f"{FLOODBOARD_BASE}/api/export/roads.geojson"
FLOODBOARD_REPORTS = f"{FLOODBOARD_BASE}/api/export/reports.csv"
FLOODBOARD_STATS = f"{FLOODBOARD_BASE}/api/stats"
FLOODBOARD_FEED = f"{FLOODBOARD_BASE}/api/feed"
CACHE_DIR = os.path.join(BASE_DIR, "data", "cache")
os.makedirs(CACHE_DIR, exist_ok=True)

app = Flask(__name__)
app.config["JSON_AS_ASCII"] = False

_flood_index = None
_flood_index_loaded_at = 0
_flood_features = []


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def row_to_dict(row):
    return dict(row)


def clean(v):
    return "" if v is None else str(v).strip()


def normalize_depth(props):
    """Return best-known water depth in cm, or None."""
    if not isinstance(props, dict):
        return None
    keys = [
        "depth", "depth_cm", "water_depth", "max_depth", "depthCm",
        "waterDepth", "maxDepth", "flood_depth", "floodDepth", "cm"
    ]
    for key in keys:
        value = props.get(key)
        try:
            if value is not None and str(value).strip() != "":
                return float(str(value).replace(",", "").strip())
        except Exception:
            pass
    text = json.dumps(props, ensure_ascii=False).lower()
    import re
    matches = re.findall(r"(?:depth|water|น้ำ)[^0-9]{0,20}(\d+(?:\.\d+)?)\s*(?:cm|เซนติเมตร)?", text)
    if matches:
        try:
            return float(matches[0])
        except Exception:
            pass
    return None


def flood_status_from_properties(props):
    depth = normalize_depth(props)
    text = json.dumps(props or {}, ensure_ascii=False).lower()
    if depth is not None:
        if depth >= 70:
            return "severe", depth
        if depth >= 20:
            return "moderate", depth
        return "low", depth
    if any(x in text for x in ["not passable", "deep", "70+", "70 cm", "danger"]):
        return "severe", None
    if any(x in text for x in ["risky", "unconfirmed", "small car", "passable"]):
        return "moderate", None
    if any(x in text for x in ["receded", "water gone"]):
        return "low", 0
    return "unknown", None


def cached_get(url, filename, ttl=60):
    path = os.path.join(CACHE_DIR, filename)
    if os.path.exists(path) and time.time() - os.path.getmtime(path) < ttl:
        with open(path, "rb") as f:
            return f.read(), None
    r = requests.get(url, timeout=45, headers={"User-Agent": "FloodSiteBaseDashboard/2.0"})
    r.raise_for_status()
    content = r.content
    with open(path, "wb") as f:
        f.write(content)
    return content, r.headers.get("Content-Type")


def load_flood_index(force=False):
    """Build a spatial index from FloodBoard roads. Site coordinates are WGS84.
    A small degree buffer is used for proximity classification; this is intended
    as an operational indicator, not a hydrological inundation model.
    """
    global _flood_index, _flood_index_loaded_at, _flood_features
    if Point is None or STRtree is None:
        return None, []
    if _flood_index is not None and not force and time.time() - _flood_index_loaded_at < 60:
        return _flood_index, _flood_features
    try:
        content, _ = cached_get(FLOODBOARD_ROADS, "roads.geojson", ttl=60)
        gj = json.loads(content.decode("utf-8"))
        geoms, feats = [], []
        for f in gj.get("features", []):
            try:
                g = shape(f.get("geometry"))
                if not g.is_empty:
                    geoms.append(g)
                    feats.append(f)
            except Exception:
                continue
        _flood_features = feats
        _flood_index = STRtree(geoms) if geoms else None
        _flood_index_loaded_at = time.time()
        return _flood_index, _flood_features
    except Exception:
        return None, []


def classify_site(lat, lon, index, features):
    if index is None or not features:
        return "unknown", None, None
    p = Point(float(lon), float(lat))
    # Roughly 100 m at Thailand latitudes; used only to relate a Site to a reported road.
    candidate_idx = index.query(p.buffer(0.0012))
    best_status, best_depth, best_distance = "unknown", None, 999.0
    for idx in candidate_idx:
        try:
            geom = index.geometries[idx]
            distance = p.distance(geom)
            if distance > 0.0015:
                continue
            props = features[idx].get("properties", {}) or {}
            status, depth = flood_status_from_properties(props)
            priority = {"severe": 4, "moderate": 3, "low": 2, "unknown": 1}.get(status, 0)
            current_priority = {"severe": 4, "moderate": 3, "low": 2, "unknown": 1}.get(best_status, 0)
            if priority > current_priority or (priority == current_priority and distance < best_distance):
                best_status, best_depth, best_distance = status, depth, distance
        except Exception:
            continue
    if best_status == "unknown":
        return "safe", None, None
    # For display/API, treat an explicit low-water/receded report as low risk.
    return best_status, best_depth, best_distance * 111000.0


def get_sites(filters=None, include_flood=False, limit=None):
    filters = filters or {}
    province = clean(filters.get("province"))
    amphur = clean(filters.get("amphur"))
    q = clean(filters.get("q"))
    south, west, north, east = [filters.get(k) for k in ("south", "west", "north", "east")]
    conn = db()
    try:
        where = ["latitude IS NOT NULL", "longitude IS NOT NULL"]
        params = []
        if province:
            where.append("province = ?"); params.append(province)
        if amphur:
            where.append("amphur = ?"); params.append(amphur)
        if q:
            where.append("(site_code LIKE ? OR location_name LIKE ? OR tumbol LIKE ? OR amphur LIKE ? OR province LIKE ?)")
            like = f"%{q}%"; params.extend([like] * 5)
        if None not in (south, west, north, east):
            where += ["latitude BETWEEN ? AND ?", "longitude BETWEEN ? AND ?"]
            params += [float(south), float(north), float(west), float(east)]
        sql = f"SELECT site_code, location_name, tumbol, amphur, province, latitude, longitude FROM sites WHERE {' AND '.join(where)} ORDER BY site_code"
        if limit is not None:
            sql += " LIMIT ?"; params.append(int(limit))
        return [row_to_dict(r) for r in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/filters")
def filters():
    conn = db()
    try:
        provinces = [r[0] for r in conn.execute("SELECT DISTINCT province FROM sites WHERE province IS NOT NULL AND province<>'' ORDER BY province").fetchall()]
        province = clean(request.args.get("province"))
        if province:
            amphurs = [r[0] for r in conn.execute("SELECT DISTINCT amphur FROM sites WHERE province=? AND amphur IS NOT NULL AND amphur<>'' ORDER BY amphur", (province,)).fetchall()]
        else:
            amphurs = [r[0] for r in conn.execute("SELECT DISTINCT amphur FROM sites WHERE amphur IS NOT NULL AND amphur<>'' ORDER BY amphur").fetchall()]
        return jsonify({"provinces": provinces, "amphurs": amphurs})
    finally:
        conn.close()


@app.get("/api/sites")
def sites():
    limit = min(max(request.args.get("limit", 5000, type=int), 1), 10000)
    data = get_sites(request.args, include_flood=False, limit=limit)
    if request.args.get("with_flood", "0") == "1":
        index_obj, features = load_flood_index()
        for s in data:
            status, depth, distance = classify_site(s["latitude"], s["longitude"], index_obj, features)
            s.update(flood_status=status, water_depth_cm=depth, flood_distance_m=distance)
    return jsonify({"count": len(data), "limit": limit, "sites": data})


@app.get("/api/site/<site_code>")
def site(site_code):
    conn = db()
    try:
        row = conn.execute("SELECT * FROM sites WHERE site_code = ? LIMIT 1", (site_code,)).fetchone()
        if not row:
            return jsonify({"error": "Site not found"}), 404
        result = row_to_dict(row)
        index_obj, features = load_flood_index()
        status, depth, distance = classify_site(result["latitude"], result["longitude"], index_obj, features)
        result.update(flood_status=status, water_depth_cm=depth, flood_distance_m=distance)
        return jsonify(result)
    finally:
        conn.close()


@app.get("/api/site-count")
def site_count():
    conn = db()
    try:
        total = conn.execute("SELECT COUNT(*) AS n FROM sites").fetchone()["n"]
        provinces = conn.execute("SELECT COUNT(DISTINCT province) AS n FROM sites WHERE province IS NOT NULL AND province <> ''").fetchone()["n"]
        return jsonify({"total": total, "provinces": provinces})
    finally:
        conn.close()


@app.get("/api/dashboard-summary")
def dashboard_summary():
    sites_data = get_sites(request.args, limit=None)
    index_obj, features = load_flood_index()
    counts = {"total": len(sites_data), "flooded": 0, "severe": 0, "moderate": 0, "low": 0, "safe": 0, "unknown": 0}
    for s in sites_data:
        status, depth, distance = classify_site(s["latitude"], s["longitude"], index_obj, features)
        counts[status] = counts.get(status, 0) + 1
    counts["flooded"] = counts.get("severe", 0) + counts.get("moderate", 0) + counts.get("low", 0)
    counts["matched"] = counts["total"]
    return jsonify(counts)


@app.get("/api/export.xlsx")
def export_xlsx():
    rows = get_sites(request.args, limit=None)
    index_obj, features = load_flood_index()
    wb = Workbook()
    ws = wb.active
    ws.title = "Site Base Report"
    headers = ["Site Code", "Location Name", "Tambon", "Amphur", "Province", "Latitude", "Longitude", "Flood Status", "Water Depth (cm)", "Distance to Flooded Road (m)"]
    ws.append(headers)
    for c in ws[1]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="1769AA")
        c.alignment = Alignment(horizontal="center", vertical="center")
    for s in rows:
        status, depth, distance = classify_site(s["latitude"], s["longitude"], index_obj, features)
        ws.append([
            s["site_code"], s["location_name"], s["tumbol"], s["amphur"], s["province"],
            s["latitude"], s["longitude"], status, depth, distance
        ])
    widths = [16, 48, 22, 22, 24, 13, 13, 16, 18, 28]
    for i, w in enumerate(widths, 1): ws.column_dimensions[chr(64+i)].width = w
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    buf = BytesIO(); wb.save(buf); buf.seek(0)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    return send_file(buf, as_attachment=True, download_name=f"site_base_flood_report_{stamp}.xlsx", mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@app.get("/api/floodboard/roads")
def floodboard_roads():
    try:
        content, _ = cached_get(FLOODBOARD_ROADS, "roads.geojson", ttl=60)
        return Response(content, content_type="application/geo+json")
    except Exception as e:
        return jsonify({"error": "Cannot load FloodBoard roads data", "detail": str(e)}), 502


@app.get("/api/floodboard/reports")
def floodboard_reports():
    try:
        content, _ = cached_get(FLOODBOARD_REPORTS, "reports.csv", ttl=60)
        return Response(content, content_type="text/csv; charset=utf-8")
    except Exception as e:
        return jsonify({"error": "Cannot load FloodBoard reports data", "detail": str(e)}), 502


@app.get("/api/floodboard/stats")
def floodboard_stats():
    try:
        content, _ = cached_get(FLOODBOARD_STATS, "stats.json", ttl=60)
        return Response(content, content_type="application/json; charset=utf-8")
    except Exception as e:
        return jsonify({"error": "Cannot load FloodBoard stats", "detail": str(e)}), 502


@app.get("/api/floodboard/feed")
def floodboard_feed():
    try:
        content, _ = cached_get(FLOODBOARD_FEED, "feed.json", ttl=60)
        return Response(content, content_type="application/json; charset=utf-8")
    except Exception as e:
        return jsonify({"error": "Cannot load FloodBoard feed", "detail": str(e)}), 502


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
