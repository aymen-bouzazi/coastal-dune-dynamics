"""Participatory binary criteria: preserve supplied judgements, sum transparently."""

from pathlib import Path

import fiona
import pandas as pd
from shapely.geometry import mapping

from .raster import vector_records


def priority_scores(table, criteria):
    if table.empty:
        raise ValueError("No participatory criteria records supplied.")
    if not criteria or len(set(criteria)) != len(criteria) or "zone_id" in criteria:
        raise ValueError("Specify a nonempty, unique list of criterion columns.")
    if not {"zone_id", *criteria} <= set(table):
        raise ValueError("Criteria table needs zone_id and every selected criterion.")
    df = table[["zone_id", *criteria]].copy()
    if df["zone_id"].isna().any():
        raise ValueError("Missing zone identifiers.")
    df["zone_id"] = df["zone_id"].astype(str).str.strip()
    if df["zone_id"].eq("").any() or df["zone_id"].duplicated().any():
        raise ValueError("Zone identifiers must be unique and nonempty.")
    if not df[criteria].isin([0, 1]).all().all():
        raise ValueError(
            "Participatory criteria must be observed binary 0/1 values; no imputation."
        )
    df["priority_score"] = df[criteria].astype(int).sum(axis=1)
    return df


def export_priority(vector_path, scores, path):
    records, crs = vector_records(vector_path)
    zones = {}
    for feature in records:
        value = feature["properties"]["zone_id"]
        if value is None or not str(value).strip():
            raise ValueError("Missing zone identifier in vector geometry.")
        zone = str(value).strip()
        if zone in zones or feature["geometry"].geom_type not in ("Polygon", "MultiPolygon"):
            raise ValueError("One unique polygon/multipolygon feature is required per zone_id.")
        zones[zone] = feature["geometry"]
    if set(zones) != set(scores["zone_id"]):
        raise ValueError("Zone geometries and criteria identifiers must match exactly.")
    path = Path(path)
    if path.exists():
        raise ValueError("Priority map already exists.")
    schema = {"geometry": "Unknown", "properties": {"zone_id": "str", "priority_score": "int"}}
    with fiona.open(
        path, "w", driver="GPKG", schema=schema, crs_wkt=crs.to_wkt(), layer="priority"
    ) as dst:
        for row in scores.itertuples():
            dst.write(
                {
                    "geometry": mapping(zones[row.zone_id]),
                    "properties": {
                        "zone_id": row.zone_id,
                        "priority_score": int(row.priority_score),
                    },
                }
            )


def relate_changes(metrics, advances):
    """Descriptive associations separated into observed and scenario-derived intervals.

    No p-values: few, spatially/temporally dependent intervals do not establish a
    causal relationship or provide independent validation of a simulated scenario.
    """
    fields = [
        "forest_largest_patch_percent",
        "forest_edge_density_m_per_ha",
        "sand_patch_density_per_100ha",
    ]
    if not {"year", "phase", *fields} <= set(metrics) or metrics["year"].duplicated().any():
        raise ValueError("Need one metrics row per year, with phase and the documented fields.")
    required = {"site", "from_year", "to_year", "sampled_max_signed_advance_m"}
    if not required <= set(advances):
        raise ValueError("Use the front_summary.csv schema with sampled displacement.")
    indexed = metrics.set_index("year")
    rows = []
    for row in advances.itertuples():
        if (
            row.from_year not in indexed.index
            or row.to_year not in indexed.index
            or row.to_year <= row.from_year
        ):
            raise ValueError(
                "Every displacement interval needs both endpoint metrics and increasing dates."
            )
        a, b = indexed.loc[row.from_year], indexed.loc[row.to_year]
        record = {
            "site": str(row.site),
            "from_year": row.from_year,
            "to_year": row.to_year,
            "phase": "observed" if a.phase == b.phase == "observed" else "scenario",
            "distance_m": row.sampled_max_signed_advance_m,
        }
        for field in fields:
            record["delta_" + field] = b[field] - a[field]
        rows.append(record)
    joined = pd.DataFrame(rows)
    associations = []
    for (site, phase), part in joined.groupby(["site", "phase"]):
        for field in fields:
            pair = part[["distance_m", "delta_" + field]].dropna()
            value = None
            if len(pair) >= 3 and pair.nunique().min() > 1:
                value = float(pair.corr().iloc[0, 1])
            associations.append(
                {
                    "site": site,
                    "phase": phase,
                    "metric": field,
                    "intervals": len(pair),
                    "descriptive_pearson_r": value,
                }
            )
    return joined, pd.DataFrame(associations)
