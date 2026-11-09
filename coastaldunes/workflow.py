"""Historical analysis, chronological hindcast and documented future scenarios."""

import hashlib
import importlib.metadata
import json
import platform
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio

from .analysis import class_areas, evaluate, landscape_metrics
from .model import CLASSES, Rules, estimate_transition, forecast, step, transition_counts
from .raster import Grid, read, write


def dump(path, value):
    Path(path).write_text(
        json.dumps(value, indent=2, allow_nan=False, default=str) + "\n", encoding="utf-8"
    )


def empty_output(path):
    path = Path(path)
    if path.exists() and (not path.is_dir() or any(path.iterdir())):
        raise ValueError("Choose a new or empty output directory; earlier results are preserved.")
    path.mkdir(parents=True, exist_ok=True)
    return path


def plot_map(path, array, title):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import BoundaryNorm, ListedColormap
    from matplotlib.patches import Patch

    colors = [
        "#e0a458",
        "#8ab17d",
        "#235347",
        "#c5d86d",
        "#8c8c8c",
        "#f7d67a",
        "#4b8bbe",
        "#b7dae2",
        "#cab8ce",
    ]
    cmap = ListedColormap(colors)
    cmap.set_bad("white")
    fig, ax = plt.subplots(figsize=(7, 6))
    ax.imshow(
        np.ma.masked_less(array, 0),
        cmap=cmap,
        norm=BoundaryNorm(np.arange(-0.5, 9.5), 9),
        interpolation="nearest",
    )
    ax.set_title(title)
    ax.set_axis_off()
    ax.legend(
        handles=[Patch(color=color, label=name) for color, name in zip(colors, CLASSES)],
        loc="upper left",
        bbox_to_anchor=(1, 1),
        fontsize=8,
    )
    fig.tight_layout()
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def plot_area_series(path, areas):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    data = areas.loc[areas["domain"].eq("common_observed_footprint")]
    observed_end = data.loc[data.phase.eq("observed"), "year"].max()
    fig, axes = plt.subplots(3, 3, figsize=(12, 9), sharex=True)
    for cls, ax in enumerate(axes.ravel()):
        part = data.loc[data.class_code.eq(cls)].sort_values("year")
        observed = part.loc[part.phase.eq("observed")]
        scenario = part.loc[part.year.ge(observed_end)]
        ax.plot(observed.year, observed.area_ha, "o-", label="Observed classification")
        if len(scenario) > 1:
            ax.plot(scenario.year, scenario.area_ha, "o--", label="Scenario")
        ax.set_title(CLASSES[cls])
        ax.set_ylabel("Area (ha)")
        ax.grid(alpha=0.2)
    axes[0, 0].legend(fontsize=7)
    fig.suptitle("Land-cover areas on the common historical footprint")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def run(config_path):
    config_path = Path(config_path).resolve()
    cfg = json.loads(config_path.read_text())
    resolve = lambda value: (config_path.parent / value).resolve()
    paths = {int(year): resolve(path) for year, path in cfg["rasters"].items()}
    years = sorted(paths)
    if len(years) < 3 or any(b - a != 5 for a, b in zip(years[:-1], years[1:])):
        raise ValueError("Provide at least three maps on consecutive five-year dates.")
    holdout = int(cfg.get("holdout_year", years[-1]))
    if holdout not in years or len([y for y in years if y < holdout]) < 2:
        raise ValueError("Holdout must be supplied and follow at least two calibration dates.")
    future = [int(y) for y in cfg.get("future_years", [])]
    rules_cfg = cfg.get("rules", {})
    rules = Rules(
        tuple(rules_cfg.get("resistance", Rules().resistance)),
        tuple(rules_cfg.get("locked", Rules().locked)),
        rules_cfg.get("allocation", "argmax"),
        rules_cfg.get("rule", "neighbours"),
    )
    rules.validate()
    aggregation = cfg.get("aggregation", "mean")
    mode = cfg.get("forecast_mode", "dynamic")
    seed = int(cfg.get("seed", 42))
    connectivity = int(cfg.get("connectivity", 4))
    maps, grid, checksums = {}, None, {}
    for year in years:
        array, current_grid = read(paths[year])
        if grid is not None and not grid.matches(current_grid):
            raise ValueError(
                f"Raster grid mismatch in {year}; align CRS, dimensions and transform upstream."
            )
        maps[year], grid = array, current_grid
        # Include sidecar masks/overviews reported by GDAL, not just the .tif bytes.
        with rasterio.open(paths[year]) as source:
            for filename in source.files:
                file = Path(filename)
                checksums[str(file)] = hashlib.sha256(file.read_bytes()).hexdigest()
    if cfg.get("aoi_mask"):
        mask_path = resolve(cfg["aoi_mask"])
        with rasterio.open(mask_path) as src:
            mg = Grid(src.width, src.height, src.transform, src.crs)
            if src.count != 1 or not grid.matches(mg):
                raise ValueError("AOI mask must share the exact land-cover grid.")
            values = src.read(1, masked=True)
            aoi = (values.filled(0) == 1) & ~np.ma.getmaskarray(values)
            if not np.isin(values.compressed(), [0, 1]).all() or not aoi.any():
                raise ValueError("AOI mask must contain 1 inside and 0/masked outside.")
            for filename in src.files:
                checksums[filename] = hashlib.sha256(Path(filename).read_bytes()).hexdigest()
        maps = {y: np.where(aoi, a, -1).astype(np.int16) for y, a in maps.items()}
    # Hindcast uses earlier observed maps ONLY, even though the target raster is loaded for scoring.
    calibration_years = [y for y in years if y < holdout]
    if holdout - calibration_years[-1] != 5:
        raise ValueError("Hindcast requires one five-year step from the last calibration map.")
    T = estimate_transition(maps, calibration_years, aggregation)
    pred = step(maps[calibration_years[-1]], T, rules, np.random.default_rng(seed))
    validation, per_class, confusion = evaluate(maps[calibration_years[-1]], maps[holdout], pred)
    outputs, audit = forecast(maps, years, future, rules, mode, aggregation, seed)
    output = empty_output(resolve(cfg["output"]))
    write(output / f"hindcast_{holdout}.tif", pred, grid)
    write(
        output / f"hindcast_error_{holdout}.tif",
        np.where(
            (maps[holdout] >= 0) & (maps[holdout] < 8) & (pred >= 0),
            (pred != maps[holdout]).astype(np.int16),
            -1,
        ),
        grid,
    )
    per_class.to_csv(output / "hindcast_per_class.csv", index=False)
    pd.DataFrame(confusion, index=CLASSES, columns=CLASSES).to_csv(
        output / "hindcast_confusion.csv"
    )
    pd.DataFrame(T, index=CLASSES[:8], columns=CLASSES[:8]).to_csv(
        output / "hindcast_transition.csv"
    )
    areas, metrics, coverage = [], [], []
    observed_domain = np.logical_and.reduce([maps[y] >= 0 for y in years])
    known_common = np.logical_and.reduce([(maps[y] >= 0) & (maps[y] < 8) for y in years])
    for year, array in {**maps, **outputs}.items():
        phase = "observed" if year in maps else "simulated"
        tables = [
            class_areas(array, grid.pixel_area).assign(domain="available"),
            class_areas(
                np.where(observed_domain, array, -1).astype(np.int16), grid.pixel_area
            ).assign(domain="common_observed_footprint"),
        ]
        areas.append(pd.concat(tables).assign(year=year, phase=phase))
        # Fixed known historical footprint controls area changes due solely to missing coverage.
        metric_map = np.where(known_common, array, -1).astype(np.int16)
        metrics.append(
            {
                "year": year,
                "phase": phase,
                **landscape_metrics(metric_map, grid.transform.a, connectivity),
            }
        )
        coverage.append(
            {
                "year": year,
                "phase": phase,
                "valid_cells": int((array >= 0).sum()),
                "ghost_cells": int((array == 8).sum()),
                "outside_cells": int((array < 0).sum()),
            }
        )
        if year in outputs:
            write(output / f"lulc_{year}_scenario.tif", array, grid)
        if cfg.get("plots", True):
            plot_map(
                output / f"lulc_{year}.png", array, f"{phase.capitalize()} land cover — {year}"
            )
    area_table = pd.concat(areas, ignore_index=True)
    area_table.to_csv(output / "class_areas.csv", index=False)
    if cfg.get("plots", True):
        plot_area_series(output / "area_timeseries.png", area_table)
        plot_map(output / f"hindcast_{holdout}.png", pred, f"Hindcast land cover — {holdout}")
    pd.DataFrame(metrics).to_csv(output / "landscape_metrics.csv", index=False)
    pd.DataFrame(coverage).to_csv(output / "coverage.csv", index=False)
    for start, end in list(zip(years[:-1], years[1:])) + [(years[0], years[-1])]:
        count = transition_counts(maps[start], maps[end], n=9)
        pd.DataFrame(count, index=CLASSES, columns=CLASSES).to_csv(
            output / f"counts_{start}_{end}.csv"
        )
        pd.DataFrame(count * grid.pixel_area / 10000, index=CLASSES, columns=CLASSES).to_csv(
            output / f"transition_area_ha_{start}_{end}.csv"
        )
    for record in audit:
        pd.DataFrame(record["matrix"], index=CLASSES[:8], columns=CLASSES[:8]).to_csv(
            output / f"transition_for_{record['year']}.csv"
        )
    dump(output / "validation.json", validation)
    dump(output / "scenario_audit.json", audit)
    dump(
        output / "run.json",
        {
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "config": cfg,
            "rules": asdict(rules),
            "input_sha256": checksums,
            "config_sha256": hashlib.sha256(config_path.read_bytes()).hexdigest(),
            "python": platform.python_version(),
            "versions": {
                p: importlib.metadata.version(p)
                for p in ["numpy", "pandas", "scipy", "rasterio", "shapely", "fiona"]
            },
            "class_codes": dict(enumerate(CLASSES)),
            "grid": {
                "crs": str(grid.crs),
                "transform": list(grid.transform),
                "width": grid.width,
                "height": grid.height,
            },
            "hindcast_calibration_years": calibration_years,
            "historical_common_known_cells": int(known_common.sum()),
            "warning": "Corrected scenario implementation; original report scores are not reproduced claims.",
        },
    )
    return {"output": str(output), "validation": validation, "forecast_years": future}


def demo(directory):
    """Small, wholly invented grid with no study coordinates or measurements."""
    from rasterio.transform import from_origin

    directory = empty_output(directory)
    grid = Grid(24, 20, from_origin(0, 600, 30, 30), rasterio.crs.CRS.from_epsg(32632))
    for i, year in enumerate(range(2005, 2030, 5)):
        a = np.full((20, 24), 2, np.int16)
        a[:2] = -1
        a[:, :2] = 6
        a[2:4, 2:] = 7
        a[4 : 8 + i, 2 : 9 + i] = 5
        a[12:17, 15:22] = 0
        a[15:, 5:10] = 1
        a[8:12, 18:22] = 4
        a[18, 18] = 8
        write(directory / f"raster_{year}.tif", a, grid)
    config = {
        "rasters": {str(y): f"raster_{y}.tif" for y in range(2005, 2030, 5)},
        "holdout_year": 2025,
        "future_years": [2030, 2035, 2040, 2045],
        "output": "results",
        "forecast_mode": "dynamic",
        "aggregation": "mean",
        "seed": 42,
        "plots": True,
        "connectivity": 4,
        "rules": asdict(Rules()),
    }
    dump(directory / "project.local.json", config)
    return directory / "project.local.json"
