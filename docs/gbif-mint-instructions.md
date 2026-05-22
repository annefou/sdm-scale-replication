# How to mint the two GBIF download DOIs for this replication

The H&J 2007 scale-replication uses **two GBIF occurrence downloads in
parallel** as two separate basis-of-record (BoR) strategies:

| Strategy | Code | basisOfRecord values | DOI |
|---|---|---|---|
| Museum + sensors | `museum` | `PRESERVED_SPECIMEN`, `MACHINE_OBSERVATION` | `10.15468/dl.r8pcat` (download key `0008222-260519110011954`) — **minted 2026-05-22** |
| All observations (incl. citizen-science) | `allbor` | `HUMAN_OBSERVATION`, `PRESERVED_SPECIMEN`, `MACHINE_OBSERVATION` | **to be minted** |

**No year filter** is applied at the download stage. The year split into
modern (`year >= 2000`, atlas-equivalent) vs historical (`year < 2000`,
range-map-equivalent via per-species convex-hull EOO) happens in
`notebooks/02_data_clean.py`. One DOI per strategy therefore serves both
year windows for that strategy.

`notebooks/01_data_download.py` runs in three modes:

1. **Pre-minted keys hardcoded** — recommended. Mint via the GBIF web UI,
   paste the key + DOI into the notebook (or set the env vars below),
   then the notebook fetches the zips by URL. No GBIF credentials needed
   at execution time. This is the CI mode.

2. **API-mint via env vars** — fall-through. If the hardcoded keys are
   still `TODO_MINT_*` AND the env vars `GBIF_USER`, `GBIF_PWD`,
   `GBIF_EMAIL` are set, the notebook mints fresh downloads via the
   GBIF API and polls until complete.

3. **Per-strategy synthetic demo fallback** — final fallback. If a
   strategy's key is unminted AND env vars are absent, the notebook
   generates a deterministic synthetic dataset *for that strategy only*
   and flags every downstream artefact as `synthetic=true` for that
   strategy. The other strategy still uses real data.

## Override via env vars

To pass keys without editing the notebook (CI / one-off runs):

```bash
# Strategy A — museum + sensors (already-minted defaults)
export GBIF_MUSEUM_DL_KEY="0008222-260519110011954"
export GBIF_MUSEUM_DL_DOI="10.15468/dl.r8pcat"

# Strategy B — all observations (mint these, then export)
export GBIF_ALLBOR_DL_KEY="<download key from GBIF mint>"
export GBIF_ALLBOR_DL_DOI="<DOI returned by GBIF>"

pixi run snakemake --cores 1
```

## How to mint via the GBIF web UI

1. Sign in to https://www.gbif.org/.

2. **Strategy A — museum + sensors** (already minted). The minted
   filter URL is:

   ```
   https://www.gbif.org/occurrence/search?taxon_key=212&country=ES&country=PT&country=AD&country=GI&has_coordinate=true&has_geospatial_issue=false&basis_of_record=PRESERVED_SPECIMEN&basis_of_record=MACHINE_OBSERVATION
   ```

   (No year filter.) DOI: `10.15468/dl.r8pcat`. Download key:
   `0008222-260519110011954`.

3. **Strategy B — all observations (incl. citizen-science)** — to mint.
   Open this pre-filtered URL:

   ```
   https://www.gbif.org/occurrence/search?taxon_key=212&country=ES&country=PT&country=AD&country=GI&has_coordinate=true&has_geospatial_issue=false&basis_of_record=HUMAN_OBSERVATION&basis_of_record=PRESERVED_SPECIMEN&basis_of_record=MACHINE_OBSERVATION
   ```

   Click **Download -> Simple (SIMPLE_CSV)**, wait for the DOI to mint
   (~5-15 min for the smaller museum set; allbor is much larger and
   may take longer), then export `GBIF_ALLBOR_DL_KEY` and
   `GBIF_ALLBOR_DL_DOI` (or paste them into the notebook).

4. Commit the updated key/DOI defaults if you want CI to pick them up
   without env vars.

## Predicate verification

The URLs above apply these predicates (mirrored in
`01_data_download.py` for the source registry):

- `taxonKey = 212` — class Aves (ACCEPTED). Verify at
  https://api.gbif.org/v1/species/match?name=Aves&rank=class.
- `country IN (ES, PT, AD, GI)` — Spain, Portugal, Andorra, Gibraltar.
- `hasCoordinate = TRUE`, `hasGeospatialIssue = FALSE`.
- `basisOfRecord IN (...)` — per-strategy list (see table above).
- (No year filter — the split is done in `02_data_clean.py`.)

## Reproducibility note

Per DOMAIN.md "GBIF download DOIs are mandatory", **mint a fresh DOI
each time you re-run this replication on updated GBIF data** — do not
reuse a DOI minted on a different date, because the underlying GBIF
data changes daily and reuse falsifies the lineage.
