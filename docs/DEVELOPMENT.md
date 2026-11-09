# Development notes

The code is organised as ordinary functions in small modules. Comments explain
assumptions and units. The tests target the scientific failure modes of this kind of
model: time leakage, spatial alignment, NoData/Ghost handling, kernel direction,
resistance, missing intersections, zone correspondence and persistence-dominated
validation.

Keep changes small and run `python -m pytest -q` and `python tools/check_public_files.py`
before each commit.

Next step on the real maps: inspect the worst hindcast transitions, compare them with
the persistence baseline, and test fixed versus rolling scenario matrices.
