# Explicit model definition

The report and notebook motivate a hybrid Markov/neighbourhood scenario. The notebook
contains several incompatible drafts. This revision defines one implementation; it is
not presented as an exact replay of the original results or a canonical quota-allocation
CA–Markov implementation.

## Transitions and time

Each update represents five years. Matrices are estimated only from aligned pixels
with known classes at both dates. Ghost and NoData provide no transition evidence.
The default is the arithmetic mean of period probability matrices, following the report;
periods in which a source class is absent contribute no evidence for that row. A never-seen
source class receives an identity row. `aggregation="pooled"` is a separate count-weighted
alternative, not an interchangeable name for the same calculation.

A 2005–2025 matrix must not be applied as though it were a five-year transition.
The long-term counts are descriptive; fitting uses consecutive five-year pairs.

## Local scores

The default rule (`rule="neighbours"`) is the report's formula, summed over the classes
found around each pixel:

`score[tc] = sum over fc of influence[fc] * T[fc, tc] * (1 - resistance[fc])`

`influence[fc]` is the kernel-weighted share of neighbours in class fc (each kernel is
normalised by its sum, and its centre weight is zero). Each neighbouring class pushes the
pixel towards the classes it tends to become: a forest pixel with sand upwind receives
a sand score through the sand row of T, while forest surrounded by forest keeps a high
forest score. Locked classes keep their state; a pixel with no evidence keeps its class.

Two consequences to keep in mind. The Markov matrix sets the direction of change but not
its quantity, so simulated areas are not forced to match `T`. And a class with high
persistence also pushes its neighbours towards itself, which smooths isolated pixels
(a majority-filter effect) and lets unlocked neighbours of agriculture become agriculture.

`rule="own_row"` is kept for comparison: each pixel uses only its own class row,
`(1 - R[i]) * T[i,j] * support[j]` for a change against `T[i,i]` for persistence. Because
support is at most 1 and `T[i,j] <= 1 - T[i,i]`, a class with persistence above about
0.5 can never change under argmax, so with real land-cover matrices this rule produces
almost frozen maps.

`allocation="argmax"` selects the largest score deterministically. Optional `"sample"`
normalises the scores and samples using a recorded seed. Sampling is an alternative
scenario mechanism, not calibrated uncertainty. Compare multiple seeds separately.

## Direction

Kernels represent where influence spreads from a source cell. With north-up rasters,
row +1 is south and column +1 is east. The implementation uses SciPy convolution:
placing a positive weight southeast of the centre spreads a single source southeast.
Tests check this orientation explicitly; changing convolution to correlation would
reverse an asymmetric stencil.

The sand stencil favours east/southeast, with a smaller south contribution. Agriculture
favours north; other classes use symmetric eight-neighbour support. The weights are
scenario assumptions derived from the stated directional intention, not fitted wind
transport parameters. Grid north is used; true-north/grid convergence is not corrected.
Monthly climate summaries do not automatically recalibrate these kernels.

## Ghost and domain

Outside/NoData (-1) never becomes land. Unknown eligible cells must be explicit 8 and
inside the valid raster/AOI mask. Their only change candidate is sand: with the default
rule a Ghost cell becomes sand when sand wins the neighbourhood vote, otherwise it stays
Ghost. Without local sand support it stays Ghost.

The report describes Ghost as including outside-area NoData. Separating these concepts
changes the simulation domain and is necessary to avoid making claims about missing
coverage. If an expansion zone outside an earlier mapped boundary is substantively
intended, delineate and justify its eligibility explicitly upstream; do not infer it
from missing-value codes. Compare the effect of that domain decision separately.

## Resistance and locks

Default resistance by canonical code:

`[0.20, 0.25, 0.50, 0.25, 0.50, 0.10, 1.00, 1.00, 0.20]`

The sparse-forest value follows the report's table (0.25); a notebook draft used 0.20.
Rocky-beach resistance 0.50 comes from the notebook because the report's table does
not completely specify that class. Agriculture, water and wet sand are locked by default.
All values remain configurable and must be treated as assumptions, not measurements.

## Hindcast evaluation

The default 2025 hindcast estimates T only from 2005→2010, 2010→2015 and 2015→2020,
then predicts from 2020. The 2025 classification is a comparison reference, not an
independent field truth. Any upstream classification error propagates to this test.
The code verifies that changing 2025 labels cannot change the hindcast or fitted T.

Overall accuracy is accompanied by per-class precision/recall/F1, the unchanged-2020
persistence baseline, and Figure of Merit (FoM):

`correct changes / (correct changes + missed changes + false changes + wrong destinations)`.

Reference Ghost is excluded. Predicted Ghost at a known reference pixel is an error.
Change metrics require known baseline classes. FoM is undefined if neither map changes;
it is not assigned a misleading perfect value. Do not choose rules repeatedly against
2025 and still call its score an untouched test. This retrospective revision is not a
new independent validation of the engineering report.

## Areas and landscape metrics

Areas use the affine pixel area in square metres, converted to hectares by /10,000.
Tables include per-date available coverage and a common historical footprint. Metrics
use the fixed footprint of cells known in every historical map. Missing-data changes
must not be mistaken for ecological dynamics. Ghost coverage is reported separately.

Forest combines classes 1, 2 and 3 before patch labelling. Connectivity is explicit (4
by default, optionally 8). Patch density is patches per 100 ha; largest-patch index is
percent of the known landscape; mean patch area is hectares. Edge density counts shared
edges to other known classes and excludes domain/NoData/Ghost boundaries, in metres/ha.
Shannon diversity uses the eight known class proportions and natural logarithms.

These are defined raster metrics, not automatic replicas of every FRAGSTATS/PyLandStats
quantity. Cohesion and proximity were requested under unsupported/uncertain column names
in the notebook and are not silently substituted here. Add them only with a chosen,
documented definition and independent numerical checks.

## Front measurements

Mean velocity follows the report: `swept_area / (elapsed_years * median_front_length)`.
The swept polygon and median line must be reviewed inputs in a metre CRS. Smoothing a
sand polygon for display must not change the geometry used for measurement.

Maximum displacement uses sampled transects in a reviewed corridor, with an explicitly
supplied movement bearing clockwise from north. All multipart front components are
sampled. Distances are signed, so retreat is negative. Missing intersections are missing,
not stable zero. Multiple intersections are counted and correspondence is selectable:
nearest by default, or farthest forward to inspect a maximum-envelope interpretation.
The result is a sampling-dependent maximum estimate, not an exact continuous optimum.
Increase sample density and check sensitivity; 30 m input maps do not support centimetre
claims simply because a geometric calculation returns decimal values.

Distinct per-date polygon row numbers are not identities. Inputs instead use explicit
site/date keys. Area differences and front correspondence require spatially meaningful
zones and reviewed lines; sorting polygons west-to-east does not establish either.

## Participatory planning and associations

Priority is the unweighted sum of participant-supplied binary criteria for each stable
zone ID, following the report. No criteria values, zone boundaries or causal explanations
are generated automatically. Observed and scenario-derived interval associations are
kept separate. Pearson r is descriptive only; no p-values are produced for the few,
dependent intervals. Derived simulation correlations are not independent validation.

## Technical references consulted

- https://docs.scipy.org/doc/scipy/reference/generated/scipy.ndimage.convolve.html
- https://rasterio.readthedocs.io/en/stable/topics/masks.html
- https://rasterio.readthedocs.io/en/stable/topics/features.html

The repository implements the stated report-guided scenario choices; it does not claim
that these software references validate the ecological assumptions.
