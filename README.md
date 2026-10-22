# Routing tiles for Brazil

[Valhalla](https://github.com/valhalla/valhalla) routing tiles for each state of Brazil, built each
month from OpenStreetMap, for an open-source offline motorcycle navigation app.

Each release is tagged with the day of the OpenStreetMap data and has:

- `manifest.json`: the build, the Valhalla version, and for each state its file, size, SHA-256 and
  tile count;
- `br-xx.tar.gz`: the Valhalla tiles (graph levels 0 to 2, no elevation) that touch the state's
  box. All states of a release come from one build and can be unpacked into one folder together.

Built by `build.py` with Valhalla 3.9.1 (`ghcr.io/valhalla/valhalla-scripted`, pinned by digest) from
[Geofabrik's Brazil extract](https://download.geofabrik.de/south-america/brazil.html).

## License

The tiles are a database derived from OpenStreetMap data, © OpenStreetMap contributors, and are
available under the [Open Database License 1.0](https://opendatacommons.org/licenses/odbl/1-0/).
See [openstreetmap.org/copyright](https://www.openstreetmap.org/copyright).

The scripts in this repository are under GPL-3.0-or-later.
