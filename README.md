# Coastal dune dynamics

A Python workflow for land-cover change analysis, constrained CA–Markov scenarios,
and dune-front measurements. It implements the modelling part of my engineering
final-year project on sand encroachment into the coastal forests of Zaouiet El Mgaiez
(Bir El Oued forests, Nabeul, Tunisia).

The repository starts with **classified land-cover maps**. It does not contain the
Landsat training data or recreate the upstream land-cover classifier. Field data,
the report, consultation records, study coordinates and generated results stay private.
Public examples and tests use invented data.

## Run the demonstration

Python 3.10 or later:

```bash
python -m pip install -r requirements-dev.txt
python coastal.py demo --output private/demo
python -m pytest -q
python tools/check_public_files.py
```

This creates small synthetic GeoTIFFs, analyses historical changes, hindcasts 2025,
and generates scenarios for 2030–2045. It writes maps, area curves, transition tables,
landscape metrics and validation diagnostics to `private/demo/results/`.
Synthetic scores are software checks, not estimates of performance at the study site.
Use a new directory for each run: existing inputs and outputs are not overwritten.

## Run on real maps

Copy `config/project.example.json` to `config/project.local.json` and set the paths
of the local maps. Relative paths resolve from the configuration file's directory.

```bash
python coastal.py run config/project.local.json
```

The maps must share **exactly the same CRS, extent, dimensions and transform**, with
square north-up cells in a projected metre CRS. The report uses a 30 m UTM grid;
this implementation reads the actual resolution rather than assuming every input is 30 m.
No automatic interpolation or reprojection of categories is performed.

| Code | Class |
|---|---|
| 0 | agriculture (`agri`) |
| 1 | sparse forest (`cforet`) |
| 2 | dense forest (`dforet`) |
| 3 | herbaceous forest (`hforet`) |
| 4 | rocky beach (`rockybeach`) |
| 5 | dry sand (`sand`) |
| 6 | water |
| 7 | wet sand |
| 8 | explicit eligible unknown pixel (`ghost`) |
| -1 | outside the study domain / missing coverage |

Check the input class mapping: numbers alone cannot establish their ecological meaning.
The report sometimes uses a different descriptive label for class 4; verify the actual
classification schema before analysis. NoData must not be encoded as agriculture 0.
Masked cells remain outside the simulation. Ghost is explicit class 8 **inside** the
eligible domain and can evolve only to sand. An optional binary AOI mask can further
restrict the domain without creating new eligible land.

## What the workflow does

1. Checks categorical values, grid compatibility and masks.
2. Calculates class areas and adjacent/long-term transition tables.
3. Fits transition probabilities on maps before the selected hindcast year.
4. Makes a one-step five-year hindcast and compares it with the later classified map,
   including a persistence baseline and change-specific Figure of Merit.
5. Generates future scenarios: each pixel is scored from its neighbours' classes, their
   transition probabilities and resistances (the report's CA–Markov formula), with
   directional kernels for sand (towards ESE/SE) and agriculture (towards north).
6. Calculates specified forest/sand patch metrics and saves full run provenance.

The default scenario retains the report's locked agriculture, water and wet sand.
This means sand **cannot** replace agriculture in that scenario, even where a general
statement says it can colonise other classes. Changing that assumption should be run as a separately
named scenario.

`forecast_mode="dynamic"` uses a rolling window, including earlier simulated maps in
later transition estimates, as in the original notebook. The audit labels this feedback explicitly.
`"fixed"` uses observed transitions only. Predictions are never described as new observations.
Neither version enforces class-area quotas or a physical sediment budget. See
[the method](docs/METHOD.md) for the scoring rule and the alternative `own_row` rule.

[Method and corrections](docs/METHOD.md) · [commands](docs/COMMANDS.md) ·
[report alignment](docs/REPORT_ALIGNMENT.md) · [privacy/publishing](docs/PRIVACY.md)

## Read the code

- `model.py`: transition estimation, local scores, constraints and time steps.
- `raster.py`: masks, grid checks, rasterisation and sand polygon export.
- `analysis.py`: areas, hindcast metrics, landscape metrics and climate aggregation.
- `fronts.py`: swept-area velocity and sampled directional front displacement.
- `planning.py`: participatory binary criteria and descriptive associations.
- `corrections.py`: separately logged expert edits; never in-place forecast changes.
- `workflow.py`: orchestration, plots and provenance.
- `cli.py`: small command-line interfaces.

## Status

Tested on synthetic arrays, rasters and vector files. This version has not yet been
re-run on the study maps, so the accuracy and forecast figures in the report are not
results of this code. Front digitisation, field validation and participatory scoring
are done outside the code.

Code under the MIT licence; no rights to the research data are granted.
See also the [development notes](docs/DEVELOPMENT.md).
