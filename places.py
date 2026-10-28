#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 the OpenTripper contributors.
# Additional permission under GPLv3 section 7: see ADDITIONAL-PERMISSION.md.
"""Builds the named places the app searches with no network: one SQLite file per state.

From the same OpenStreetMap extract as the routing tiles (build.py): every node, way or relation
with a name and a tag that makes it a place one rides to (a shop, a fuel station, a workshop, a
hospital, an airport...). osmium-tool picks them out, run in Debian's image so that nothing is
installed on the machine; a way or a relation is placed at the middle of its outline. Each place
goes to the state whose outline holds it (outlines.json, the app's own `assets/regions/br.json`).

A file holds one table:
  places(name, folded, kind, lat, lon, extent, locality, city)
    name     as OpenStreetMap writes it
    folded   what is searched: the name and the others it goes by (alt_name, short_name, loc_name,
             official_name), words run together split ("RIOgaleão", "BarraShopping"), each in lower
             case, with no accents, anything but letters and digits as one space, joined by " | "
             so that each name is scored on its own
    extent   meters across its outline, 0 for a point: how big a place is, so that the airport
             comes before the café named after it
    kind     the value of the tag that made it a place ("fuel", "supermarket", "aerodrome")
    lat, lon micro-degrees
    locality, city  from its addr:suburb and addr:city tags, when it has them (empty otherwise)

and the speed cameras OpenStreetMap has in the state (nodes tagged highway=speed_camera):
  cameras(lat, lon, kmh)
    kmh      the limit it enforces, from its maxspeed tag; 0 when it has none
Their direction tag is left out: it points the wrong way on most highways, many mappers tagging
where the camera looks (docs/research/speed-cameras.md).

Usage: places.py <extract.osm.pbf> <out dir> [state id ...]
Writes <out>/places-br-xx.sqlite.gz and returns, for build.py's manifest, what it wrote.
"""

import gzip
import hashlib
import json
import math
import pathlib
import re
import sqlite3
import subprocess
import sys
import unicodedata

HERE = pathlib.Path(__file__).resolve().parent
OUTLINES = HERE / "outlines.json"
STATES = HERE / "states.json"
IMAGE = "debian:bookworm-slim"
# osmium is held to this, so that a full run cannot take the machine's memory (a laptop froze, 2026-10-28).
MEMORY = "3g"

# The tags that make something a place to ride to, in the order the kind is taken from.
KEYS = ["amenity", "shop", "tourism", "aeroway", "railway", "public_transport", "leisure", "healthcare", "office", "craft", "historic"]
# For these keys only these values: a named runway or platform is not a destination.
ONLY = {
    "aeroway": {"aerodrome", "terminal", "heliport"},
    "railway": {"station", "halt"},
    "public_transport": {"station"},
    "leisure": {"park", "stadium", "sports_centre", "marina", "water_park", "beach_resort", "nature_reserve", "golf_course"},
}
# Kinds named often but never ridden to.
NEVER = {"bench", "waste_basket", "vending_machine", "parking_space", "grave_yard", "post_box", "telephone", "atm"}


def fold(text):
    plain = "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn")
    return re.sub(r"[^0-9a-z]+", " ", plain.lower()).strip()


# The other names a place goes by, which riders type: "Maracanã" is the stadium's short_name,
# "Aeroporto do Galeão" the airport's loc_name.
OTHER_NAMES = ["alt_name", "short_name", "loc_name", "official_name"]


def searched(tags):
    """The text a place is found by: all its names, words run together split, folded."""
    names = [tags.get("name", "")] + [tags[k] for k in OTHER_NAMES if tags.get(k)]
    split = [re.sub(r"([a-z])([A-Z])", r"\1 \2", re.sub(r"([A-Z]{2,})([a-z])", r"\1 \2", n)) for n in names]
    return " | ".join(dict.fromkeys(f for f in (fold(n) for n in names + split) if f))


def extent(geometry):
    """Meters across a geometry's box, roughly: 0 for a point."""
    if geometry["type"] == "Point":
        return 0
    points = []
    def walk(c):
        if isinstance(c[0], (int, float)):
            points.append(c)
        else:
            for x in c:
                walk(x)
    walk(geometry["coordinates"])
    lats = [p[1] for p in points]
    lons = [p[0] for p in points]
    across_lat = (max(lats) - min(lats)) * 111_000
    across_lon = (max(lons) - min(lons)) * 111_000 * math.cos(math.radians(sum(lats) / len(lats)))
    return round(math.hypot(across_lat, across_lon))


def extract(pbf):
    """
    The named places of the extract, as GeoJSON features, one a line, from osmium; kept from an
    earlier run when it is newer than the extract.
    """
    folder = pbf.parent.resolve()
    done = folder / "places.geojsonseq"
    if done.exists() and done.stat().st_mtime > pbf.stat().st_mtime:
        return done
    filters = " ".join(f"nwr/{key}" for key in KEYS)
    script = (
        "apt-get -qq update >/dev/null && apt-get -qq install -y osmium-tool >/dev/null && "
        f"osmium tags-filter -O -o /data/named.osm.pbf /data/{pbf.name} nwr/name && "
        f"osmium tags-filter -O -o /data/places.osm.pbf /data/named.osm.pbf {filters} && "
        "osmium export -O -f geojsonseq -x print_record_separator=false --geometry-types=point,linestring,polygon "
        "-o /data/places.geojsonseq /data/places.osm.pbf"
    )
    subprocess.run(["docker", "run", "--rm", "--memory", MEMORY, "-v", f"{folder}:/data", IMAGE, "sh", "-c", script], check=True)
    return folder / "places.geojsonseq"


def extract_cameras(pbf):
    """The speed cameras of the extract, as GeoJSON points, one a line; kept from an earlier run when newer than the extract."""
    folder = pbf.parent.resolve()
    done = folder / "cameras.geojsonseq"
    if done.exists() and done.stat().st_mtime > pbf.stat().st_mtime:
        return done
    script = (
        "apt-get -qq update >/dev/null && apt-get -qq install -y osmium-tool >/dev/null && "
        f"osmium tags-filter -O -R -o /data/cameras.osm.pbf /data/{pbf.name} n/highway=speed_camera && "
        "osmium export -O -f geojsonseq -x print_record_separator=false --geometry-types=point "
        "-o /data/cameras.geojsonseq /data/cameras.osm.pbf"
    )
    subprocess.run(["docker", "run", "--rm", "--memory", MEMORY, "-v", f"{folder}:/data", IMAGE, "sh", "-c", script], check=True)
    return done


def speed_of(tags):
    """A camera's limit in km/h from its maxspeed tag ("60", "60 km/h"); 0 when none can be read."""
    match = re.match(r"\s*(\d{2,3})", tags.get("maxspeed", ""))
    return int(match.group(1)) if match and 10 <= int(match.group(1)) <= 150 else 0


def middle(geometry):
    """A point for a geometry: itself, or the average of its outline's points."""
    kind, coords = geometry["type"], geometry["coordinates"]
    if kind == "Point":
        return coords[1], coords[0]
    points = coords if kind == "LineString" else coords[0] if kind == "Polygon" else coords[0][0]
    return sum(p[1] for p in points) / len(points), sum(p[0] for p in points) / len(points)


def kind_of(tags):
    for key in KEYS:
        value = tags.get(key)
        if value and value not in NEVER and (key not in ONLY or value in ONLY[key]):
            return value
    return None


def inside(lat, lon, ring):
    odd = False
    for i in range(len(ring)):
        a, b = ring[i], ring[(i + 1) % len(ring)]
        if (a[0] > lat) != (b[0] > lat) and lon < (b[1] - a[1]) * (lat - a[0]) / (b[0] - a[0]) + a[1]:
            odd = not odd
    return odd


def state_of(lat, lon, states, rings):
    """The state whose outline holds the point; [rings] are each state's rings with their boxes."""
    for sid, state in states.items():
        s, w, n, e = state["box"]
        if s <= lat <= n and w <= lon <= e and any(
            rs <= lat <= rn and rw <= lon <= re_ and inside(lat, lon, ring) for ring, (rs, rw, rn, re_) in rings[sid]
        ):
            return sid
    return None


def build(pbf, out, only=None):
    states = json.loads(STATES.read_text())
    if only:
        states = {k: v for k, v in states.items() if k in only}
    outlines = json.loads(OUTLINES.read_text())
    rings = {
        sid: [(ring, (min(p[0] for p in ring), min(p[1] for p in ring), max(p[0] for p in ring), max(p[1] for p in ring))) for ring in outlines[sid]["rings"]]
        for sid in states
    }
    found = {sid: [] for sid in states}
    with open(extract(pbf), encoding="utf-8") as lines:
        for line in lines:
            feature = json.loads(line)
            tags = feature["properties"]
            name, kind = tags.get("name", "").strip(), kind_of(tags)
            if not name or not kind:
                continue
            lat, lon = middle(feature["geometry"])
            sid = state_of(lat, lon, states, rings)
            if sid:
                found[sid].append((name, searched(tags), kind, round(lat * 1e6), round(lon * 1e6), extent(feature["geometry"]), tags.get("addr:suburb", ""), tags.get("addr:city", "")))
    cameras = {sid: [] for sid in states}
    with open(extract_cameras(pbf), encoding="utf-8") as lines:
        for line in lines:
            feature = json.loads(line)
            lat, lon = middle(feature["geometry"])
            sid = state_of(lat, lon, states, rings)
            if sid:
                cameras[sid].append((round(lat * 1e6), round(lon * 1e6), speed_of(feature["properties"])))
    out.mkdir(parents=True, exist_ok=True)
    written = {}
    for sid, rows in found.items():
        # A way and its own node often both carry the name: one place where they say the same.
        # The bigger of the two is kept: the outline knows the place's size, its node does not.
        rows = list({(r[1], r[2], r[3] // 2000, r[4] // 2000): r for r in sorted(rows, key=lambda r: r[5])}.values())
        db_path = out / f"places-{sid}.sqlite"
        db_path.unlink(missing_ok=True)
        db = sqlite3.connect(db_path)
        db.execute("CREATE TABLE places(name TEXT, folded TEXT, kind TEXT, lat INTEGER, lon INTEGER, extent INTEGER, locality TEXT, city TEXT)")
        db.executemany("INSERT INTO places VALUES (?,?,?,?,?,?,?,?)", sorted(rows, key=lambda r: r[1]))
        db.execute("CREATE TABLE cameras(lat INTEGER, lon INTEGER, kmh INTEGER)")
        db.executemany("INSERT INTO cameras VALUES (?,?,?)", cameras[sid])
        db.commit()
        db.execute("VACUUM")
        db.close()
        name = f"places-{sid}.sqlite.gz"
        with open(db_path, "rb") as source, gzip.open(out / name, "wb", compresslevel=9) as target:
            target.write(source.read())
        written[sid] = {
            "file": name, "bytes": (out / name).stat().st_size, "unpacked": db_path.stat().st_size,
            "sha256": hashlib.sha256((out / name).read_bytes()).hexdigest(), "places": len(rows), "cameras": len(cameras[sid]),
        }
        db_path.unlink()
        print(sid, len(rows), "places", len(cameras[sid]), "cameras", written[sid]["bytes"] // 1000, "kB", flush=True)
    return written


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    build(pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2]), set(sys.argv[3:]) or None)
