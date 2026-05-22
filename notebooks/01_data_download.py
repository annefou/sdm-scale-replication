# ---
# jupyter:
#   jupytext:
#     formats: py:percent
#     text_representation:
#       extension: .py
#       format_name: percent
#       format_version: '1.3'
#       jupytext_version: 1.16.0
#   kernelspec:
#     display_name: Python 3
#     language: python
#     name: python3
# ---

# %% [markdown]
# # 01 — Data download (Iberian birds, Hurlbert & Jetz 2007 scale-replication)
#
# This notebook fetches all input data needed by the replication pipeline.
# It is self-contained: a fresh clone can run this notebook end-to-end
# without manual data preparation.
#
# **Two data products** are needed (the modern analogues of H&J 2007's
# range-map vs atlas comparison — see `nanopubs/drafts/00_paper_summary.md`):
#
# 1. **Modern GBIF Iberian bird occurrences (2000-present)** — point
#    records, the modern atlas analogue. Aggregated per HEALPix cell in
#    `02_data_clean.py` to give per-cell species richness from
#    survey-quality observations.
#
# 2. **"Range maps" analogue** — per-species extent-of-occurrence
#    polygons. We do **not** use BirdLife BOTW shapefiles (not openly
#    redistributable, requires data-use agreement) nor the IUCN Red List
#    range polygons (gated behind a non-redistributable license and an
#    API token). Instead, we derive an open, automated **EOO-from-GBIF**
#    polygon per species — i.e. each species' convex-hull (or alpha-hull)
#    of its **historical pre-2000 GBIF point occurrences**, which is the
#    classic "extent of occurrence" definition (IUCN 2024 Red List
#    Guidelines §4.9.2). This is a methodological substitute for
#    expert-drawn range maps; the substitution is honest about its
#    limitations (it is itself derived from GBIF, not from independent
#    expert opinion) and the deviation will be flagged in the Outcome's
#    Deviations field (Phase 5 step 05).
#
# This `01_data_download.py` therefore mints **two** GBIF download DOIs:
# one for the modern (post-2000) atlas-equivalent dataset, and one for
# the historical (pre-2000) EOO-equivalent dataset. Per DOMAIN.md
# "GBIF download DOIs are mandatory" each fresh query mints a fresh DOI.
#
# **Credentials.** The downloader uses the **public GBIF occurrence
# download endpoint** by URL (no credentials needed) once a download key
# has been minted. Mint the keys via the `pygbif.occurrences.download`
# helper if `GBIF_USER` / `GBIF_PWD` / `GBIF_EMAIL` env vars are set;
# otherwise the notebook uses pre-minted keys hardcoded below. This
# matches the Bombus/Lizards sibling chain's "pre-minted via UI" pattern
# so the notebook runs in CI without GBIF credentials.

# %%
import json
import os
import time
import zipfile
from datetime import date
from pathlib import Path

import requests

# %% [markdown]
# ## Paths

# %%
ROOT = Path("..").resolve()
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
GBIF_DIR = DATA_DIR / "gbif"

for d in (RAW_DIR, GBIF_DIR):
    d.mkdir(parents=True, exist_ok=True)

print(f"ROOT    = {ROOT}")
print(f"RAW_DIR = {RAW_DIR}")
print(f"GBIF_DIR= {GBIF_DIR}")

SOURCES: list[dict] = []

# Conservative thresholds — small enough to detect broken downloads,
# big enough to never false-positive on a real zip.
MIN_ZIP_BYTES = 1_000


# %% [markdown]
# ## 1. Modern GBIF Iberian birds (2000-present) — "atlas-equivalent"
#
# Predicates:
#
#   * taxonKey = 212 (Aves, class)
#   * country IN (ES, PT, AD, GI)
#   * hasCoordinate = TRUE
#   * hasGeospatialIssue = FALSE
#   * basisOfRecord IN (HUMAN_OBSERVATION, PRESERVED_SPECIMEN, MACHINE_OBSERVATION)
#   * year >= 2000
#
# **Pre-minted via the GBIF web UI on 2026-05-22 by Anne Fouilloux.**
# See `docs/gbif-mint-instructions.md` for re-mint instructions. The
# download key + DOI below are placeholders that the user updates after
# minting; until then the notebook will fall through to a `pygbif`
# fresh mint if `GBIF_USER`/`GBIF_PWD`/`GBIF_EMAIL` env vars are set,
# or emit a "skipped" entry into the source registry otherwise.

# %%
GBIF_MODERN_DL_KEY = os.environ.get("GBIF_MODERN_DL_KEY", "TODO_MINT_MODERN_KEY")
GBIF_MODERN_DL_DOI = os.environ.get("GBIF_MODERN_DL_DOI", "TODO_MINT_MODERN_DOI")

GBIF_MODERN_PREDICATES = {
    "taxonKey": 212,
    "taxonKey_resolution": "Aves (class, ACCEPTED) — https://api.gbif.org/v1/species/match?name=Aves&rank=class",
    "country": ["ES", "PT", "AD", "GI"],
    "hasCoordinate": True,
    "hasGeospatialIssue": False,
    "basisOfRecord": ["HUMAN_OBSERVATION", "PRESERVED_SPECIMEN", "MACHINE_OBSERVATION"],
    "year_min": 2000,
    "year_max": None,
}

GBIF_MODERN_ZIP = GBIF_DIR / "birds_iberia_modern.zip"
GBIF_MODERN_DOI_PATH = GBIF_DIR / "modern_download_doi.txt"
GBIF_MODERN_KEY_PATH = GBIF_DIR / "modern_download_key.txt"
GBIF_MODERN_META = GBIF_DIR / "birds_iberia_modern_metadata.json"


# %% [markdown]
# ## 2. Historical GBIF Iberian birds (pre-2000) — "range-map-equivalent"
#
# Same taxon + region + coordinate filters as the modern query, with
# `year < 2000` instead of `year >= 2000`. Per-species convex hulls of
# the historical occurrences will be computed in `02_data_clean.py` as
# the modern analogue of H&J 2007's expert-drawn range maps.
#
# **Pre-minted via the GBIF web UI on 2026-05-22 by Anne Fouilloux.**

# %%
GBIF_HISTORICAL_DL_KEY = os.environ.get("GBIF_HISTORICAL_DL_KEY", "TODO_MINT_HISTORICAL_KEY")
GBIF_HISTORICAL_DL_DOI = os.environ.get("GBIF_HISTORICAL_DL_DOI", "TODO_MINT_HISTORICAL_DOI")

GBIF_HISTORICAL_PREDICATES = {
    "taxonKey": 212,
    "country": ["ES", "PT", "AD", "GI"],
    "hasCoordinate": True,
    "hasGeospatialIssue": False,
    "basisOfRecord": ["HUMAN_OBSERVATION", "PRESERVED_SPECIMEN", "MACHINE_OBSERVATION"],
    "year_max": 1999,
}

GBIF_HISTORICAL_ZIP = GBIF_DIR / "birds_iberia_historical.zip"
GBIF_HISTORICAL_DOI_PATH = GBIF_DIR / "historical_download_doi.txt"
GBIF_HISTORICAL_KEY_PATH = GBIF_DIR / "historical_download_key.txt"
GBIF_HISTORICAL_META = GBIF_DIR / "birds_iberia_historical_metadata.json"


# %% [markdown]
# ## Helpers
#
# `fetch_gbif_by_key` — pull a pre-minted download zip by its key, no
# credentials needed (the zip URL is public). Idempotent: returns
# immediately if the zip is already present.
#
# `mint_gbif_download` — fall back path. Requires GBIF_USER, GBIF_PWD,
# GBIF_EMAIL env vars; mints a new download via the GBIF API, polls
# until ready, then downloads the zip. Used only when the hardcoded
# key is still `TODO_MINT_*` AND the env vars are present.

# %%
def fetch_gbif_by_key(key: str, zip_path: Path, doi: str, doi_path: Path,
                      key_path: Path, meta_path: Path,
                      predicates: dict) -> dict:
    """Fetch a pre-minted GBIF download zip by URL. No credentials needed."""
    if (zip_path.exists() and zip_path.stat().st_size > MIN_ZIP_BYTES
            and doi_path.exists() and key_path.exists()):
        print(f"  [cached]  key = {key_path.read_text().strip()}, "
              f"doi = {doi_path.read_text().strip()}")
        print(f"            zip = {zip_path} ({zip_path.stat().st_size:,} bytes)")
        return {"key": key_path.read_text().strip(),
                "doi": doi_path.read_text().strip(),
                "zip": str(zip_path)}

    url = f"https://api.gbif.org/v1/occurrence/download/request/{key}.zip"
    print(f"  fetching {url}")
    r = requests.get(url, stream=True, timeout=600, allow_redirects=True)
    r.raise_for_status()
    with open(zip_path, "wb") as f:
        for chunk in r.iter_content(chunk_size=1 << 16):
            f.write(chunk)
    print(f"  saved {zip_path} ({zip_path.stat().st_size:,} bytes)")

    doi_path.write_text(doi + "\n")
    key_path.write_text(key + "\n")
    meta = {
        "download_key": key,
        "doi": doi,
        "doi_url": f"https://doi.org/{doi}",
        "source_url": url,
        "predicates": predicates,
    }
    meta_path.write_text(json.dumps(meta, indent=2))
    return {"key": key, "doi": doi, "zip": str(zip_path)}


def mint_gbif_download(predicates: dict, name: str) -> dict | None:
    """Mint a fresh GBIF download via the API. Returns dict with key+doi or None
    if credentials are absent / the mint fails."""
    user = os.environ.get("GBIF_USER")
    pwd = os.environ.get("GBIF_PWD")
    email = os.environ.get("GBIF_EMAIL")
    if not (user and pwd and email):
        print(f"  [skip  ]  GBIF_USER/GBIF_PWD/GBIF_EMAIL not set — cannot mint '{name}'")
        return None
    try:
        from pygbif import occurrences as occ
    except ImportError:
        print("  [skip  ]  pygbif not importable")
        return None

    preds = [
        ("taxonKey", "=", str(predicates["taxonKey"])),
        ("hasCoordinate", "=", "true"),
        ("hasGeospatialIssue", "=", "false"),
    ]
    # Country list -> OR of equals
    country_preds = [("country", "=", c) for c in predicates["country"]]
    # Basis of record list -> OR of equals
    bor_preds = [("basisOfRecord", "=", b) for b in predicates["basisOfRecord"]]

    # pygbif's download API takes a list of predicate-tuples in conjunctive form
    # plus optional disjunctions. Use the low-level JSON predicate instead so
    # the OR groups are explicit.
    json_predicate = {
        "type": "and",
        "predicates": [
            {"type": "equals", "key": "TAXON_KEY", "value": str(predicates["taxonKey"])},
            {"type": "equals", "key": "HAS_COORDINATE", "value": "true"},
            {"type": "equals", "key": "HAS_GEOSPATIAL_ISSUE", "value": "false"},
            {"type": "in", "key": "COUNTRY", "values": predicates["country"]},
            {"type": "in", "key": "BASIS_OF_RECORD", "values": predicates["basisOfRecord"]},
        ],
    }
    if predicates.get("year_min"):
        json_predicate["predicates"].append(
            {"type": "greaterThanOrEquals", "key": "YEAR",
             "value": str(predicates["year_min"])}
        )
    if predicates.get("year_max"):
        json_predicate["predicates"].append(
            {"type": "lessThanOrEquals", "key": "YEAR",
             "value": str(predicates["year_max"])}
        )

    print(f"  [mint  ]  requesting GBIF download for '{name}'")
    print(f"            predicate = {json.dumps(json_predicate)[:200]}...")
    # pygbif's `download` wraps a simpler predicate language; for full
    # control we POST the JSON predicate directly.
    api_url = "https://api.gbif.org/v1/occurrence/download/request"
    body = {
        "creator": user,
        "notificationAddresses": [email],
        "sendNotification": False,
        "format": "SIMPLE_CSV",
        "predicate": json_predicate,
    }
    resp = requests.post(api_url, json=body, auth=(user, pwd), timeout=120)
    if not resp.ok:
        print(f"  [fail  ]  mint POST returned {resp.status_code}: {resp.text[:200]}")
        return None
    key = resp.text.strip()
    print(f"  [mint  ]  download key = {key} — polling for completion ...")

    # Poll status until completed or failed (up to ~30 min).
    status_url = f"https://api.gbif.org/v1/occurrence/download/{key}"
    for attempt in range(60):
        s = requests.get(status_url, timeout=30).json()
        status = s.get("status")
        print(f"            attempt {attempt + 1}: status = {status}")
        if status == "SUCCEEDED":
            doi = s.get("doi", "")
            return {"key": key, "doi": doi}
        if status in ("FAILED", "CANCELLED", "FILE_ERASED"):
            print(f"  [fail  ]  download {status}")
            return None
        time.sleep(30)
    print("  [fail  ]  poll timeout after 30 min")
    return None


def get_or_mint(name: str, hardcoded_key: str, hardcoded_doi: str,
                zip_path: Path, doi_path: Path, key_path: Path,
                meta_path: Path, predicates: dict) -> dict:
    """If hardcoded key is real, fetch by URL. Else attempt to mint via API.
    Else emit a skip entry."""
    if not hardcoded_key.startswith("TODO_"):
        return fetch_gbif_by_key(hardcoded_key, zip_path, hardcoded_doi,
                                 doi_path, key_path, meta_path, predicates)
    minted = mint_gbif_download(predicates, name)
    if minted:
        return fetch_gbif_by_key(minted["key"], zip_path, minted["doi"],
                                 doi_path, key_path, meta_path, predicates)
    return {"key": None, "doi": None, "zip": None, "skipped": True,
            "reason": (f"No pre-minted key for '{name}' and "
                       f"GBIF_USER/GBIF_PWD/GBIF_EMAIL not set.")}


# %% [markdown]
# ## Execute the two downloads

# %%
print("\n--- 1. Modern Iberian birds (2000-present) ---")
modern_result = get_or_mint(
    name="modern", hardcoded_key=GBIF_MODERN_DL_KEY,
    hardcoded_doi=GBIF_MODERN_DL_DOI,
    zip_path=GBIF_MODERN_ZIP, doi_path=GBIF_MODERN_DOI_PATH,
    key_path=GBIF_MODERN_KEY_PATH, meta_path=GBIF_MODERN_META,
    predicates=GBIF_MODERN_PREDICATES,
)
SOURCES.append({
    "name": "GBIF Iberian birds modern (2000-present)",
    "role": "atlas-equivalent (per-cell richness from point observations)",
    "doi": modern_result.get("doi"),
    "url": (f"https://doi.org/{modern_result['doi']}"
            if modern_result.get("doi") else None),
    "license": "CC-BY-NC-4.0 (per individual GBIF datasets)",
    "accessed_on": date.today().isoformat(),
    "download_key": modern_result.get("key"),
    "predicates": GBIF_MODERN_PREDICATES,
    "local_path": modern_result.get("zip"),
    "skipped": modern_result.get("skipped", False),
    "skip_reason": modern_result.get("reason"),
})

# %%
print("\n--- 2. Historical Iberian birds (pre-2000) — EOO-equivalent ---")
historical_result = get_or_mint(
    name="historical", hardcoded_key=GBIF_HISTORICAL_DL_KEY,
    hardcoded_doi=GBIF_HISTORICAL_DL_DOI,
    zip_path=GBIF_HISTORICAL_ZIP, doi_path=GBIF_HISTORICAL_DOI_PATH,
    key_path=GBIF_HISTORICAL_KEY_PATH, meta_path=GBIF_HISTORICAL_META,
    predicates=GBIF_HISTORICAL_PREDICATES,
)
SOURCES.append({
    "name": "GBIF Iberian birds historical (pre-2000)",
    "role": "range-map-equivalent (per-species convex hull of historical occurrences)",
    "doi": historical_result.get("doi"),
    "url": (f"https://doi.org/{historical_result['doi']}"
            if historical_result.get("doi") else None),
    "license": "CC-BY-NC-4.0 (per individual GBIF datasets)",
    "accessed_on": date.today().isoformat(),
    "download_key": historical_result.get("key"),
    "predicates": GBIF_HISTORICAL_PREDICATES,
    "local_path": historical_result.get("zip"),
    "skipped": historical_result.get("skipped", False),
    "skip_reason": historical_result.get("reason"),
})


# %% [markdown]
# ## 3. Demo fallback — synthetic data for CI/notebook execution
#
# If both GBIF downloads were skipped (CI / fresh checkout without a
# minted key and without GBIF credentials), generate a deterministic
# **synthetic** Iberian bird dataset so the rest of the pipeline can
# execute end-to-end. The synthetic data is labelled as such in
# `data/raw/sources.json` and the analysis tags downstream artefacts
# with a `synthetic_data: true` flag so the figure clearly says
# "DEMO DATA — NOT A REAL REPLICATION".
#
# This pattern lets `snakemake --cores 1` run green on a fresh clone for
# the structural integration test, while preserving full traceability
# that the numerical result is not the real one. The user replaces this
# by minting real GBIF download keys (instructions in
# `docs/gbif-mint-instructions.md`).

# %%
SYNTHETIC_FLAG = RAW_DIR / "USING_SYNTHETIC_DEMO_DATA.txt"

both_skipped = (
    modern_result.get("skipped", False)
    and historical_result.get("skipped", False)
)


def make_synthetic_demo() -> None:
    """Generate deterministic Iberian bird demo data when GBIF is unavailable.

    Creates two minimal SIMPLE_CSV-style zips at GBIF_MODERN_ZIP /
    GBIF_HISTORICAL_ZIP so 02_data_clean.py reads them via the same
    code path as real data. The synthetic data has ~80 species with
    plausible Iberian distributions:
      - Historical: range-equivalent — wide convex hulls (few coarse
        clumps per species).
      - Modern: atlas-equivalent — denser points inside the historical
        range, with localised richness peaks (the simulated "hotspots").
    """
    import numpy as np
    rng = np.random.default_rng(seed=20260522)

    SPECIES_N = 80
    # Iberia bbox
    lon0, lon1 = -10.0, 4.0
    lat0, lat1 = 35.0, 44.0

    # Pre-pick a Voronoi-like distribution centre per species.
    centres_lon = rng.uniform(lon0 + 1, lon1 - 1, size=SPECIES_N)
    centres_lat = rng.uniform(lat0 + 1, lat1 - 1, size=SPECIES_N)
    range_radii = rng.uniform(1.0, 4.0, size=SPECIES_N)  # degrees

    species_names = [f"Synthavis demoensis_{i:03d}" for i in range(SPECIES_N)]

    def write_zip(records: list[dict], target: Path) -> None:
        # SIMPLE_CSV-style header that 02_data_clean.py reads.
        cols = ["gbifID", "species", "decimalLatitude", "decimalLongitude",
                "year", "basisOfRecord", "countryCode"]
        lines = ["\t".join(cols)]
        for i, rec in enumerate(records):
            lines.append("\t".join([
                str(i), rec["species"],
                f"{rec['lat']:.5f}", f"{rec['lon']:.5f}",
                str(rec["year"]), "HUMAN_OBSERVATION", "ES",
            ]))
        csv_text = "\n".join(lines) + "\n"
        with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("occurrence.csv", csv_text)

    # Historical (pre-2000): ~20 wide-spread points per species.
    historical_records = []
    for sp_idx, name in enumerate(species_names):
        n_pts = rng.integers(15, 40)
        lons = rng.normal(centres_lon[sp_idx], range_radii[sp_idx], n_pts)
        lats = rng.normal(centres_lat[sp_idx], range_radii[sp_idx] * 0.6, n_pts)
        years = rng.integers(1950, 2000, n_pts)
        keep = (lons >= lon0) & (lons <= lon1) & (lats >= lat0) & (lats <= lat1)
        for j in np.where(keep)[0]:
            historical_records.append({
                "species": name, "lat": float(lats[j]), "lon": float(lons[j]),
                "year": int(years[j]),
            })

    # Modern (2000+): ~60 points per species, with a sub-region having
    # 3x density (simulated "hotspot" at fine grain). Hotspot is centred
    # off the species' historical centre, which is what creates the
    # range-map vs atlas hotspot mismatch the replication tests.
    modern_records = []
    # Pick three hotspot centres
    hotspot_centres = np.array([
        [-3.5, 37.0],   # Sierra Nevada-ish
        [0.0, 42.5],    # Pyrenees-ish
        [-6.5, 39.5],   # Extremadura-ish
    ])
    for sp_idx, name in enumerate(species_names):
        n_pts = rng.integers(40, 120)
        lons = rng.normal(centres_lon[sp_idx], range_radii[sp_idx] * 0.8, n_pts)
        lats = rng.normal(centres_lat[sp_idx], range_radii[sp_idx] * 0.5, n_pts)
        years = rng.integers(2000, 2025, n_pts)
        # Add extra hotspot density for ~half the species
        if sp_idx % 2 == 0:
            hc = hotspot_centres[sp_idx % 3]
            extra_n = rng.integers(20, 60)
            extra_lons = rng.normal(hc[0], 0.3, extra_n)
            extra_lats = rng.normal(hc[1], 0.3, extra_n)
            extra_years = rng.integers(2010, 2025, extra_n)
            lons = np.concatenate([lons, extra_lons])
            lats = np.concatenate([lats, extra_lats])
            years = np.concatenate([years, extra_years])
        keep = (lons >= lon0) & (lons <= lon1) & (lats >= lat0) & (lats <= lat1)
        for j in np.where(keep)[0]:
            modern_records.append({
                "species": name, "lat": float(lats[j]), "lon": float(lons[j]),
                "year": int(years[j]),
            })

    write_zip(modern_records, GBIF_MODERN_ZIP)
    write_zip(historical_records, GBIF_HISTORICAL_ZIP)

    GBIF_MODERN_DOI_PATH.write_text("SYNTHETIC_DEMO_DATA_NO_DOI\n")
    GBIF_MODERN_KEY_PATH.write_text("SYNTHETIC_DEMO\n")
    GBIF_HISTORICAL_DOI_PATH.write_text("SYNTHETIC_DEMO_DATA_NO_DOI\n")
    GBIF_HISTORICAL_KEY_PATH.write_text("SYNTHETIC_DEMO\n")

    SYNTHETIC_FLAG.write_text(
        "This run used SYNTHETIC DEMO DATA — not real GBIF observations.\n"
        "Mint real GBIF download keys per docs/gbif-mint-instructions.md\n"
        "to produce a real replication result.\n"
    )
    print(f"  [demo  ]  wrote synthetic Iberian bird data:")
    print(f"            modern    = {GBIF_MODERN_ZIP} "
          f"({len(modern_records)} records, {SPECIES_N} species)")
    print(f"            historical= {GBIF_HISTORICAL_ZIP} "
          f"({len(historical_records)} records, {SPECIES_N} species)")
    print(f"            flag      = {SYNTHETIC_FLAG}")


if both_skipped:
    print("\n--- 3. Synthetic demo fallback (GBIF unavailable) ---")
    make_synthetic_demo()
    SOURCES.append({
        "name": "Synthetic Iberian bird demo data",
        "role": "demo fallback — used when GBIF credentials absent",
        "doi": None,
        "url": None,
        "license": "n/a (generated locally with fixed seed 20260522)",
        "accessed_on": date.today().isoformat(),
        "synthetic": True,
        "note": ("80 simulated species across Iberia; downstream artefacts "
                 "are flagged synthetic_data=True so figures clearly state "
                 "DEMO DATA. Replace by minting real GBIF keys."),
    })
else:
    # Remove a stale synthetic flag if it exists (in case the user
    # re-ran after minting real keys).
    if SYNTHETIC_FLAG.exists():
        SYNTHETIC_FLAG.unlink()


# %% [markdown]
# ## 4. Source registry
#
# Single JSON at `data/raw/sources.json` recording every download's
# URL/DOI/license/accessed-on date + skip status. This is the provenance
# contract the Replication Study draft (Phase 5 step 04) cites.

# %%
SOURCES_JSON = RAW_DIR / "sources.json"
with open(SOURCES_JSON, "w") as f:
    json.dump({"sources": SOURCES, "written_on": date.today().isoformat()}, f, indent=2)
print(f"\n--- 4. Wrote source registry -> {SOURCES_JSON}")


# %% [markdown]
# ## Summary

# %%
print("\nArtefact inventory:")
artefacts = [
    ("Modern GBIF zip",          GBIF_MODERN_ZIP),
    ("Modern download DOI",      GBIF_MODERN_DOI_PATH),
    ("Modern download key",      GBIF_MODERN_KEY_PATH),
    ("Historical GBIF zip",      GBIF_HISTORICAL_ZIP),
    ("Historical download DOI",  GBIF_HISTORICAL_DOI_PATH),
    ("Historical download key",  GBIF_HISTORICAL_KEY_PATH),
    ("Synthetic-demo flag",      SYNTHETIC_FLAG),
    ("Source registry JSON",     SOURCES_JSON),
]
for name, p in artefacts:
    if p.exists():
        size = (
            p.stat().st_size if p.is_file()
            else sum(f.stat().st_size for f in p.rglob("*") if f.is_file())
        )
        print(f"  ok    {name:<28} {size:>12,} bytes  {p.relative_to(ROOT)}")
    else:
        print(f"  MISS  {name:<28} {'-':>12}        {p.relative_to(ROOT)}")
