"""Real-place data from OpenStreetMap (map data (c) OpenStreetMap contributors, ODbL 1.0, openstreetmap.org/copyright).

    python osm_place.py fetch      # ONE polite Overpass request for the configured place -> data/osm/<name>.json (raw,
                                   # gitignored). Owner-approved download (2026-10-23). Skipped if the file exists.
    python osm_place.py process    # raw -> places/<name>.json (committed, small): everything the simulator needs, in
                                   # LOCAL METRES, so tests, CI and the online dashboard never need the internet.

Which place: config.yaml `place:` (bbox_deg = [south, west, north, east]). Only plain Python (urllib + json) is used.

Local metres (equirectangular around the box centre; documented in docs/case_nepal/):
    x = (lon - lon_c) * cos(lat_c) * pi/180 * R + L/2,   y = (lat - lat_c) * pi/180 * R + L/2,   R = 6 371 008.8 m
(mean Earth radius, IUGG). Over a 2 x 2 km box the error against a proper projection is far below a metre (the scale
factor cos(lat) changes by ~1e-4 between the box edges), much smaller than the 2 m height raster. The box itself is
built from its centre and side L in these same formulas, so (0, 0)..(L, L) is exactly the simulator's map.

What is kept (and how):
  buildings  every `building=*` way, and the OUTER rings of `building=*` multipolygon relations (inner rings, courtyards
             are dropped: a simplification, courtyards are rare and small here). Height: the `height` tag (metres; a
             trailing 'm' is accepted) when present, else `building:levels` x levels_m (config; 3 m per storey is an
             ENGINEERING ASSUMPTION), else null (place.py fills it from the distribution of the tagged buildings).
             Footprints are kept if any vertex is inside the box (the raster clips them at the map edge).
  waterways  `waterway=river|stream|canal` lines with their name (the flood band uses the configured river names).
  shelters   evacuation-point candidates: amenity school/college/university/hospital/clinic/community_centre/
             place_of_worship/shelter, emergency=assembly_point, leisure=park (the designated open spaces of the valley
             are often mapped as parks or assembly points). One point per object (node position, or way-vertex mean).
Coordinates are rounded to 0.1 m (deterministic output: the same raw file always gives byte-identical JSON).
"""
import json
import math
import sys
import urllib.parse
import urllib.request
from pathlib import Path

import make_dataset as md

HERE = Path(__file__).parent
R_EARTH_M = 6371008.8               # mean Earth radius (IUGG), metres
OVERPASS_URL = "https://overpass-api.de/api/interpreter"
SHELTER_AMENITY = ("school", "college", "university", "hospital", "clinic", "community_centre", "place_of_worship",
                   "shelter")
CREDIT = "Map data (c) OpenStreetMap contributors, ODbL 1.0"


# ---------------------------------------------------------------- coordinates
def bbox_from_centre(lat_c, lon_c, side_m):
    """[south, west, north, east] (degrees) of the side_m x side_m square centred on (lat_c, lon_c), in the same
    equirectangular formulas as to_local, so the box maps exactly to (0, 0)..(side, side)."""
    dlat = math.degrees(side_m / 2 / R_EARTH_M)
    dlon = math.degrees(side_m / 2 / (R_EARTH_M * math.cos(math.radians(lat_c))))
    return [lat_c - dlat, lon_c - dlon, lat_c + dlat, lon_c + dlon]


def to_local(lat, lon, lat_c, lon_c, side_m):
    """(lat, lon) degrees -> (x, y) metres in the simulator's map: origin at the box's south-west corner, x east,
    y north. Works on floats or numpy arrays."""
    k = math.pi / 180.0 * R_EARTH_M
    return (lon - lon_c) * math.cos(math.radians(lat_c)) * k + side_m / 2, (lat - lat_c) * k + side_m / 2


def to_latlon(x, y, lat_c, lon_c, side_m):
    """Inverse of to_local."""
    k = math.pi / 180.0 * R_EARTH_M
    return lat_c + (y - side_m / 2) / k, lon_c + (x - side_m / 2) / (k * math.cos(math.radians(lat_c)))


# ---------------------------------------------------------------- download
def overpass_query(bbox):
    s, w, n, e = bbox
    b = f"({s:.6f},{w:.6f},{n:.6f},{e:.6f})"
    am = "|".join(SHELTER_AMENITY)
    return (f'[out:json][timeout:180];('
            f'way["building"]{b};relation["building"]{b};'
            f'way["waterway"~"^(river|stream|canal)$"]{b};'
            f'node["amenity"~"^({am})$"]{b};way["amenity"~"^({am})$"]{b};'
            f'node["emergency"="assembly_point"]{b};way["emergency"="assembly_point"]{b};'
            f'way["leisure"="park"]{b};'
            f');out geom;')


def raw_path(name):
    return HERE / "data" / "osm" / f"{name}.json"


def processed_path(name):
    return HERE / "places" / f"{name}.json"


def fetch(pc):
    """ONE Overpass request (polite: a User-Agent naming the project, a single call, the result cached on disk)."""
    out = raw_path(pc["name"])
    if out.exists():
        print(f"{out} exists; not downloading again")
        return out
    out.parent.mkdir(parents=True, exist_ok=True)
    body = urllib.parse.urlencode({"data": overpass_query(pc["bbox_deg"])}).encode()
    req = urllib.request.Request(OVERPASS_URL, data=body, headers={
        "User-Agent": "uavsim-research/0.1 (UAV-NOMA planning simulator; one-off case-study download)"})
    with urllib.request.urlopen(req, timeout=300) as r:
        raw = r.read()
    json.loads(raw)                                   # fail loudly on an error page
    out.write_bytes(raw)
    print(f"saved {out} ({len(raw) / 1e6:.1f} MB)")
    return out


# ---------------------------------------------------------------- processing (pure, deterministic)
def parse_height(tags, levels_m):
    """(height_m or None, source) from OSM tags: 'height' > 'building:levels' x levels_m > None."""
    h = tags.get("height")
    if h is not None:
        try:
            v = float(str(h).lower().replace("m", "").strip())
            if 0 < v < 400:
                return v, "height"
        except ValueError:
            pass
    lv = tags.get("building:levels")
    if lv is not None:
        try:
            v = float(str(lv).split(";")[0].strip())
            if 0 < v < 100:
                return v * levels_m, "levels"
        except ValueError:
            pass
    return None, "none"


def _ring(geom, lat_c, lon_c, side):
    return [[round(c, 1) for c in to_local(p["lat"], p["lon"], lat_c, lon_c, side)] for p in geom]


def _inside(ring, side):
    return any(0 <= x <= side and 0 <= y <= side for x, y in ring)


def process(raw, pc):
    """Raw Overpass JSON (dict) + the place config -> the processed place (dict, local metres). Pure function."""
    lat_c, lon_c, side = pc["centre_deg"][0], pc["centre_deg"][1], float(pc["side_m"])
    buildings, rivers, shelters = [], [], []
    for el in sorted(raw.get("elements", []), key=lambda e: (e["type"], e["id"])):
        tags = el.get("tags", {})
        if "building" in tags and el["type"] in ("way", "relation"):
            if el["type"] == "way":
                rings = [el.get("geometry", [])]
            else:
                rings = [m.get("geometry", []) for m in el.get("members", [])
                         if m.get("role") == "outer" and m.get("type") == "way"]
            h, src = parse_height(tags, float(pc["levels_m"]))
            for k, g in enumerate(rings):
                if len(g) < 3:
                    continue
                ring = _ring(g, lat_c, lon_c, side)
                if ring[0] == ring[-1]:
                    ring = ring[:-1]
                if len(ring) >= 3 and _inside(ring, side):
                    buildings.append({"id": f"{el['type'][0]}{el['id']}" + (f"_{k}" if k else ""), "h": h,
                                      "src": src, "xy": ring})
        if tags.get("waterway") in ("river", "stream", "canal") and el["type"] == "way":
            rivers.append({"id": f"w{el['id']}", "name": tags.get("name:en") or tags.get("name") or "",
                           "kind": tags["waterway"], "xy": _ring(el.get("geometry", []), lat_c, lon_c, side)})
        kind = None
        if tags.get("amenity") in SHELTER_AMENITY:
            kind = tags["amenity"]
        elif tags.get("emergency") == "assembly_point":
            kind = "assembly_point"
        elif tags.get("leisure") == "park":
            kind = "park"
        if kind is not None:
            if el["type"] == "node":
                x, y = to_local(el["lat"], el["lon"], lat_c, lon_c, side)
            elif el.get("geometry"):
                pts = el["geometry"][:-1] if len(el["geometry"]) > 1 else el["geometry"]
                x, y = to_local(sum(p["lat"] for p in pts) / len(pts), sum(p["lon"] for p in pts) / len(pts),
                                lat_c, lon_c, side)
            else:
                continue
            if 0 <= x <= side and 0 <= y <= side:
                shelters.append({"id": f"{el['type'][0]}{el['id']}", "kind": kind,
                                 "name": tags.get("name:en") or tags.get("name") or "", "x": round(x, 1),
                                 "y": round(y, 1)})
    return {"name": pc["name"], "title": pc["title"], "credit": CREDIT, "centre_deg": [lat_c, lon_c],
            "bbox_deg": pc["bbox_deg"], "side_m": side, "levels_m": float(pc["levels_m"]),
            "projection": "equirectangular around the box centre, R = 6371008.8 m; origin = south-west corner",
            "buildings": buildings, "rivers": rivers, "shelters": shelters}


def write_processed(place, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(place, separators=(",", ":"), sort_keys=True), encoding="utf-8")
    nb = len(place["buildings"])
    tagged = sum(b["h"] is not None for b in place["buildings"])
    print(f"saved {path} ({path.stat().st_size / 1e6:.2f} MB): {nb} buildings ({tagged} with a height or levels tag), "
          f"{len(place['rivers'])} waterway lines, {len(place['shelters'])} shelter candidates")


def place_config(name=None):
    pc = dict(md.CFG["place"])
    if name:
        pc = {**pc, **md.CFG["places"][name]}
    else:
        pc = {**pc, **md.CFG["places"][pc["name"]]}
    pc["bbox_deg"] = bbox_from_centre(pc["centre_deg"][0], pc["centre_deg"][1], float(pc["side_m"]))
    return pc


if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else "process"
    md.apply_profile("place_kathmandu_bagmati")
    pc = place_config()
    print("bbox [S, W, N, E]:", [round(v, 6) for v in pc["bbox_deg"]])
    if what == "fetch":
        fetch(pc)
    if what in ("fetch", "process"):
        raw = json.loads(raw_path(pc["name"]).read_text(encoding="utf-8"))
        write_processed(process(raw, pc), processed_path(pc["name"]))
