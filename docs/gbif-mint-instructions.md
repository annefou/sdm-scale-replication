# How to mint the two GBIF download DOIs for this replication

The H&J 2007 scale-replication uses **two** GBIF occurrence downloads
for Iberian birds — one modern (post-2000) as the atlas-equivalent
data, one historical (pre-2000) as the range-map-equivalent data.

`notebooks/01_data_download.py` will run end-to-end in three modes:

1. **Pre-minted keys hardcoded** — recommended. Mint once via the GBIF
   web UI (instructions below), paste the keys + DOIs into
   `01_data_download.py`, then the notebook fetches the zips by URL.
   No GBIF credentials needed at execution time. This is the CI mode.

2. **API-mint via env vars** — fall-through. If the hardcoded keys
   are still `TODO_MINT_*` AND the env vars `GBIF_USER`, `GBIF_PWD`,
   `GBIF_EMAIL` are set, the notebook mints fresh downloads via the
   GBIF API and polls until they complete.

3. **Synthetic demo fallback** — final fallback. If neither of the
   above succeeds, the notebook generates a deterministic synthetic
   dataset and flags every downstream artefact as `synthetic=True`.
   The pipeline runs end-to-end but the result is a structural smoke
   test, not a real replication.

## How to mint via the GBIF web UI

1. Sign in to https://www.gbif.org/.

2. **Modern dataset (post-2000)** — open this pre-filtered search URL:

   ```
   https://www.gbif.org/occurrence/search?taxon_key=212&country=ES&country=PT&country=AD&country=GI&has_coordinate=true&has_geospatial_issue=false&basis_of_record=HUMAN_OBSERVATION&basis_of_record=PRESERVED_SPECIMEN&basis_of_record=MACHINE_OBSERVATION&occurrence_year=2000,2030
   ```

   Click **Download -> Simple (SIMPLE_CSV)**, wait for the DOI to
   mint (~5-15 min), then copy the download key and DOI into the
   `GBIF_MODERN_DL_KEY` / `GBIF_MODERN_DL_DOI` variables near the top
   of `notebooks/01_data_download.py`.

3. **Historical dataset (pre-2000)** — open this pre-filtered URL:

   ```
   https://www.gbif.org/occurrence/search?taxon_key=212&country=ES&country=PT&country=AD&country=GI&has_coordinate=true&has_geospatial_issue=false&basis_of_record=HUMAN_OBSERVATION&basis_of_record=PRESERVED_SPECIMEN&basis_of_record=MACHINE_OBSERVATION&occurrence_year=1900,1999
   ```

   Same mint flow. Paste into `GBIF_HISTORICAL_DL_KEY` /
   `GBIF_HISTORICAL_DL_DOI`.

4. Commit the updated `notebooks/01_data_download.py`. CI will pick up
   the new keys on its next run.

## Predicate verification

The pre-filtered URLs apply these predicates (mirrored in
`01_data_download.py` for the source registry):

- `taxonKey = 212` — class Aves (ACCEPTED). Verify at
  https://api.gbif.org/v1/species/match?name=Aves&rank=class.
- `country IN (ES, PT, AD, GI)` — Spain, Portugal, Andorra, Gibraltar.
- `hasCoordinate = TRUE`, `hasGeospatialIssue = FALSE`.
- `basisOfRecord IN (HUMAN_OBSERVATION, PRESERVED_SPECIMEN, MACHINE_OBSERVATION)`.
- `year >= 2000` (modern) or `year <= 1999` (historical).

These predicates also live in `01_data_download.py` for downstream
audit (source registry JSON).

## Reproducibility note

Per DOMAIN.md "GBIF download DOIs are mandatory", **mint a fresh DOI
each time you re-run this replication on updated GBIF data** — do not
reuse a DOI minted on a different date, because the underlying GBIF
data changes daily and reuse falsifies the lineage.
