"""Strict grid/mask handling. Reprojection is an explicit upstream task."""

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import rasterio
from rasterio.features import rasterize, shapes
from shapely.geometry import mapping, shape

from .model import CLASSES, NODATA, check_array


@dataclass(frozen=True)
class Grid:
    width: int
    height: int
    transform: object
    crs: object

    @property
    def pixel_area(self):
        t = self.transform
        return abs(t.a * t.e - t.b * t.d)

    def validate(self):
        if (
            not self.crs
            or not self.crs.is_projected
            or self.crs.linear_units not in ("metre", "meter")
        ):
            raise ValueError("Use a projected CRS in metres for area and distance measurements.")
        t = self.transform
        if t.b != 0 or t.d != 0 or t.a <= 0 or t.e >= 0:
            raise ValueError("Directional kernels require a north-up, unrotated grid.")
        if self.width <= 0 or self.height <= 0:
            raise ValueError("Empty raster grid.")
        if not np.isclose(t.a, -t.e):
            raise ValueError(
                "Use square cells for the documented neighbourhood and landscape metrics."
            )

    def matches(self, other):
        return (
            self.width == other.width
            and self.height == other.height
            and self.crs == other.crs
            and self.transform == other.transform
        )


def read(path):
    with rasterio.open(path) as src:
        if src.count != 1:
            raise ValueError(f"{Path(path).name}: expected one categorical band.")
        grid = Grid(src.width, src.height, src.transform, src.crs)
        grid.validate()
        if src.nodata is not None and src.nodata in range(9):
            raise ValueError("NoData collides with a valid class code. Resolve the mask upstream.")
        raw = src.read(1, masked=True)
        if not np.issubdtype(raw.dtype, np.integer):
            raise ValueError("Class rasters must use an integer storage type.")
        a = raw.astype(np.int32).filled(NODATA)
    check_array(a)
    return a.astype(np.int16), grid


def write(path, array, grid):
    path = Path(path)
    if path.exists():
        raise ValueError(f"Refusing to overwrite {path.name}.")
    check_array(array)
    if array.shape != (grid.height, grid.width):
        raise ValueError("Array shape does not match the target grid.")
    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=grid.height,
        width=grid.width,
        count=1,
        dtype="int16",
        crs=grid.crs,
        transform=grid.transform,
        nodata=NODATA,
        compress="deflate",
    ) as dst:
        dst.write(np.asarray(array, dtype=np.int16), 1)


def vector_records(path):
    """Read SHP/GPKG/GeoJSON with explicit CRS. No assumptions about feature order."""
    import fiona

    with fiona.open(path) as source:
        crs = rasterio.crs.CRS.from_user_input(source.crs) if source.crs else None
        if not crs or not crs.is_projected or crs.linear_units not in ("metre", "meter"):
            raise ValueError("Vector measurements require an explicit projected CRS in metres.")
        records = [
            {"properties": dict(feature["properties"]), "geometry": shape(feature["geometry"])}
            for feature in source
            if feature["geometry"] is not None
        ]
    if any(not f["geometry"].is_valid or f["geometry"].is_empty for f in records):
        raise ValueError("Repair invalid/empty vector geometry upstream, with an audit record.")
    return records, crs


def rasterize_classes(vector_path, template_path, output_path, field="class_code"):
    """One template for ALL years, with no interpolation of class labels."""
    _, grid = read(template_path)
    records, crs = vector_records(vector_path)
    if crs != grid.crs:
        raise ValueError(
            "Vector and template CRS differ; reproject explicitly before rasterisation."
        )
    features = []
    for feature in records:
        value = feature["properties"][field]
        if isinstance(value, str) and value in CLASSES:
            value = CLASSES.index(value)
        if not isinstance(value, (int, np.integer)) or value not in range(9):
            raise ValueError("Class field must contain canonical integer codes or names.")
        if feature["geometry"].geom_type not in ("Polygon", "MultiPolygon"):
            raise ValueError("Rasterisation requires polygon features.")
        features.append((mapping(feature["geometry"]), int(value)))
    if not features:
        raise ValueError("No polygons supplied.")
    # Reject centre-pixel overlaps: the feature order must not decide class identity.
    count = rasterize(
        [(geom, 1) for geom, _ in features],
        out_shape=(grid.height, grid.width),
        transform=grid.transform,
        fill=0,
        merge_alg=rasterio.enums.MergeAlg.add,
        dtype="int32",
    )
    if (count > 1).any():
        raise ValueError("Overlapping polygon coverage at cell centres; resolve upstream.")
    array = rasterize(
        features,
        out_shape=(grid.height, grid.width),
        transform=grid.transform,
        fill=NODATA,
        dtype="int16",
        all_touched=False,
    )
    write(output_path, array, grid)


def export_sand(path, array, grid):
    """GeoPackage polygons from UNSMOOTHED pixels; display smoothing is separate."""
    import fiona

    path = Path(path)
    if path.exists():
        raise ValueError("Vector output already exists.")
    schema = {"geometry": "Polygon", "properties": {"class_code": "int"}}
    mask = array == 5
    with fiona.open(
        path, "w", driver="GPKG", crs_wkt=grid.crs.to_wkt(), schema=schema, layer="sand"
    ) as dst:
        for geometry, value in shapes(array.astype("int16"), mask=mask, transform=grid.transform):
            dst.write({"geometry": geometry, "properties": {"class_code": int(value)}})
