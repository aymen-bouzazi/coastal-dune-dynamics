# Report and notebook alignment

Basis: the project report (printed pp. 28–34) and the original analysis notebook,
both kept private. The table lists how each part of the original method is handled
in this version.

| Component | Report / notebook intention | Revised implementation |
|---|---|---|
| Historical LULC | Five dates, 2005–2025 | User-supplied classified maps with fixed grid/schema checks |
| Upstream classification | Landsat bands/indices and Random Forest | Done upstream; not part of this repository |
| Rasterisation | Common 30 m UTM maps | A common template, explicit class field and CRS; pixel size read from metadata |
| Transitions | Adjacent five-year pairs and integrated 2005–2025 changes | Both descriptive tables; only five-year intervals fit the update matrix |
| Average matrix | Mean period probabilities | Arithmetic mean by supported source rows; optional pooled-count alternative is named separately |
| CA source class | Neighbour classes fc push the pixel towards tc | Same formula, summed over neighbour classes; own-row rule kept as an option |
| Neighbour condition | Target present in the local neighbourhood | Per-cell target support; global `np.any` is removed |
| Resistance | Class stability through factors in local scores | (1 − R[fc]) weights each neighbour class's push, as in the report |
| Sparse-forest resistance | Report table 0.25; one notebook draft 0.20 | Default 0.25, configurable |
| Rocky-beach resistance | Incomplete report table; notebook uses 0.50 | Explicit notebook-based default 0.50, flagged as an assumption |
| Directionality | Sand ESE/SE, agriculture north | Tested spread stencils and explicit north-up grid convention |
| Agriculture | Report explicitly locks it | Locked by default, despite broader wording about sand colonisation |
| Water/wet sand | Static | Locked by default |
| Ghost | May only become sand near existing sand | Explicit valid-domain class 8 with sand-only change rule |
| Outside-area NoData | Sometimes conflated with Ghost | Always outside (-1); eligible domain must be justified explicitly |
| Future dynamic T | Rolling matrix updates | Implemented, with predicted-map feedback labelled in an audit; fixed observed-only alternative available |
| 2025 validation | Compare CA output against RF-derived 2025 map | Earlier years only for fitting; persistence and change metrics alongside accuracy |
| Forecast editing | Hard-coded cell/coordinate overrides | Optional input-driven corrections with expected-class checks and separate outputs; no hard-coded site cells |
| Areas | Counts and hectares | Affine-derived hectares and explicit coverage domains |
| Front mean velocity | S/(tL), reviewed swept surface and median line | Exact equation with metre-CRS geometry from reviewed digitisation |
| Maximum front advance | Measurement in a fragmentation corridor | Explicit bearing and corridor, all line components, signed/missing/ambiguous samples retained |
| Cross-year polygon identity | Notebook joins independent row-number shape IDs | No such join; stable site/date keys and reviewed geometry |
| Display smoothing | Smooth polygons for presentation | Measurement export stays unsmoothed; display changes are external copies |
| Landscape metrics | Forest/sand patterns and temporal change | A defined, tested subset; no unsupported metric-name lookups |
| Climate | Monthly NASA POWER summaries | User-supplied monthly table, explicit precipitation units and missingness checks |
| Associations | Dune advance vs fragmentation | Descriptive differences/correlations, observed and scenario intervals separated |
| Participatory planning | Locally selected binary criteria, summed by zone | Supplied criteria only, joined by stable zone ID; no automated human judgements |

## Interpretation limits

The local rule differs from some original notebook drafts, so their scores, forecast
areas and manual edits do not carry over. Results need to be re-run on the actual maps
and compared across named scenarios.

The report's 2025 reference is itself a classification. Map agreement is not the same
as independent ground validation. Static-class policies constrain the possible answers;
changing those policies is a scientific scenario decision, not a code cleanup.

The raster forecast does not model wind-driven sediment transport, dune topography,
sand mass balance or storm forcing. The time step, stencils and resistances are
coarse spatial scenario rules. The management contribution also includes field and
participatory work that cannot be recreated by generating Python code.
