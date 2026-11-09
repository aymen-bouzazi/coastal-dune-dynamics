"""Geometry-based front measurements with explicit site/date correspondence."""

import numpy as np
import pandas as pd
from shapely.geometry import LineString


def area_velocity(swept_area, midline, years):
    """Report equation v=S/(t*L). Inputs must already be in a metre CRS."""
    if swept_area.geom_type not in ("Polygon", "MultiPolygon") or midline.geom_type not in (
        "LineString",
        "MultiLineString",
    ):
        raise ValueError("Provide a swept polygon and its reviewed median-front line.")
    if (
        not swept_area.is_valid
        or not midline.is_valid
        or swept_area.is_empty
        or midline.length <= 0
        or years <= 0
    ):
        raise ValueError("Need valid geometry, positive line length and positive elapsed years.")
    return {
        "swept_area_m2": float(swept_area.area),
        "midline_length_m": float(midline.length),
        "elapsed_years": years,
        "mean_advance_m": float(swept_area.area / midline.length),
        "mean_velocity_m_per_year": float(swept_area.area / (midline.length * years)),
    }


def line_parts(geometry):
    if geometry.geom_type == "LineString":
        return [geometry] if geometry.length else []
    if hasattr(geometry, "geoms"):
        return [part for g in geometry.geoms for part in line_parts(g)]
    return []


def point_parts(geometry):
    if geometry.is_empty:
        return []
    if geometry.geom_type == "Point":
        return [geometry]
    if geometry.geom_type in ("MultiPoint", "GeometryCollection"):
        return [point for part in geometry.geoms for point in point_parts(part)]
    # Overlapping line segments do not specify an unambiguous front intersection.
    raise ValueError("Transect overlaps the target front along a line.")


def transects(
    old, new, corridor, bearing_deg, spacing_m=10.0, half_length_m=2000.0, correspondence="nearest"
):
    """Sample all old-front components inside a reviewed corridor.

    Bearing is movement direction clockwise from north, not an inferred direction
    from the first feature. Positive displacement follows that bearing. The maximum
    is a sampled estimate, not an exact continuous maximum. Missing intersections
    are retained as missing, never replaced by a zero displacement.
    """
    if old.geom_type not in ("LineString", "MultiLineString") or new.geom_type not in (
        "LineString",
        "MultiLineString",
    ):
        raise ValueError("Fronts must be lines, not polygons.")
    if corridor.geom_type not in ("Polygon", "MultiPolygon") or not corridor.is_valid:
        raise ValueError("Provide a reviewed corridor polygon.")
    if not np.isfinite(bearing_deg) or spacing_m <= 0 or half_length_m <= 0:
        raise ValueError("Need finite bearing and positive sampling distances.")
    if correspondence not in ("nearest", "farthest_forward"):
        raise ValueError("Unknown front-correspondence rule.")
    direction = np.array([np.sin(np.deg2rad(bearing_deg)), np.cos(np.deg2rad(bearing_deg))])
    direction[np.abs(direction) < 1e-14] = 0.0  # exact cardinal bearings avoid endpoint roundoff
    target = new.intersection(corridor)
    rows = []
    for component, line in enumerate(line_parts(old.intersection(corridor))):
        positions = np.unique(np.r_[np.arange(0.0, line.length, spacing_m), line.length])
        for distance in positions:
            point = line.interpolate(distance)
            xy = np.array([point.x, point.y])
            ray = LineString(
                [xy - half_length_m * direction, xy + half_length_m * direction]
            ).intersection(corridor)
            intersections = target.intersection(ray)
            record = {
                "component": component,
                "along_component_m": float(distance),
                "x": float(point.x),
                "y": float(point.y),
                "distance_m": None,
                "intersection_count": 0,
                "status": "missing_intersection",
            }
            try:
                points = point_parts(intersections)
            except ValueError:
                record["status"] = "overlapping_front"
                rows.append(record)
                continue
            if points:
                values = np.array([np.dot(np.array([p.x, p.y]) - xy, direction) for p in points])
                record["intersection_count"] = len(values)
                if correspondence == "farthest_forward":
                    forward = values[values >= 0]
                    chosen = forward.max() if len(forward) else values.max()
                else:
                    chosen = values[np.argmin(np.abs(values))]
                record.update(distance_m=float(chosen), status="ok")
            rows.append(record)
    if not rows:
        raise ValueError("The old front does not intersect the corridor as a line.")
    return pd.DataFrame(rows)


def measure_features(records, bearing_deg, spacing_m, half_length_m, correspondence):
    """Features are keyed by site + kind + date(s), never by row order or shape IDs."""
    grouped = {}
    for feature in records:
        p = feature["properties"]
        if "site" not in p or "kind" not in p:
            raise ValueError("Every geometry needs site and kind attributes.")
        site = str(p["site"])
        kind = p["kind"]
        if kind == "front":
            key = (kind, int(p["year"]))
        elif kind in ("swept_area", "midline"):
            key = (kind, int(p["from_year"]), int(p["to_year"]))
        elif kind == "corridor":
            key = (kind,)
        else:
            raise ValueError(f"Unknown geometry kind: {kind}")
        if key in grouped.setdefault(site, {}):
            raise ValueError("Duplicate site/date/kind key. Merge multipart geometry explicitly.")
        grouped[site][key] = feature["geometry"]
    summaries, details = [], []
    for site, geometries in grouped.items():
        years = sorted(k[1] for k in geometries if k[0] == "front")
        for start, end in zip(years[:-1], years[1:]):
            row = {"site": site, "from_year": start, "to_year": end}
            polygon = geometries.get(("swept_area", start, end))
            midline = geometries.get(("midline", start, end))
            if (polygon is None) != (midline is None):
                raise ValueError("A swept-area polygon and median line must be provided together.")
            if polygon is not None:
                row.update(area_velocity(polygon, midline, end - start))
            corridor = geometries.get(("corridor",))
            if corridor is not None:
                data = transects(
                    geometries[("front", start)],
                    geometries[("front", end)],
                    corridor,
                    bearing_deg,
                    spacing_m,
                    half_length_m,
                    correspondence,
                )
                data.insert(0, "site", site)
                data["from_year"], data["to_year"] = start, end
                details.append(data)
                valid = data["distance_m"].dropna()
                row.update(
                    sampled_transects=len(data),
                    matched_transects=len(valid),
                    ambiguous_transects=int((data["intersection_count"] > 1).sum()),
                    sampled_max_signed_advance_m=float(valid.max()) if len(valid) else None,
                )
            if polygon is None and corridor is None:
                raise ValueError(
                    "Provide swept-area/median-line inputs or a corridor for each site."
                )
            summaries.append(row)
    if not summaries:
        raise ValueError("Need at least two dated fronts per site.")
    return pd.DataFrame(summaries), pd.concat(
        details, ignore_index=True
    ) if details else pd.DataFrame()
