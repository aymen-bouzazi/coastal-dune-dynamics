# Public source, private research inputs

No report PDF, original notebook, field/map data, geometry corrections, real study
coordinates, consultation scores, fitted outputs, source-data hashes or private local
paths are distributed with this repository. Tests generate invented inputs in temporary
folders. The example configuration names generic local paths and contains assumptions,
not measurements. There are no cloud credentials or study download links.

Inputs belong in `private/` or outside the repository. Generated tables, maps, GeoPackages,
plots, audits and calibration results belong in ignored output folders. Their contents
and provenance can contain sensitive measurements or paths. Do not attach the original
working notebook, report or output directory to a GitHub release.

Before publishing, use a clean new repository directory and inspect staged bytes:

```bash
git init -b main
git add .
python tools/check_public_files.py
git diff --cached --stat
git diff --cached
```

Then commit and push.

The checker rejects common research-data formats, private directories/configuration,
field-derived fixtures, binary payloads and some credential patterns. Within a Git repo
it inspects the index, including forced additions, rather than assuming `.gitignore`
protects the data. Outside Git it checks the whole folder. It never prints file contents.
It is a guardrail, not a proof that every arbitrary source string is safe to publish.
Review the staged diff and notebooks/images manually if adding them later.

Ignoring a file does not remove old copies already committed. Do not publish the history
of an older working repository that contained data.
See https://docs.github.com/en/get-started/git-basics/ignoring-files .

CI runs the source guard, lint and synthetic tests. It has no access to private study
inputs, does not upload artifacts and does not publish results. 
