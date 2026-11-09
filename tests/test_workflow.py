import json
from pathlib import Path

import fiona
import numpy as np
import pandas as pd
import pytest
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import box, mapping

from coastaldunes.cli import main
from coastaldunes.planning import export_priority, priority_scores
from coastaldunes.raster import Grid, export_sand, rasterize_classes, read, write
from coastaldunes.workflow import demo, run


def grid():
    return Grid(4, 3, from_origin(0, 90, 30, 30), rasterio.crs.CRS.from_epsg(32632))


def test_geotiff_roundtrip_preserves_ghost_and_nodata(tmp_path):
    a = np.full((3, 4), 2, np.int16)
    a[0, 0] = -1
    a[1, 1] = 8
    write(tmp_path / "a.tif", a, grid())
    got, actual_grid = read(tmp_path / "a.tif")
    np.testing.assert_array_equal(a, got)
    assert actual_grid.matches(grid())
    with pytest.raises(ValueError):
        write(tmp_path / "a.tif", a, grid())


def test_latitude_longitude_grid_rejected():
    geographic = Grid(4, 3, from_origin(0, 1, 0.01, 0.01), rasterio.crs.CRS.from_epsg(4326))
    with pytest.raises(ValueError):
        geographic.validate()


def test_shifted_grid_is_not_treated_as_aligned():
    shifted = Grid(4, 3, from_origin(1, 90, 30, 30), grid().crs)
    assert not grid().matches(shifted)


def test_nodata_must_not_collide_with_agriculture(tmp_path):
    path = tmp_path / "bad.tif"
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=3,
        width=4,
        count=1,
        dtype="int16",
        transform=grid().transform,
        crs=grid().crs,
        nodata=0,
    ) as dst:
        dst.write(np.full((3, 4), 2, np.int16), 1)
    with pytest.raises(ValueError, match="collides"):
        read(path)


def test_sand_export_preserves_unsmoothed_raster_area(tmp_path):
    a = np.full((3, 4), 2, np.int16)
    a[:, :2] = 5
    export_sand(tmp_path / "sand.gpkg", a, grid())
    with fiona.open(tmp_path / "sand.gpkg") as src:
        from shapely.geometry import shape

        area = sum(shape(f["geometry"]).area for f in src)
    assert area == 6 * 900


def write_zones(path):
    schema = {"geometry": "Polygon", "properties": {"zone_id": "str", "class_code": "int"}}
    with fiona.open(
        path, "w", driver="GPKG", schema=schema, crs_wkt=grid().crs.to_wkt(), layer="zones"
    ) as dst:
        for zone, polygon, code in [("A", box(0, 0, 60, 90), 5), ("B", box(60, 0, 120, 90), 2)]:
            dst.write(
                {"geometry": mapping(polygon), "properties": {"zone_id": zone, "class_code": code}}
            )


def test_vector_rasterisation_uses_template_and_class_fields(tmp_path):
    write(tmp_path / "template.tif", np.full((3, 4), 2, np.int16), grid())
    write_zones(tmp_path / "zones.gpkg")
    rasterize_classes(tmp_path / "zones.gpkg", tmp_path / "template.tif", tmp_path / "out.tif")
    a, actual_grid = read(tmp_path / "out.tif")
    assert actual_grid.matches(grid())
    np.testing.assert_array_equal(a[:, :2], 5)
    np.testing.assert_array_equal(a[:, 2:], 2)


def test_priority_join_uses_identifiers_not_feature_order(tmp_path):
    write_zones(tmp_path / "zones.gpkg")
    table = pd.DataFrame({"zone_id": ["B", "A"], "housing": [0, 1]})
    scores = priority_scores(table, ["housing"])
    export_priority(tmp_path / "zones.gpkg", scores, tmp_path / "priority.gpkg")
    with fiona.open(tmp_path / "priority.gpkg") as source:
        got = {f["properties"]["zone_id"]: f["properties"]["priority_score"] for f in source}
    assert got == {"A": 1, "B": 0}


def test_full_demo_creates_validation_scenarios_and_audit(tmp_path):
    config = demo(tmp_path / "demo")
    cfg = json.loads(config.read_text())
    cfg["plots"] = False
    config.write_text(json.dumps(cfg))
    report = run(config)
    output = Path(report["output"])
    assert (output / "hindcast_2025.tif").exists()
    for year in [2030, 2035, 2040, 2045]:
        assert (output / f"lulc_{year}_scenario.tif").exists()
    meta = json.loads((output / "run.json").read_text())
    assert meta["hindcast_calibration_years"] == [2005, 2010, 2015, 2020]
    areas = pd.read_csv(output / "class_areas.csv")
    assert set(areas.phase) == {"observed", "simulated"}
    with pytest.raises(ValueError):
        run(config)


def test_hindcast_training_does_not_read_target_labels(tmp_path):
    config = demo(tmp_path / "demo")
    cfg = json.loads(config.read_text())
    cfg["plots"] = False
    config.write_text(json.dumps(cfg))
    report_a = run(config)
    target, g = read(config.parent / "raster_2025.tif")
    changed = target.copy()
    changed[target == 2] = 5
    write(config.parent / "changed_target.tif", changed, g)
    cfg["rasters"]["2025"] = "changed_target.tif"
    cfg["output"] = "other_results"
    config.write_text(json.dumps(cfg))
    report_b = run(config)
    a, _ = read(Path(report_a["output"]) / "hindcast_2025.tif")
    b, _ = read(Path(report_b["output"]) / "hindcast_2025.tif")
    np.testing.assert_array_equal(a, b)
    np.testing.assert_array_equal(
        pd.read_csv(Path(report_a["output"]) / "hindcast_transition.csv").values,
        pd.read_csv(Path(report_b["output"]) / "hindcast_transition.csv").values,
    )


def test_cli_errors_have_nonzero_exit(tmp_path, capsys):
    status = main(["run", str(tmp_path / "missing.json")])
    assert status == 2
    assert "Error:" in capsys.readouterr().err
