#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 the OpenTripper contributors.
# Additional permission under GPLv3 section 7: see ADDITIONAL-PERMISSION.md.
"""Builds the routing data the app downloads: Valhalla tiles for Brazil, one archive per state.

All of Brazil is built at once, so that every state's archive comes from the same build: Valhalla
cannot use tiles of two builds together, and a rider with two states needs them to join at the
border. A state's archive holds the tiles that touch its box (the boxes of the app's
MapRegions.kt), so neighbours share some tiles; the app unpacks them into one folder.

Steps, each skipped when its output is already there:
  1. download Geofabrik's Brazil extract (about 2 GB);
  2. build the tiles with Valhalla's own image, pinned (about 3 GB of tiles);
  3. write <out>/br-xx.tar.gz for each state;
  4. write <out>/places-br-xx.sqlite.gz, the named places searched with no network (places.py);
  5. write <out>/manifest.json, which names both.

Needs Python 3 and Docker. Usage: build.py <work dir> <out dir>
Runs the same on a computer and in the data repository's monthly job (repository/.github/workflows/build.yml).
"""

import datetime
import email.utils
import hashlib
import json
import os
import pathlib
import subprocess
import sys
import tarfile
import urllib.request

import places

EXTRACT = "https://download.geofabrik.de/south-america/brazil-latest.osm.pbf"
# Valhalla 3.9.1, the version valhalla-mobile 0.6.4 follows. Pinned: tiles must suit the engine on the phone.
IMAGE = "ghcr.io/valhalla/valhalla-scripted@sha256:eaad372b8ef31e3e4592c442875aeb1375fbf5aeaa0d259b469e3b46583ab10d"
VALHALLA = "3.9.1"
STATES = pathlib.Path(__file__).resolve().parent / "states.json"
TILE_SIZE = {0: 4.0, 1: 1.0, 2: 0.25}


def download(work):
    pbf = work / "custom_files" / "brazil-latest.osm.pbf"
    if not pbf.exists():
        pbf.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["curl", "-fL", "-o", str(pbf) + ".part", EXTRACT], check=True)
        os.rename(str(pbf) + ".part", pbf)
    with urllib.request.urlopen(urllib.request.Request(EXTRACT, method="HEAD"), timeout=60) as answer:
        modified = email.utils.parsedate_to_datetime(answer.headers["Last-Modified"])
    return modified.date().isoformat()


def build(work):
    tiles = work / "custom_files" / "valhalla_tiles"
    if tiles.exists() and any(tiles.rglob("*.gph")):
        return tiles
    subprocess.run([
        "docker", "run", "--rm", "-v", f"{(work / 'custom_files').resolve()}:/custom_files",
        "-e", "serve_tiles=False", "-e", "build_tar=False", "-e", "build_admins=True",
        "-e", "build_time_zones=True", "-e", "build_elevation=False", "-e", "force_rebuild=True",
        "-e", "use_default_speeds_config=True", "-e", "server_threads=4", IMAGE,
    ], check=True)
    return tiles


def tile_box(path):
    """The box of a tile, (south, west, north, east), from its path under the tiles' folder: level/aaa/bbb[/ccc].gph."""
    parts = path.parts
    level = int(parts[0])
    tile_id = int("".join(parts[1:]).removesuffix(".gph"))
    size = TILE_SIZE[level]
    row, col = divmod(tile_id, int(360 / size))
    south, west = -90 + row * size, -180 + col * size
    return south, west, south + size, west + size


def cut(tiles, out, data_day):
    out.mkdir(parents=True, exist_ok=True)
    all_tiles = sorted(tiles.rglob("*.gph"))
    boxes = {t: tile_box(t.relative_to(tiles)) for t in all_tiles}
    states = json.loads(STATES.read_text())
    manifest = {"build": data_day, "valhalla": VALHALLA, "made": datetime.date.today().isoformat(), "states": {}}
    for sid, state in states.items():
        s, w, n, e = state["box"]
        chosen = [t for t, (ts, tw, tn, te) in boxes.items() if tw < e and te > w and ts < n and tn > s]
        name = f"{sid}.tar.gz"
        with tarfile.open(out / name, "w:gz", compresslevel=6) as archive:
            for t in chosen:
                archive.add(t, arcname=str(t.relative_to(tiles)))
        digest = hashlib.sha256((out / name).read_bytes()).hexdigest()
        manifest["states"][sid] = {
            "file": name, "bytes": (out / name).stat().st_size, "sha256": digest,
            "tiles": len(chosen), "unpacked": sum(t.stat().st_size for t in chosen),
        }
        print(sid, len(chosen), "tiles", manifest["states"][sid]["bytes"] // 1_000_000, "MB", flush=True)
    return manifest


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    work, out = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
    data_day = download(work)
    tiles = build(work)
    manifest = cut(tiles, out, data_day)
    manifest["places"] = places.build(work / "custom_files" / "brazil-latest.osm.pbf", out)
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
