# Commands and private input contracts

Run from the repository directory after installing `requirements-dev.txt`.
Create your own virtual environment if needed. Both `python coastal.py ...` and the
installed `coastal-dunes ...` entry point call the same functions.

## Historical analysis, validation and projection

```bash
python coastal.py run config/project.local.json
```

Paths in the JSON resolve from the configuration file's directory. Use a new `output`
directory per run. Keep rule changes in separate configurations/runs. The example
contains no real site coordinates or study inputs. It assumes canonical class codes;
no encoding is inferred from the alphabetical order of class labels.

`rasters` maps dates to classified GeoTIFFs, not raw Landsat bands. Dates must be consecutive
five-year intervals. `holdout_year` must follow at least two earlier maps. `future_years`
must follow the most recent supplied observed date in five-year steps. `aoi_mask`, if
provided, is a single-band, exactly aligned binary raster (1 inside, 0/masked outside).
The mask can restrict an existing domain, not fill outside data automatically.

| Output | Meaning |
|---|---|
| `class_areas.csv` | Canonical class counts and hectares; phase and footprint are explicit |
| `counts_*.csv`, `transition_area_ha_*.csv` | Historical counts and transition hectares |
| `hindcast_transition.csv` | Fitted matrix using dates before the target only |
| `hindcast_<year>.tif` | Untouched one-step prediction |
| `hindcast_error_<year>.tif` | 0=agreement, 1=error, -1=not evaluated |
| `hindcast_confusion.csv`, `hindcast_per_class.csv` | Comparison with the classified reference |
| `validation.json` | Overall, persistence and change-specific metrics |
| `lulc_<year>_scenario.tif` | Untouched scenario output |
| `transition_for_<year>.csv`, `scenario_audit.json` | Matrices and observed/simulated history used |
| `coverage.csv`, `landscape_metrics.csv` | Domain coverage and specified patch metrics |
| `lulc_*.png`, `area_timeseries.png` | Local visual summaries; observations/scenarios distinguished |
| `run.json` | Configuration, dependency versions, grid, source hashes and assumptions |

Input TIFF hashes include GDAL-reported sidecars. All outputs and their provenance can
contain private data or paths; keep the entire output directory private.

## Convert classified polygons to the common grid

```bash
python coastal.py rasterize private/classes_2010.gpkg --template private/raster_2005.tif --field class_code --output private/raster_2010.tif
```

The vector file and categorical template must use the same metre CRS. The template
supplies the grid, not a new class encoding. The selected field contains canonical
integer codes 0..8 or exact canonical names. NoData outside polygon coverage is -1.
Overlapping polygons at cell centres are rejected instead of letting feature order
choose a class. All-touched rasterisation is off. Review edge-pixel sensitivity separately.

## Export sand polygons

```bash
python coastal.py sand private/raster_2025.tif --output results/sand_2025.gpkg
```

GeoPackage preserves the projected CRS. Polygon area equals the unsmoothed sand-cell
area. Do not smooth in geographic degrees or measure a cartographically simplified
boundary as though it were the original classification. Convert display copies to
KML in QGIS if needed; retain the metre-CRS measurement source.

## Mean dune-front velocity and maximum displacement

Use a vector layer containing the following explicit attributes. GeoPackage is recommended
because a layer can contain mixed geometry types and long field names. Other supported
Fiona formats may impose field/type limitations. All records must have a metre CRS.

| `kind` | Geometry | Attributes |
|---|---|---|
| `front` | LineString / MultiLineString | `site`, `year` |
| `corridor` | Polygon / MultiPolygon | `site` |
| `swept_area` | Polygon / MultiPolygon | `site`, `from_year`, `to_year` |
| `midline` | LineString / MultiLineString | `site`, `from_year`, `to_year` |

Keys must be unique. Supply at least two fronts per site. Consecutive available front
dates form measurement pairs; use a separate layer containing only the desired pair for
a direct long-term comparison. A reviewed corridor enables transects. A swept polygon
AND its matching median line enable the report's mean-velocity equation. You can provide
both. Missing criteria are errors, not inferred geometry.

```bash
python coastal.py fronts private/fronts.gpkg --bearing 90 --spacing 10 --half-length 2000 --output results/front_measurements
```

Here 90 is an invented eastward example, not the study's actual movement direction.
Bearing is clockwise from north. One call uses one bearing; split site layers when their
movement directions differ. It should represent the intended measurement direction
relative to the reviewed fragmentation corridor, not the feature order in a shapefile.

`front_summary.csv` includes the S/(tL) result when its inputs exist, matched/missing
transect counts and sampled maximum signed displacement. `transects.csv` retains each
sample and ambiguity count. Missing intersections are blank. Multiple front intersections
use nearest correspondence by default; `--correspondence farthest_forward` provides a
separate maximum-envelope interpretation. These alternatives need visual review.
Repeat with a smaller spacing and verify sensitivity. Do not add maxima from different
intervals and describe the sum as one tracked physical trajectory.

## Separately documented expert corrections

```bash
python coastal.py correct results/run_01/lulc_2030_scenario.tif private/edits_2030.csv --output results/expert_scenario_2030
```

The correction table must contain `row`, `col` (zero-based), `from_class`, `to_class`,
`reason`, and `source`. Expected original classes must match. Duplicate cell edits,
missing justifications, out-of-bounds coordinates and changes from NoData are rejected.
The original raster remains unchanged. `expert_edited.tif`, the correction table and
source hashes are saved separately. Document whether this represents an error repair
or an expert scenario constraint; neither makes the edited map an untouched prediction.
Corrections are not fed into the main forecasts or validation automatically.

## Monthly climate

```bash
python coastal.py climate private/monthly_climate.csv --precipitation-kind mean_daily_rate --output results/annual_climate.csv
```

Required columns: `date`, `temperature`, `precipitation`, `wind_speed`. Each row represents
one month, and every year must contain all 12 months with finite values. Clean NASA POWER
missing-value sentinels first. Temperature and wind speed are monthly means in consistent
units. Choose precipitation units explicitly: `mean_daily_rate` multiplies each month's
rate by its number of days; `monthly_total` sums the supplied monthly totals.

Optional `relative_humidity` is in percent; `wind_direction` is a meteorological FROM
bearing in degrees clockwise from north. Direction is averaged circularly, weighted
by wind speed and days. This is an annual resultant direction, not a complete wind
rose or proof of the transport-dominant wind. Temperature/RH/speed means are day-weighted.
Direction is undefined for a vanishing resultant. No key, credentials or automatic
network request is required or included.

## Landscape/displacement associations

```bash
python coastal.py relate results/run_01/landscape_metrics.csv results/front_measurements/front_summary.csv --output results/associations
```

Creates endpoint metric differences and descriptive Pearson correlations separately
for each site and observed/scenario-derived interval. Missing endpoints raise an error.
At least three nonconstant complete intervals are needed for r; otherwise it is blank.
No p-values or causal interpretations are generated. Overlapping periods and repeated
sites are not independent samples; inspect interval construction before interpretation.

## Participatory priority scores

```bash
python coastal.py priority private/zones.gpkg private/criteria.csv --criteria housing agriculture heritage --output results/priority
```

The criterion names above are invented examples, not a reconstructed consultation.
The polygon layer and CSV must share unique stable `zone_id` values. Preserve IDs as
strings, including leading zeros. Each selected criterion must be an observed 0 or 1;
missing values are rejected. The output is their unweighted sum, following the report's
participatory procedure. All zones must have criteria and all criteria rows must have
geometry. The GeoPackage map and scoring table stay private.

The participants choose the criteria and judgements; the code does not replace the
consultation or determine actual dune-stabilisation interventions.
