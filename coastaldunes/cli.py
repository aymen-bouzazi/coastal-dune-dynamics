"""Command-line entry points. Local paths and outputs never need publication."""

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

from .analysis import annual_climate
from .fronts import measure_features
from .planning import export_priority, priority_scores, relate_changes
from .raster import export_sand, rasterize_classes, read, vector_records
from .workflow import demo, dump, empty_output, run


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    p = commands.add_parser("run", help="Historical analysis, hindcast and future scenarios.")
    p.add_argument("config", type=Path)
    p = commands.add_parser("demo", help="Create invented rasters and run the whole workflow.")
    p.add_argument("--output", type=Path, required=True)
    p = commands.add_parser(
        "rasterize", help="Rasterise reviewed polygons on one fixed template grid."
    )
    p.add_argument("vector", type=Path)
    p.add_argument("--template", type=Path, required=True)
    p.add_argument("--field", default="class_code")
    p.add_argument("--output", type=Path, required=True)
    p = commands.add_parser("sand", help="Export unsmoothed sand pixels as a GeoPackage layer.")
    p.add_argument("raster", type=Path)
    p.add_argument("--output", type=Path, required=True)
    p = commands.add_parser(
        "fronts", help="Measure keyed fronts, swept areas and reviewed corridors."
    )
    p.add_argument("vector", type=Path)
    p.add_argument(
        "--bearing", type=float, required=True, help="Movement bearing clockwise from north."
    )
    p.add_argument("--spacing", type=float, default=10.0)
    p.add_argument("--half-length", type=float, default=2000.0)
    p.add_argument("--correspondence", choices=["nearest", "farthest_forward"], default="nearest")
    p.add_argument("--output", type=Path, required=True)
    p = commands.add_parser(
        "climate", help="Aggregate complete monthly climate with explicit rainfall units."
    )
    p.add_argument("csv", type=Path)
    p.add_argument(
        "--precipitation-kind", choices=["monthly_total", "mean_daily_rate"], required=True
    )
    p.add_argument("--output", type=Path, required=True)
    p = commands.add_parser(
        "priority", help="Sum supplied binary participatory criteria and join reviewed zones."
    )
    p.add_argument("zones", type=Path)
    p.add_argument("criteria_csv", type=Path)
    p.add_argument("--criteria", nargs="+", required=True)
    p.add_argument("--output", type=Path, required=True)
    p = commands.add_parser(
        "relate", help="Descriptive associations; observed/scenario intervals stay separate."
    )
    p.add_argument("metrics_csv", type=Path)
    p.add_argument("front_summary_csv", type=Path)
    p.add_argument("--output", type=Path, required=True)
    p = commands.add_parser(
        "correct", help="Save a separate expert-edited map and a traceable correction log."
    )
    p.add_argument("raster", type=Path)
    p.add_argument("corrections_csv", type=Path)
    p.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "run":
            print(json.dumps(run(args.config), indent=2))
        elif args.command == "demo":
            config = demo(args.output)
            print(json.dumps(run(config), indent=2))
        elif args.command == "rasterize":
            rasterize_classes(args.vector, args.template, args.output, args.field)
        elif args.command == "sand":
            a, grid = read(args.raster)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            export_sand(args.output, a, grid)
        elif args.command == "fronts":
            records, crs = vector_records(args.vector)
            summary, transects = measure_features(
                records, args.bearing, args.spacing, args.half_length, args.correspondence
            )
            output = empty_output(args.output)
            summary.to_csv(output / "front_summary.csv", index=False)
            transects.to_csv(output / "transects.csv", index=False)
            dump(
                output / "measurement.json",
                {
                    "crs": str(crs),
                    "bearing_deg": args.bearing,
                    "spacing_m": args.spacing,
                    "half_length_m": args.half_length,
                    "correspondence": args.correspondence,
                    "maximum_is_sampled": True,
                    "missing_intersections_are_not_zero": True,
                },
            )
        elif args.command == "priority":
            scores = priority_scores(
                pd.read_csv(args.criteria_csv, dtype={"zone_id": str}), args.criteria
            )
            output = empty_output(args.output)
            export_priority(args.zones, scores, output / "priority.gpkg")
            scores.to_csv(output / "priority_scores.csv", index=False)
            dump(
                output / "criteria.json",
                {
                    "criteria": args.criteria,
                    "rule": "unweighted sum of supplied binary judgements",
                    "warning": "Criteria and zone boundaries require actual participatory input.",
                },
            )
        elif args.command == "relate":
            joined, associations = relate_changes(
                pd.read_csv(args.metrics_csv), pd.read_csv(args.front_summary_csv)
            )
            output = empty_output(args.output)
            joined.to_csv(output / "interval_changes.csv", index=False)
            associations.to_csv(output / "descriptive_associations.csv", index=False)
        elif args.command == "climate":
            if args.output.exists():
                raise ValueError("Output already exists.")
            result = annual_climate(pd.read_csv(args.csv), args.precipitation_kind)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            result.to_csv(args.output, index=False)
    except (ValueError, OSError, KeyError, ImportError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2
    return 0
