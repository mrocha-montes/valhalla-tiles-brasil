# Routing tiles for Brazil

[Valhalla](https://github.com/valhalla/valhalla) routing tiles for each state of Brazil, built each
month from OpenStreetMap, for an open-source offline motorcycle navigation app.

Each release is tagged with the day of the OpenStreetMap data and has:

- `manifest.json`: the build, the Valhalla version, and for each state its file, size, SHA-256 and
  tile count;
- `br-xx.tar.gz`: the Valhalla tiles (graph levels 0 to 2, no elevation) that touch the state's
  box. All states of a release come from one build and can be unpacked into one folder together.
- `places-br-xx.sqlite.gz`: the state's named places (shops, fuel stations, workshops, airports...),
  for searching with no network: name, the names it also goes by, kind, position and size; and
  the speed cameras OpenStreetMap has (`highway=speed_camera`), with the limit they enforce. Two
  SQLite tables described in `places.py`. Placed in a state by its outline (`outlines.json`).
  Listed under `places` in the manifest.

Built by `build.py` (the places by `places.py`, with osmium-tool in Debian's image) with Valhalla 3.9.1 (`ghcr.io/valhalla/valhalla-scripted`, pinned by digest) from
[Geofabrik's Brazil extract](https://download.geofabrik.de/south-america/brazil.html).

## License

The tiles and the places are databases derived from OpenStreetMap data, © OpenStreetMap contributors, and are
available under the [Open Database License 1.0](https://opendatacommons.org/licenses/odbl/1-0/).
See [openstreetmap.org/copyright](https://www.openstreetmap.org/copyright).

The scripts in this repository are under GPL-3.0-or-later.
