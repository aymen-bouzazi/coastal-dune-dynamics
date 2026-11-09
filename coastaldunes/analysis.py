"""Areas, change-specific validation and explicitly defined landscape metrics."""

import numpy as np
import pandas as pd
from scipy.ndimage import generate_binary_structure, label

from .model import CLASSES, check_array


def class_areas(array, pixel_area):
    a = check_array(array)
    counts = np.bincount(a[a >= 0], minlength=9)
    return pd.DataFrame(
        {
            "class_code": range(9),
            "class_name": CLASSES,
            "pixels": counts,
            "area_ha": counts * pixel_area / 10000,
        }
    )


def evaluate(base, reference, prediction):
    """Evaluate a hindcast against the reference classification, not field truth.

    Reference Ghost is unknown and excluded. A predicted Ghost at a known
    reference pixel counts as an error, rather than being removed from scoring.
    Change-only metrics additionally require a known baseline class.
    """
    base, reference, prediction = map(check_array, (base, reference, prediction))
    if not (base.shape == reference.shape == prediction.shape):
        raise ValueError("Validation maps must have identical shapes.")
    valid = (base >= 0) & (reference >= 0) & (reference < 8)
    if (prediction[valid] < 0).any():
        raise ValueError("Prediction has lost valid baseline coverage.")
    if not valid.any():
        raise ValueError("No comparable reference pixels.")
    truth, pred = reference[valid], prediction[valid]
    cm = np.bincount(truth.astype(np.int64) * 9 + pred, minlength=81).reshape(9, 9)
    rows = []
    for cls in range(8):
        tp, support, assigned = int(cm[cls, cls]), int(cm[cls].sum()), int(cm[:, cls].sum())
        rows.append(
            {
                "class_code": cls,
                "class_name": CLASSES[cls],
                "reference_pixels": support,
                "predicted_pixels": assigned,
                "precision": tp / assigned if assigned else None,
                "recall": tp / support if support else None,
                "f1": 2 * tp / (support + assigned) if support + assigned else None,
            }
        )
    known = valid & (base < 8)
    actual_change = known & (reference != base)
    predicted_change = known & (prediction != base)
    hit = actual_change & predicted_change & (reference == prediction)
    wrong = actual_change & predicted_change & (reference != prediction)
    missed = actual_change & ~predicted_change
    false = ~actual_change & predicted_change
    denominator = int((hit | wrong | missed | false).sum())
    summary = {
        "evaluated_pixels": int(valid.sum()),
        "excluded_pixels": int((~valid).sum()),
        "overall_accuracy": float((truth == pred).mean()),
        "persistence_accuracy": float((base[valid] == truth).mean()),
        "predicted_ghost_on_known_reference": int((pred == 8).sum()),
        "change_hits": int(hit.sum()),
        "wrong_change_destination": int(wrong.sum()),
        "missed_changes": int(missed.sum()),
        "false_changes": int(false.sum()),
        "figure_of_merit": float(hit.sum() / denominator) if denominator else None,
        "change_recall": float(hit.sum() / actual_change.sum()) if actual_change.any() else None,
        "change_precision": float(hit.sum() / predicted_change.sum())
        if predicted_change.any()
        else None,
    }
    return summary, pd.DataFrame(rows), cm


def landscape_metrics(array, resolution, connectivity=4):
    """Merged forest/sand patches. Denominators are valid known landscape cells.

    Edge density counts shared edges with other known classes, excluding the
    raster border and edges to Ghost/NoData. Patch density is per 100 hectares.
    These are specified raster metrics, not a promise of all FRAGSTATS metrics.
    """
    a = check_array(array)
    if connectivity not in (4, 8) or resolution <= 0:
        raise ValueError("Use connectivity 4/8 and a positive metre resolution.")
    valid = (a >= 0) & (a < 8)
    area = int(valid.sum()) * resolution**2
    if not area:
        raise ValueError("No known landscape area.")
    counts = np.bincount(a[valid], minlength=8)
    p = counts[counts > 0] / counts.sum()
    out = {
        "known_area_ha": area / 10000,
        "shannon_diversity": float(-(p * np.log(p)).sum()),
        "connectivity": connectivity,
    }
    for name, codes in [("forest", (1, 2, 3)), ("sand", (5,))]:
        mask = np.isin(a, codes)
        labels, number = label(mask, generate_binary_structure(2, 1 if connectivity == 4 else 2))
        sizes = np.bincount(labels.ravel())[1:]
        edge_count = 0
        for axis in (0, 1):
            l, r = (
                ((slice(None, -1), slice(None)), (slice(1, None), slice(None)))
                if axis == 0
                else ((slice(None), slice(None, -1)), (slice(None), slice(1, None)))
            )
            edge_count += int(((mask[l] != mask[r]) & valid[l] & valid[r]).sum())
        out.update(
            {
                f"{name}_patch_count": int(number),
                f"{name}_patch_density_per_100ha": number / (area / 1_000_000),
                f"{name}_largest_patch_percent": float(sizes.max() * resolution**2 / area * 100)
                if number
                else 0.0,
                f"{name}_mean_patch_area_ha": float(sizes.mean() * resolution**2 / 10000)
                if number
                else None,
                f"{name}_edge_density_m_per_ha": edge_count * resolution / (area / 10000),
            }
        )
    return out


def annual_climate(table, precipitation_kind):
    """Aggregate complete monthly input; precipitation units are an explicit contract.

    Input dates identify months. temperature/wind_speed monthly means are weighted
    by calendar days; precipitation is either monthly total or mean daily rate.
    Missing months/values produce an error, not a plausible-looking annual total.
    """
    df = table.copy()
    if df.empty:
        raise ValueError("No monthly climate records supplied.")
    required = {"date", "temperature", "precipitation", "wind_speed"}
    if not required <= set(df):
        raise ValueError(f"Monthly climate needs columns {sorted(required)}.")
    if precipitation_kind not in ("monthly_total", "mean_daily_rate"):
        raise ValueError("Specify monthly_total or mean_daily_rate for precipitation.")
    dates = pd.to_datetime(df["date"], errors="raise")
    if dates.isna().any() or dates.dt.tz is not None:
        raise ValueError("Climate dates must be nonmissing timezone-naive calendar dates.")
    df["month"] = dates.dt.to_period("M")
    if df["month"].duplicated().any():
        raise ValueError("One climate row per month is required.")
    for col in sorted(required - {"date"}):
        df[col] = pd.to_numeric(df[col], errors="raise")
        if not np.isfinite(df[col]).all():
            raise ValueError(f"Missing/sentinel climate values in {col}. Clean the source first.")
    if (df["precipitation"] < 0).any() or (df["wind_speed"] < 0).any():
        raise ValueError("Negative precipitation/wind; check units and missing-value sentinels.")
    for col, hi in [("relative_humidity", 100), ("wind_direction", 360)]:
        if col in df:
            df[col] = pd.to_numeric(df[col], errors="raise")
            if not np.isfinite(df[col]).all() or not df[col].between(0, hi).all():
                raise ValueError(f"Invalid {col} values or units.")
    rows = []
    for year, part in df.groupby(df["month"].dt.year):
        if len(part) != 12:
            raise ValueError(f"Incomplete monthly coverage for {year}.")
        days = part["month"].dt.days_in_month.to_numpy()
        precipitation = part["precipitation"].to_numpy()
        rows.append(
            {
                "year": int(year),
                "temperature": float(np.average(part["temperature"], weights=days)),
                "wind_speed": float(np.average(part["wind_speed"], weights=days)),
                "precipitation_total": float(
                    np.sum(precipitation * days)
                    if precipitation_kind == "mean_daily_rate"
                    else precipitation.sum()
                ),
            }
        )
        if "relative_humidity" in part:
            rows[-1]["relative_humidity"] = float(
                np.average(part["relative_humidity"], weights=days)
            )
        if "wind_direction" in part:
            angle = np.deg2rad(part["wind_direction"].to_numpy())
            weights = part["wind_speed"].to_numpy() * days
            east, north = np.sum(np.sin(angle) * weights), np.sum(np.cos(angle) * weights)
            magnitude = np.hypot(east, north)
            rows[-1]["wind_from_direction_deg"] = (
                float(np.rad2deg(np.arctan2(east, north)) % 360) if magnitude > 1e-10 else None
            )
    return pd.DataFrame(rows)
