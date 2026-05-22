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
# ## Two-strategy basis-of-record (BoR) design
#
# We compare **two GBIF download strategies in parallel**, each minted as
# its own DOI with **no year filter** (the year split into modern/historical
# happens in `02_data_clean.py`):
#
# 1. **Strategy A — "museum + sensors"** (`museum`). BoR =
#    `PRESERVED_SPECIMEN + MACHINE_OBSERVATION`. Excludes
#    `HUMAN_OBSERVATION` deliberately, giving a cleaner museum/sensor
#    provenance — no citizen-science detection bias.
# 2. **Strategy B — "all observations incl. citizen-science"** (`allbor`).
#    BoR = `HUMAN_OBSERVATION + PRESERVED_SPECIMEN + MACHINE_OBSERVATION`.
#    Includes large citizen-science volumes (eBird via GBIF, Observation,
#    iNaturalist research-grade).
#
# Within each strategy, `02_data_clean.py` splits records by year:
#
# - `year >= 2000` -> **modern** frame (atlas-equivalent).
# - `year < 2000`  -> **historical** frame (range-map-equivalent via
#   per-species convex-hull EOO).
#
# So one DOI per strategy serves both year windows for that strategy. The
# replication's headline statistic (hotspot misidentification % vs Nside)
# is reported separately for each strategy in `results/headline.json`.
#
# **Credentials.** The downloader uses the **public GBIF occurrence
# download endpoint** by URL once a download key has been minted — no
# credentials needed at execution time. Mint via the GBIF UI (instructions
# in `docs/gbif-mint-instructions.md`) or via the `pygbif`-based
# `mint_gbif_download` helper below if `GBIF_USER` / `GBIF_PWD` /
# `GBIF_EMAIL` env vars are set.

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
# ## Strategy A — "museum + sensors" (`museum`)
#
# **DOI #1**: pre-minted via the GBIF web UI on 2026-05-22 by Anne Fouilloux.
#
# Predicates (matches GBIF's actual minted JSON predicate at key
# `0008222-260519110011954`):
#
#   * taxonKey = 212 (Aves, class)
#   * country IN (ES, PT, AD, GI)
#   * hasCoordinate = TRUE
#   * hasGeospatialIssue = FALSE
#   * basisOfRecord IN (PRESERVED_SPECIMEN, MACHINE_OBSERVATION)
#   * (no year filter — split into modern/historical in 02_data_clean.py)
#
# DOI / download key are read from env vars first (so CI / other users
# can override) and otherwise default to the minted values.

# %%
GBIF_MUSEUM_DL_KEY = os.environ.get(
    "GBIF_MUSEUM_DL_KEY", "0008222-260519110011954"
)
GBIF_MUSEUM_DL_DOI = os.environ.get(
    "GBIF_MUSEUM_DL_DOI", "10.15468/dl.r8pcat"
)

GBIF_MUSEUM_PREDICATES = {
    "taxonKey": 212,
    "taxonKey_resolution": "Aves (class, ACCEPTED) — https://api.gbif.org/v1/species/match?name=Aves&rank=class",
    "country": ["ES", "PT", "AD", "GI"],
    "hasCoordinate": True,
    "hasGeospatialIssue": False,
    "basisOfRecord": ["PRESERVED_SPECIMEN", "MACHINE_OBSERVATION"],
    # no year filter — year split happens in 02_data_clean.py
}

GBIF_MUSEUM_ZIP = GBIF_DIR / "birds_iberia_museum.zip"
GBIF_MUSEUM_DOI_PATH = GBIF_DIR / "museum_download_doi.txt"
GBIF_MUSEUM_KEY_PATH = GBIF_DIR / "museum_download_key.txt"
GBIF_MUSEUM_META = GBIF_DIR / "birds_iberia_museum_metadata.json"


# %% [markdown]
# ## Strategy B — "all observations incl. citizen-science" (`allbor`)
#
# **DOI #2**: to be minted by the user. Predicates differ from Strategy A
# only by including `HUMAN_OBSERVATION` in the BoR list.
#
#   * taxonKey = 212 (Aves, class)
#   * country IN (ES, PT, AD, GI)
#   * hasCoordinate = TRUE
#   * hasGeospatialIssue = FALSE
#   * basisOfRecord IN (HUMAN_OBSERVATION, PRESERVED_SPECIMEN,
#                      MACHINE_OBSERVATION)
#   * (no year filter)
#
# Defaults are placeholders; set `GBIF_ALLBOR_DL_KEY` and
# `GBIF_ALLBOR_DL_DOI` env vars to override.

# %%
GBIF_ALLBOR_DL_KEY = os.environ.get(
    "GBIF_ALLBOR_DL_KEY", "TODO_MINT_ALLBOR_KEY"
)
GBIF_ALLBOR_DL_DOI = os.environ.get(
    "GBIF_ALLBOR_DL_DOI", "TODO_MINT_ALLBOR_DOI"
)

GBIF_ALLBOR_PREDICATES = {
    "taxonKey": 212,
    "taxonKey_resolution": "Aves (class, ACCEPTED) — https://api.gbif.org/v1/species/match?name=Aves&rank=class",
    "country": ["ES", "PT", "AD", "GI"],
    "hasCoordinate": True,
    "hasGeospatialIssue": False,
    "basisOfRecord": [
        "HUMAN_OBSERVATION", "PRESERVED_SPECIMEN", "MACHINE_OBSERVATION"
    ],
    # no year filter — year split happens in 02_data_clean.py
}

GBIF_ALLBOR_ZIP = GBIF_DIR / "birds_iberia_allbor.zip"
GBIF_ALLBOR_DOI_PATH = GBIF_DIR / "allbor_download_doi.txt"
GBIF_ALLBOR_KEY_PATH = GBIF_DIR / "allbor_download_key.txt"
GBIF_ALLBOR_META = GBIF_DIR / "birds_iberia_allbor_metadata.json"


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
    if credentials are absent / the mint fails.

    Builds the JSON predicate from the `predicates` dict's BoR list (no year
    filter is added — the year split is a clean-stage operation now)."""
    user = os.environ.get("GBIF_USER")
    pwd = os.environ.get("GBIF_PWD")
    email = os.environ.get("GBIF_EMAIL")
    if not (user and pwd and email):
        print(f"  [skip  ]  GBIF_USER/GBIF_PWD/GBIF_EMAIL not set — cannot mint '{name}'")
        return None
    try:
        from pygbif import occurrences as occ  # noqa: F401
    except ImportError:
        print("  [skip  ]  pygbif not importable")
        return None

    json_predicate = {
        "type": "and",
        "predicates": [
            {"type": "equals", "key": "TAXON_KEY",
             "value": str(predicates["taxonKey"])},
            {"type": "equals", "key": "HAS_COORDINATE", "value": "true"},
            {"type": "equals", "key": "HAS_GEOSPATIAL_ISSUE", "value": "false"},
            {"type": "in", "key": "COUNTRY", "values": predicates["country"]},
            {"type": "in", "key": "BASIS_OF_RECORD",
             "values": predicates["basisOfRecord"]},
        ],
    }

    print(f"  [mint  ]  requesting GBIF download for '{name}'")
    print(f"            predicate = {json.dumps(json_predicate)[:200]}...")
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
    Else return a skip entry."""
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
# ## Execute the two-strategy downloads

# %%
print("\n--- Strategy A: museum + sensors ---")
museum_result = get_or_mint(
    name="museum", hardcoded_key=GBIF_MUSEUM_DL_KEY,
    hardcoded_doi=GBIF_MUSEUM_DL_DOI,
    zip_path=GBIF_MUSEUM_ZIP, doi_path=GBIF_MUSEUM_DOI_PATH,
    key_path=GBIF_MUSEUM_KEY_PATH, meta_path=GBIF_MUSEUM_META,
    predicates=GBIF_MUSEUM_PREDICATES,
)
SOURCES.append({
    "strategy": "museum",
    "name": "GBIF Iberian birds — PRESERVED_SPECIMEN + MACHINE_OBSERVATION",
    "role": "Strategy A — museum+sensor provenance (no citizen-science HUMAN_OBSERVATION)",
    "doi": museum_result.get("doi"),
    "url": (f"https://doi.org/{museum_result['doi']}"
            if museum_result.get("doi") else None),
    "license": "CC-BY-NC-4.0 (per individual GBIF datasets)",
    "accessed_on": date.today().isoformat(),
    "download_key": museum_result.get("key"),
    "predicates": GBIF_MUSEUM_PREDICATES,
    "local_path": museum_result.get("zip"),
    "skipped": museum_result.get("skipped", False),
    "skip_reason": museum_result.get("reason"),
})

# %%
print("\n--- Strategy B: all observations (incl. citizen-science) ---")
allbor_result = get_or_mint(
    name="allbor", hardcoded_key=GBIF_ALLBOR_DL_KEY,
    hardcoded_doi=GBIF_ALLBOR_DL_DOI,
    zip_path=GBIF_ALLBOR_ZIP, doi_path=GBIF_ALLBOR_DOI_PATH,
    key_path=GBIF_ALLBOR_KEY_PATH, meta_path=GBIF_ALLBOR_META,
    predicates=GBIF_ALLBOR_PREDICATES,
)
SOURCES.append({
    "strategy": "allbor",
    "name": "GBIF Iberian birds — HUMAN_OBSERVATION + PRESERVED_SPECIMEN + MACHINE_OBSERVATION",
    "role": "Strategy B — all observations including citizen-science",
    "doi": allbor_result.get("doi"),
    "url": (f"https://doi.org/{allbor_result['doi']}"
            if allbor_result.get("doi") else None),
    "license": "CC-BY-NC-4.0 (per individual GBIF datasets)",
    "accessed_on": date.today().isoformat(),
    "download_key": allbor_result.get("key"),
    "predicates": GBIF_ALLBOR_PREDICATES,
    "local_path": allbor_result.get("zip"),
    "skipped": allbor_result.get("skipped", False),
    "skip_reason": allbor_result.get("reason"),
})


# %% [markdown]
# ## Per-strategy synthetic fallback
#
# Per-strategy: if a strategy's download was skipped (placeholder key
# AND no env vars), emit a deterministic synthetic Iberian bird dataset
# at that strategy's zip path. **This is per-strategy** — Strategy A
# can be real while Strategy B is synthetic (the expected state until
# the user mints DOI #2).
#
# Each strategy writes its own synthetic-flag file
# `data/raw/USING_SYNTHETIC_DEMO_DATA_<strategy>.txt`. Downstream
# notebooks key off these flags and tag artefacts with
# `synthetic_data: true` per strategy.

# %%
def make_synthetic_demo(zip_path: Path, doi_path: Path, key_path: Path,
                        meta_path: Path, strategy: str,
                        flag_path: Path) -> dict:
    """Generate deterministic Iberian bird demo data for a single strategy.

    Writes a SIMPLE_CSV-style zip at `zip_path` with ~80 species spanning
    all years (1950-2024) so the year split in 02_data_clean.py has both
    a modern and historical frame to work with. Strategy-specific seeds
    keep the museum-vs-allbor synthetic outputs distinguishable.
    """
    import numpy as np

    # Strategy-specific seed so the two synthetic strategies differ.
    seed = {"museum": 20260522, "allbor": 20260523}.get(strategy, 20260524)
    rng = np.random.default_rng(seed=seed)

    SPECIES_N = 80
    lon0, lon1 = -10.0, 4.0
    lat0, lat1 = 35.0, 44.0

    centres_lon = rng.uniform(lon0 + 1, lon1 - 1, size=SPECIES_N)
    centres_lat = rng.uniform(lat0 + 1, lat1 - 1, size=SPECIES_N)
    range_radii = rng.uniform(1.0, 4.0, size=SPECIES_N)

    species_names = [f"Synthavis demoensis_{i:03d}" for i in range(SPECIES_N)]

    # Hotspot centres (used to inject modern-era richness peaks).
    hotspot_centres = np.array([
        [-3.5, 37.0],   # Sierra Nevada-ish
        [0.0, 42.5],    # Pyrenees-ish
        [-6.5, 39.5],   # Extremadura-ish
    ])

    records: list[dict] = []
    # 1) Historical (pre-2000) records — wide spread per species, ~20-40 each.
    for sp_idx, name in enumerate(species_names):
        n_pts = rng.integers(15, 40)
        lons = rng.normal(centres_lon[sp_idx], range_radii[sp_idx], n_pts)
        lats = rng.normal(centres_lat[sp_idx], range_radii[sp_idx] * 0.6, n_pts)
        years = rng.integers(1950, 2000, n_pts)
        keep = (lons >= lon0) & (lons <= lon1) & (lats >= lat0) & (lats <= lat1)
        for j in np.where(keep)[0]:
            records.append({
                "species": name, "lat": float(lats[j]),
                "lon": float(lons[j]), "year": int(years[j]),
                "bor": "PRESERVED_SPECIMEN",
            })
    # 2) Modern (2000+) records — denser, with hotspot-injected density for
    #    half the species. Years 2000-2024.
    for sp_idx, name in enumerate(species_names):
        n_pts = rng.integers(40, 120)
        lons = rng.normal(centres_lon[sp_idx], range_radii[sp_idx] * 0.8, n_pts)
        lats = rng.normal(centres_lat[sp_idx], range_radii[sp_idx] * 0.5, n_pts)
        years = rng.integers(2000, 2025, n_pts)
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
            records.append({
                "species": name, "lat": float(lats[j]),
                "lon": float(lons[j]), "year": int(years[j]),
                "bor": "MACHINE_OBSERVATION",
            })

    cols = ["gbifID", "species", "decimalLatitude", "decimalLongitude",
            "year", "basisOfRecord", "countryCode"]
    lines = ["\t".join(cols)]
    for i, rec in enumerate(records):
        lines.append("\t".join([
            str(i), rec["species"],
            f"{rec['lat']:.5f}", f"{rec['lon']:.5f}",
            str(rec["year"]), rec["bor"], "ES",
        ]))
    csv_text = "\n".join(lines) + "\n"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("occurrence.csv", csv_text)

    doi_path.write_text(f"SYNTHETIC_DEMO_DATA_NO_DOI_{strategy}\n")
    key_path.write_text(f"SYNTHETIC_DEMO_{strategy}\n")
    meta_path.write_text(json.dumps({
        "synthetic": True,
        "strategy": strategy,
        "seed": seed,
        "n_records": len(records),
        "n_species": SPECIES_N,
    }, indent=2))
    flag_path.write_text(
        f"Strategy '{strategy}' is SYNTHETIC DEMO DATA.\n"
        f"Mint the real GBIF DOI for this strategy and re-run to replace.\n"
    )
    print(f"  [demo  ]  wrote synthetic strategy='{strategy}': "
          f"{len(records):,} records across {SPECIES_N} species")
    return {"n_records": len(records), "n_species": SPECIES_N, "seed": seed}


# %%
# Per-strategy synthetic flag paths. Downstream notebooks read these.
SYNTHETIC_FLAG_MUSEUM = RAW_DIR / "USING_SYNTHETIC_DEMO_DATA_museum.txt"
SYNTHETIC_FLAG_ALLBOR = RAW_DIR / "USING_SYNTHETIC_DEMO_DATA_allbor.txt"

# Strategy A synthetic fallback (almost never triggered — DOI is minted)
if museum_result.get("skipped"):
    print("\n--- Synthetic demo fallback for Strategy A (museum) ---")
    demo_info = make_synthetic_demo(
        zip_path=GBIF_MUSEUM_ZIP, doi_path=GBIF_MUSEUM_DOI_PATH,
        key_path=GBIF_MUSEUM_KEY_PATH, meta_path=GBIF_MUSEUM_META,
        strategy="museum", flag_path=SYNTHETIC_FLAG_MUSEUM,
    )
    SOURCES.append({
        "strategy": "museum",
        "name": "Synthetic Iberian bird demo data (Strategy A — museum)",
        "role": "demo fallback — used when DOI #1 unavailable",
        "doi": None, "url": None,
        "license": f"n/a (generated locally, seed {demo_info['seed']})",
        "accessed_on": date.today().isoformat(),
        "synthetic": True,
        "note": "Replace by minting the real GBIF museum-strategy DOI.",
    })
else:
    if SYNTHETIC_FLAG_MUSEUM.exists():
        SYNTHETIC_FLAG_MUSEUM.unlink()

# Strategy B synthetic fallback (expected until user mints DOI #2)
if allbor_result.get("skipped"):
    print("\n--- Synthetic demo fallback for Strategy B (allbor) ---")
    demo_info = make_synthetic_demo(
        zip_path=GBIF_ALLBOR_ZIP, doi_path=GBIF_ALLBOR_DOI_PATH,
        key_path=GBIF_ALLBOR_KEY_PATH, meta_path=GBIF_ALLBOR_META,
        strategy="allbor", flag_path=SYNTHETIC_FLAG_ALLBOR,
    )
    SOURCES.append({
        "strategy": "allbor",
        "name": "Synthetic Iberian bird demo data (Strategy B — allbor)",
        "role": "demo fallback — used when DOI #2 unavailable",
        "doi": None, "url": None,
        "license": f"n/a (generated locally, seed {demo_info['seed']})",
        "accessed_on": date.today().isoformat(),
        "synthetic": True,
        "note": ("Replace by minting the real GBIF allbor-strategy DOI "
                 "(all 3 BoR values) and setting GBIF_ALLBOR_DL_KEY / "
                 "GBIF_ALLBOR_DL_DOI env vars."),
    })
else:
    if SYNTHETIC_FLAG_ALLBOR.exists():
        SYNTHETIC_FLAG_ALLBOR.unlink()


# %% [markdown]
# ## Source registry
#
# Single JSON at `data/raw/sources.json` recording every download's
# strategy/URL/DOI/license/accessed-on date + skip status. This is the
# provenance contract the Replication Study draft (Phase 5 step 04) cites.

# %%
SOURCES_JSON = RAW_DIR / "sources.json"
with open(SOURCES_JSON, "w") as f:
    json.dump({
        "sources": SOURCES,
        "strategies": {
            "museum": {
                "synthetic": museum_result.get("skipped", False),
                "doi": museum_result.get("doi"),
                "download_key": museum_result.get("key"),
                "zip": str(GBIF_MUSEUM_ZIP.relative_to(ROOT))
                if GBIF_MUSEUM_ZIP.exists() else None,
            },
            "allbor": {
                "synthetic": allbor_result.get("skipped", False),
                "doi": allbor_result.get("doi"),
                "download_key": allbor_result.get("key"),
                "zip": str(GBIF_ALLBOR_ZIP.relative_to(ROOT))
                if GBIF_ALLBOR_ZIP.exists() else None,
            },
        },
        "written_on": date.today().isoformat(),
    }, f, indent=2)
print(f"\n--- Wrote source registry -> {SOURCES_JSON}")


# %% [markdown]
# ## Summary

# %%
print("\nArtefact inventory:")
artefacts = [
    ("Museum zip",              GBIF_MUSEUM_ZIP),
    ("Museum download DOI",     GBIF_MUSEUM_DOI_PATH),
    ("Museum download key",     GBIF_MUSEUM_KEY_PATH),
    ("Museum synth flag",       SYNTHETIC_FLAG_MUSEUM),
    ("Allbor zip",              GBIF_ALLBOR_ZIP),
    ("Allbor download DOI",     GBIF_ALLBOR_DOI_PATH),
    ("Allbor download key",     GBIF_ALLBOR_KEY_PATH),
    ("Allbor synth flag",       SYNTHETIC_FLAG_ALLBOR),
    ("Source registry JSON",    SOURCES_JSON),
]
for name, p in artefacts:
    if p.exists():
        size = (
            p.stat().st_size if p.is_file()
            else sum(f.stat().st_size for f in p.rglob("*") if f.is_file())
        )
        print(f"  ok    {name:<24} {size:>12,} bytes  {p.relative_to(ROOT)}")
    else:
        print(f"  MISS  {name:<24} {'-':>12}        {p.relative_to(ROOT)}")
