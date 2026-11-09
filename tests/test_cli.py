import fiona
import numpy as np
import pandas as pd
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import LineString, box, mapping

from coastaldunes.cli import main
from coastaldunes.raster import Grid, write


def test_geospatial_cli_commands_on_invented_features(tmp_path):
    grid = Grid(4, 3, from_origin(0, 90, 30, 30), rasterio.crs.CRS.from_epsg(32632))
    raster = tmp_path / "input.tif"
    write(raster, np.full((3, 4), 2, np.int16), grid)
    zones = tmp_path / "zones.gpkg"
    with fiona.open(
        zones,
        "w",
        driver="GPKG",
        crs_wkt=grid.crs.to_wkt(),
        schema={"geometry": "Polygon", "properties": {"zone_id": "str", "class_code": "int"}},
    ) as dst:
        dst.write(
            {
                "geometry": mapping(box(0, 0, 120, 90)),
                "properties": {"zone_id": "A", "class_code": 5},
            }
        )
    assert (
        main(
            [
                "rasterize",
                str(zones),
                "--template",
                str(raster),
                "--output",
                str(tmp_path / "classes.tif"),
            ]
        )
        == 0
    )
    assert (
        main(["sand", str(tmp_path / "classes.tif"), "--output", str(tmp_path / "sand.gpkg")]) == 0
    )
    pd.DataFrame({"zone_id": ["A"], "housing": [1]}).to_csv(tmp_path / "criteria.csv", index=False)
    assert (
        main(
            [
                "priority",
                str(zones),
                str(tmp_path / "criteria.csv"),
                "--criteria",
                "housing",
                "--output",
                str(tmp_path / "priority"),
            ]
        )
        == 0
    )
    pd.DataFrame(
        {
            "row": [0],
            "col": [0],
            "from_class": [2],
            "to_class": [5],
            "reason": ["Invented correction"],
            "source": ["Software check"],
        }
    ).to_csv(tmp_path / "edits.csv", index=False)
    assert (
        main(
            [
                "correct",
                str(raster),
                str(tmp_path / "edits.csv"),
                "--output",
                str(tmp_path / "edited"),
            ]
        )
        == 0
    )
    fronts = tmp_path / "fronts.gpkg"
    props = {"kind": "str", "site": "str", "year": "int", "from_year": "int", "to_year": "int"}
    features = [
        ("front", 2005, None, None, LineString([(0, 0), (0, 100)])),
        ("front", 2010, None, None, LineString([(20, 0), (20, 100)])),
        ("corridor", None, None, None, box(-10, -10, 30, 110)),
        ("swept_area", None, 2005, 2010, box(0, 0, 20, 100)),
        ("midline", None, 2005, 2010, LineString([(10, 0), (10, 100)])),
    ]
    with fiona.open(
        fronts,
        "w",
        driver="GPKG",
        crs_wkt=grid.crs.to_wkt(),
        schema={"geometry": "Unknown", "properties": props},
    ) as dst:
        for kind, year, start, end, geom in features:
            dst.write(
                {
                    "geometry": mapping(geom),
                    "properties": {
                        "kind": kind,
                        "site": "A",
                        "year": year,
                        "from_year": start,
                        "to_year": end,
                    },
                }
            )
    assert (
        main(
            ["fronts", str(fronts), "--bearing", "90", "--output", str(tmp_path / "front_results")]
        )
        == 0
    )
    result = pd.read_csv(tmp_path / "front_results/front_summary.csv").iloc[0]
    assert result.mean_velocity_m_per_year == 4
    assert result.sampled_max_signed_advance_m == 20


def test_climate_and_descriptive_association_commands(tmp_path):
    climate = pd.DataFrame(
        {
            "date": pd.date_range("2020-01-01", periods=12, freq="MS"),
            "temperature": 20.0,
            "precipitation": 1.0,
            "wind_speed": 3.0,
        }
    )
    climate.to_csv(tmp_path / "monthly.csv", index=False)
    assert (
        main(
            [
                "climate",
                str(tmp_path / "monthly.csv"),
                "--precipitation-kind",
                "mean_daily_rate",
                "--output",
                str(tmp_path / "annual.csv"),
            ]
        )
        == 0
    )
    fields = [
        "forest_largest_patch_percent",
        "forest_edge_density_m_per_ha",
        "sand_patch_density_per_100ha",
    ]
    metrics = pd.DataFrame(
        {"year": [2005, 2010], "phase": ["observed", "observed"], **{f: [1, 2] for f in fields}}
    )
    metrics.to_csv(tmp_path / "metrics.csv", index=False)
    pd.DataFrame(
        {
            "site": ["A"],
            "from_year": [2005],
            "to_year": [2010],
            "sampled_max_signed_advance_m": [20],
        }
    ).to_csv(tmp_path / "front.csv", index=False)
    assert (
        main(
            [
                "relate",
                str(tmp_path / "metrics.csv"),
                str(tmp_path / "front.csv"),
                "--output",
                str(tmp_path / "associations"),
            ]
        )
        == 0
    )
