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
# # 02 — Data clean (Iberian birds, HEALPix-NESTED ladder, two BoR strategies)
#
# Bins **each of the two BoR-strategy GBIF zips** from
# `01_data_download.py` onto a HEALPix **NESTED** ladder of Nside in
# {16, 32, 64, 128, 256, 512}, with a **year-stage split at the cleaning
# step**:
#
# - `year >= 2000` -> **modern** frame = "atlas-equivalent". Per-cell
#   species richness = number of distinct species observed in the cell.
# - `year < 2000`  -> **historical** frame = "range-map-equivalent". Per
#   species, build the convex hull of pre-2000 occurrences (Shapely);
#   for each Nside, the hull's HEALPix-NESTED cell coverage is computed
#   via `healpix_geo.nested.polygon_coverage`; per-cell richness = number
#   of species whose hull covers the cell.
#
# Conceptually we relabel modern as `atlas` and historical as `rangemap`
# downstream (they are the H&J 2007 analogues, and the year-window source
# is now an implementation detail of the substitute).
#
# Two strategies x two sources = four per-cell richness arrays per Nside,
# per strategy. The output layout:
#
# - `data/clean/richness_<strategy>.nc` — one NetCDF per strategy, with
#   one NetCDF group per Nside, each group holding `richness_atlas` and
#   `richness_rangemap` variables on the `cell` dimension. Different
#   per-Nside cell counts prevent a single rectangular array.
# - `data/clean/species_eoo_polygons.parquet` — per-strategy, per-species
#   convex-hull WKT polygons + record counts. `strategy` column.
# - `data/clean/clean_report.json` — per-strategy record / species
#   counts + which strategy is synthetic.
#
# **Domain conventions enforced** (`DOMAIN.md`):
#
# - HEALPix indexing is always **NESTED** at every Nside;
#   `healpix-geo` (geographic, WGS84-aware), never `healpy`.
# - Intermediate arrays use **NetCDF** + **Parquet**; never `.npz`.
# - Per-strategy synthetic flag is honoured — synthetic data is not
#   silently mixed with real data; the report json calls it out and
#   downstream artefacts carry the flag.

# %%
import json
import zipfile
from collections.abc import Iterator
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr
from healpix_geo import nested as hp_nested
from shapely.geometry import MultiPoint, Polygon

# %% [markdown]
# ## Constants
#
# - **HEALPix ladder** = Nside in {16, 32, 64, 128, 256, 512}, each
#   NESTED. Cell side ~407 km at Nside=16 down to ~13 km at Nside=512 —
#   bracketing H&J's 0.25°-2° range comfortably.
# - **Iberia bbox** matches the prior sibling chain (-10..4 lon,
#   35..44 lat).
# - **Ellipsoid** = "WGS84".

# %%
STRATEGIES = ["museum", "allbor"]
NSIDES = [16, 32, 64, 128, 256, 512]
DEPTHS = {n: int(np.log2(n)) for n in NSIDES}

ELLIPSOID = "WGS84"
YEAR_SPLIT = 2000  # year >= 2000 -> modern (atlas), year < 2000 -> historical

IBERIA_LON_MIN, IBERIA_LAT_MIN = -10.0, 35.0
IBERIA_LON_MAX, IBERIA_LAT_MAX = 4.0, 44.0

ROOT = Path("..").resolve()
DATA = ROOT / "data"
GBIF_DIR = DATA / "gbif"
RAW_DIR = DATA / "raw"
CLEAN_DIR = DATA / "clean"
CLEAN_DIR.mkdir(parents=True, exist_ok=True)

STRATEGY_ZIPS = {
    "museum": GBIF_DIR / "birds_iberia_museum.zip",
    "allbor": GBIF_DIR / "birds_iberia_allbor.zip",
}
STRATEGY_SYNTH_FLAGS = {
    "museum": RAW_DIR / "USING_SYNTHETIC_DEMO_DATA_museum.txt",
    "allbor": RAW_DIR / "USING_SYNTHETIC_DEMO_DATA_allbor.txt",
}
STRATEGY_RICHNESS_NC = {
    s: CLEAN_DIR / f"richness_{s}.nc" for s in STRATEGIES
}

EOO_PARQUET = CLEAN_DIR / "species_eoo_polygons.parquet"
CLEAN_REPORT = CLEAN_DIR / "clean_report.json"

SYNTHETIC = {s: STRATEGY_SYNTH_FLAGS[s].exists() for s in STRATEGIES}
print(f"ROOT       = {ROOT}")
print(f"STRATEGIES = {STRATEGIES}")
print(f"NSIDES     = {NSIDES}")
print(f"YEAR_SPLIT = {YEAR_SPLIT} (>= modern, < historical)")
print(f"SYNTHETIC  = {SYNTHETIC}")

report: dict = {
    "written_on": date.today().isoformat(),
    "strategies": STRATEGIES,
    "year_split": YEAR_SPLIT,
    "synthetic_per_strategy": SYNTHETIC,
    "nsides": NSIDES,
    "iberia_bbox": {
        "lon": [IBERIA_LON_MIN, IBERIA_LON_MAX],
        "lat": [IBERIA_LAT_MIN, IBERIA_LAT_MAX],
    },
    "per_strategy": {},
}


# %% [markdown]
# ## Iberian HEALPix-NESTED cell sets at each Nside
#
# Enumerate all global cells at each depth, transform centres to
# lon/lat via `healpix_geo.nested.healpix_to_lonlat`, keep those whose
# centre falls inside the Iberia bbox. (Computed once; reused for both
# strategies and both sources.)

# %%
def iberian_pix(depth: int, nside: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """All NESTED cells at `depth` whose centre lies in the Iberia bbox.

    Returns (pix, lon, lat) — each shape (n_cells,)."""
    pix_all = np.arange(12 * nside * nside, dtype=np.uint64)
    lon, lat = hp_nested.healpix_to_lonlat(pix_all, depth, ELLIPSOID)
    lon = np.where(lon > 180.0, lon - 360.0, lon)
    mask = (
        (lon >= IBERIA_LON_MIN) & (lon <= IBERIA_LON_MAX)
        & (lat >= IBERIA_LAT_MIN) & (lat <= IBERIA_LAT_MAX)
    )
    return (pix_all[mask].astype(np.int64),
            lon[mask].astype(np.float32),
            lat[mask].astype(np.float32))


IBERIA_PIX: dict[int, np.ndarray] = {}
IBERIA_LON: dict[int, np.ndarray] = {}
IBERIA_LAT: dict[int, np.ndarray] = {}
for nside in NSIDES:
    pix, lon, lat = iberian_pix(DEPTHS[nside], nside)
    IBERIA_PIX[nside] = pix
    IBERIA_LON[nside] = lon
    IBERIA_LAT[nside] = lat
    print(f"  nside={nside:>4}  (depth={DEPTHS[nside]}): "
          f"{len(pix):>7,} cells in Iberia bbox")

report["n_cells_per_nside"] = {n: int(len(IBERIA_PIX[n])) for n in NSIDES}


# %% [markdown]
# ## GBIF zip streaming reader
#
# Streams the SIMPLE_CSV inside a GBIF download zip (tab-separated
# despite the name) in chunks of 1 M rows. Each yielded chunk is already
# NA-dropped on the essentials (species, lat, lon, year) and filtered to
# the Iberia bbox, so downstream consumers can fold chunks into per-cell
# and per-species accumulators without ever materialising the whole
# dataset in memory.
#
# Streaming matters because the all-BoR allbor download is ~50–65 M
# rows (~6.5 GB compressed, ~25–30 GB uncompressed TSV). A one-shot
# `pd.read_csv` peaks at >10 GB resident and has been observed to crash
# the kernel on 16 GB laptops (see `memory/pipeline_clean_oom_risk.md`).

# %%
GBIF_CHUNKSIZE = 1_000_000


def iter_gbif_chunks(zip_path: Path,
                     chunksize: int = GBIF_CHUNKSIZE) -> Iterator[pd.DataFrame]:
    """Yield NA-dropped, bbox-filtered chunks of a GBIF SIMPLE_CSV zip."""
    if not zip_path.exists():
        raise FileNotFoundError(
            f"Expected GBIF zip at {zip_path} — re-run "
            f"notebooks/01_data_download.py to populate it."
        )
    with zipfile.ZipFile(zip_path) as zf:
        candidates = [n for n in zf.namelist() if n.endswith(".csv")]
        if not candidates:
            raise RuntimeError(f"No CSV inside {zip_path}")
        member = candidates[0]
        with zf.open(member) as src:
            reader = pd.read_csv(
                src, sep="\t",
                usecols=lambda c: c in {
                    "gbifID", "species", "decimalLatitude",
                    "decimalLongitude", "year", "basisOfRecord",
                    "countryCode",
                },
                dtype={"gbifID": "Int64", "year": "Int64",
                       "countryCode": "string"},
                chunksize=chunksize, on_bad_lines="skip",
            )
            for raw in reader:
                df = raw.dropna(
                    subset=["species", "decimalLatitude",
                            "decimalLongitude", "year"]
                )
                if df.empty:
                    continue
                lon = df["decimalLongitude"].astype(float)
                lat = df["decimalLatitude"].astype(float)
                in_bbox = (
                    (lon >= IBERIA_LON_MIN) & (lon <= IBERIA_LON_MAX)
                    & (lat >= IBERIA_LAT_MIN) & (lat <= IBERIA_LAT_MAX)
                )
                df = df.loc[in_bbox]
                if df.empty:
                    continue
                yield df.reset_index(drop=True)


# %% [markdown]
# ## Per-strategy helpers
#
# - `species_hull` — convex hull of a (lon, lat) point array with
#   pragmatic fallbacks for n < 3.
# - `hull_to_cells` — `healpix_geo.nested.polygon_coverage` of the hull.
# - `historical_cell_counts` — per Nside, per-cell count of species
#   whose EOO hull covers the cell, restricted to the Iberian cell set.
#
# Modern (atlas) per-cell richness is computed inline in the per-strategy
# streaming loop below, by folding chunked `(cell, species_id)` pairs into
# per-Nside numpy arrays and then deduplicating once at the end.

# %%
def species_hull(points: np.ndarray) -> Polygon:
    """Convex hull of a (lon, lat) point array with n<3 fallbacks."""
    if len(points) >= 3:
        mp = MultiPoint(points)
        hull = mp.convex_hull
        if hull.geom_type != "Polygon":
            hull = hull.buffer(0.05)
    elif len(points) == 2:
        from shapely.geometry import LineString
        hull = LineString(points).buffer(0.1)
    else:  # 1 point
        from shapely.geometry import Point
        hull = Point(points[0]).buffer(0.2)
    return hull


def hull_to_cells(hull: Polygon, depth: int) -> np.ndarray:
    """NESTED cell IDs covered by `hull` at `depth` via polygon_coverage."""
    exterior = np.asarray(hull.exterior.coords)[:, :2]
    if np.allclose(exterior[0], exterior[-1]):
        exterior = exterior[:-1]
    if len(exterior) < 3:
        return np.empty(0, dtype=np.int64)
    cell_ids, _, _ = hp_nested.polygon_coverage(
        exterior, depth, ellipsoid=ELLIPSOID, flat=True,
    )
    return np.asarray(cell_ids, dtype=np.int64)


def historical_cell_counts(species_hulls: dict[str, Polygon],
                           nside: int,
                           iberian_set: set[int]) -> pd.DataFrame:
    """Per-cell count of species whose EOO hull covers the cell, restricted to
    Iberian cells."""
    depth = DEPTHS[nside]
    counts: dict[int, int] = {}
    iberian_arr = np.fromiter(iberian_set, dtype=np.int64)
    for sp, hull in species_hulls.items():
        cells = hull_to_cells(hull, depth)
        cells = cells[np.isin(cells, iberian_arr)]
        for c in cells:
            counts[int(c)] = counts.get(int(c), 0) + 1
    if not counts:
        return pd.DataFrame({"cell": [], "richness": []}, dtype=np.int64)
    return pd.DataFrame(
        {"cell": list(counts.keys()),
         "richness": list(counts.values())}
    ).astype({"cell": np.int64, "richness": np.int64})


# %% [markdown]
# ## Process each strategy (streaming)
#
# Stream the zip in 1 M-row chunks. Per chunk:
#
# - Split on `YEAR_SPLIT` into modern / historical sub-chunks.
# - For modern: for each Nside, compute the `(cell, species_id)` pairs
#   and accumulate per-chunk-unique pair arrays into per-Nside lists.
#   Final per-cell atlas richness = `|distinct species per cell|` after
#   a single end-of-stream `np.unique` across all chunks.
# - For historical: accumulate per-species (lon, lat) point arrays into
#   a dict, then build convex hulls once after the stream completes.
#
# This keeps peak memory bounded by `|unique (cell, species) pairs|`
# (atlas) + `|historical records|` (range-map), rather than by the full
# row count of the zip.

# %%
all_eoo_records: list[dict] = []

for strategy in STRATEGIES:
    print(f"\n{'='*60}")
    print(f"=== Strategy: {strategy}  (synthetic={SYNTHETIC[strategy]}) ===")
    print(f"{'='*60}")
    zip_path = STRATEGY_ZIPS[strategy]
    nc_path = STRATEGY_RICHNESS_NC[strategy]

    # Per-strategy species → small int ID, so modern pair arrays can stay
    # as int64×int64 instead of carrying string objects.
    species_to_id: dict[str, int] = {}

    def _sid(sp: str) -> int:
        sid = species_to_id.get(sp)
        if sid is None:
            sid = len(species_to_id)
            species_to_id[sp] = sid
        return sid

    # Modern accumulator: per Nside, list of per-chunk-unique (cell, sid)
    # int64 pair arrays. Final dedup + per-cell count happens once below.
    modern_pairs: dict[int, list[np.ndarray]] = {n: [] for n in NSIDES}
    # Historical accumulator: per species, list of (lon, lat) point arrays.
    hist_pts: dict[str, list[np.ndarray]] = {}

    n_records_total = 0
    n_records_modern = 0
    n_records_historical = 0
    species_total: set[str] = set()
    species_modern: set[str] = set()
    species_historical: set[str] = set()
    year_min: int | None = None
    year_max: int | None = None

    for ci, chunk in enumerate(iter_gbif_chunks(zip_path), start=1):
        n_records_total += len(chunk)
        years = chunk["year"].astype(int).values
        cmin, cmax = int(years.min()), int(years.max())
        year_min = cmin if year_min is None else min(year_min, cmin)
        year_max = cmax if year_max is None else max(year_max, cmax)
        species_total.update(chunk["species"].unique().tolist())

        is_modern = years >= YEAR_SPLIT
        modern_chunk = chunk.loc[is_modern]
        hist_chunk = chunk.loc[~is_modern]
        n_records_modern += len(modern_chunk)
        n_records_historical += len(hist_chunk)

        if len(modern_chunk):
            species_modern.update(modern_chunk["species"].unique().tolist())
            mod_lon = modern_chunk["decimalLongitude"].astype(float).values
            mod_lat = modern_chunk["decimalLatitude"].astype(float).values
            mod_sp = modern_chunk["species"].values
            mod_sid = np.fromiter(
                (_sid(s) for s in mod_sp),
                dtype=np.int64, count=len(mod_sp),
            )
            for nside in NSIDES:
                cells = hp_nested.lonlat_to_healpix(
                    mod_lon, mod_lat, DEPTHS[nside], ELLIPSOID,
                ).astype(np.int64)
                pairs = np.column_stack([cells, mod_sid])
                pairs = np.unique(pairs, axis=0)
                modern_pairs[nside].append(pairs)

        if len(hist_chunk):
            species_historical.update(hist_chunk["species"].unique().tolist())
            for sp, grp in hist_chunk.groupby("species", sort=False):
                pts = (
                    grp[["decimalLongitude", "decimalLatitude"]]
                    .astype(float)
                    .values
                )
                hist_pts.setdefault(sp, []).append(pts)

        print(f"  chunk {ci:>3}: +{len(chunk):>8,} rows  "
              f"(modern +{len(modern_chunk):>8,}, "
              f"hist +{len(hist_chunk):>7,})  "
              f"running total: {n_records_total:>11,}")

    print(f"\n  loaded     : {n_records_total:>10,} records, "
          f"{len(species_total)} species  "
          f"(years {year_min}..{year_max})")
    print(f"  modern     : {n_records_modern:>10,} records, "
          f"{len(species_modern)} species  (>= {YEAR_SPLIT})")
    print(f"  historical : {n_records_historical:>10,} records, "
          f"{len(species_historical)} species  (< {YEAR_SPLIT})")

    strat_report: dict = {
        "synthetic": SYNTHETIC[strategy],
        "n_records_total": int(n_records_total),
        "n_species_total": int(len(species_total)),
        "n_records_modern": int(n_records_modern),
        "n_species_modern": int(len(species_modern)),
        "n_records_historical": int(n_records_historical),
        "n_species_historical": int(len(species_historical)),
        "year_min": int(year_min) if year_min is not None else None,
        "year_max": int(year_max) if year_max is not None else None,
    }

    # --- Build per-species EOO hulls from accumulated historical points ---
    print(f"\n--- Building per-species EOO hulls (historical, {strategy}) ---")
    species_hulls: dict[str, Polygon] = {}
    n_species_eoo = len(hist_pts)
    sorted_species = sorted(hist_pts.keys())
    for i, sp in enumerate(sorted_species, start=1):
        parts = hist_pts.pop(sp)
        pts = np.vstack(parts) if len(parts) > 1 else parts[0]
        hull = species_hull(pts)
        species_hulls[sp] = hull
        all_eoo_records.append({
            "strategy": strategy,
            "species": sp,
            "n_points": int(len(pts)),
            "hull_area_sqdeg": float(hull.area),
            "wkt": hull.wkt,
        })
        if i % 50 == 0 or i == n_species_eoo:
            print(f"  built hull {i:>4}/{n_species_eoo}  ({sp[:32]}, "
                  f"area={hull.area:.2f} deg^2)")
    strat_report["n_species_with_eoo"] = int(n_species_eoo)

    # --- Per-Nside per-cell richness for this strategy ---
    print(f"\n--- Cross-tabulating richness per Nside ({strategy}) ---")
    # Write each Nside as a NetCDF group inside the per-strategy file.
    if nc_path.exists():
        nc_path.unlink()
    strat_report["per_nside"] = {}
    for nside in NSIDES:
        iberian_pix_arr = IBERIA_PIX[nside]
        iberian_set = set(int(p) for p in iberian_pix_arr)

        # Atlas: dedup across chunks, restrict to Iberian cells, then count
        # distinct species per cell.
        parts = modern_pairs[nside]
        if parts:
            all_pairs = np.vstack(parts) if len(parts) > 1 else parts[0]
            all_pairs = np.unique(all_pairs, axis=0)
            mask = np.isin(all_pairs[:, 0], iberian_pix_arr)
            kept_cells = all_pairs[mask, 0]
            uniq_cells, counts = np.unique(kept_cells, return_counts=True)
            mod = pd.DataFrame(
                {"cell": uniq_cells, "richness": counts}
            ).astype({"cell": np.int64, "richness": np.int64}).set_index("cell")
        else:
            mod = pd.DataFrame(
                {"cell": [], "richness": []}, dtype=np.int64,
            ).set_index("cell")
        # Free per-Nside pair memory now that we've reduced it.
        modern_pairs[nside] = []

        hist = historical_cell_counts(species_hulls, nside, iberian_set).set_index("cell")

        df = pd.DataFrame({"cell": iberian_pix_arr}).set_index("cell")
        df["richness_atlas"] = (
            mod["richness"].reindex(df.index, fill_value=0).astype(np.int32)
        )
        df["richness_rangemap"] = (
            hist["richness"].reindex(df.index, fill_value=0).astype(np.int32)
        )
        df["lon"] = IBERIA_LON[nside]
        df["lat"] = IBERIA_LAT[nside]

        n_cells = len(df)
        mean_a = float(df["richness_atlas"].mean())
        mean_r = float(df["richness_rangemap"].mean())
        zz = int(((df["richness_atlas"] == 0) & (df["richness_rangemap"] == 0)).sum())
        print(f"  nside={nside:>4}  "
              f"n_cells={n_cells:>6,}  "
              f"mean richness atlas={mean_a:5.2f}, rangemap={mean_r:5.2f}  "
              f"zero-zero={zz:>5,}")
        strat_report["per_nside"][nside] = {
            "n_cells": int(n_cells),
            "mean_richness_atlas": round(mean_a, 3),
            "mean_richness_rangemap": round(mean_r, 3),
            "zero_zero_cells": zz,
        }

        ds = xr.Dataset(
            data_vars={
                "richness_atlas": (
                    ("cell",), df["richness_atlas"].values,
                    {"long_name": "Per-cell species richness from modern "
                                  "(year>=2000) GBIF occurrences (atlas-equivalent)",
                     "units": "n_species",
                     "strategy": strategy,
                     "synthetic": str(SYNTHETIC[strategy])}),
                "richness_rangemap": (
                    ("cell",), df["richness_rangemap"].values,
                    {"long_name": "Per-cell species richness from historical "
                                  "(year<2000) EOO convex-hull coverage (range-map-equivalent)",
                     "units": "n_species",
                     "strategy": strategy,
                     "synthetic": str(SYNTHETIC[strategy])}),
            },
            coords={
                "cell": ("cell", df.index.values.astype(np.int64),
                         {"long_name": f"HEALPix NESTED pixel index (nside={nside})"}),
                "lon": ("cell", df["lon"].values,
                        {"units": "degrees_east"}),
                "lat": ("cell", df["lat"].values,
                        {"units": "degrees_north"}),
            },
            attrs={
                "nside": nside,
                "depth": DEPTHS[nside],
                "ellipsoid": ELLIPSOID,
                "healpix_ordering": "NESTED",
                "strategy": strategy,
                "synthetic": str(SYNTHETIC[strategy]),
                "year_split": YEAR_SPLIT,
            },
        )
        ds.to_netcdf(
            nc_path,
            mode="a" if nc_path.exists() else "w",
            group=f"nside_{nside}",
            engine="netcdf4",
            encoding={
                "richness_atlas": {"zlib": True, "complevel": 4},
                "richness_rangemap": {"zlib": True, "complevel": 4},
            },
        )

    size_mb = nc_path.stat().st_size / 1e6
    print(f"\n  saved {nc_path}  ({size_mb:.2f} MB)")
    strat_report["richness_nc"] = str(nc_path.relative_to(ROOT))
    strat_report["richness_nc_size_mb"] = round(size_mb, 2)
    report["per_strategy"][strategy] = strat_report


# %% [markdown]
# ## Persist per-strategy EOO polygons + clean report
#
# Single parquet covering both strategies, with a `strategy` column.

# %%
eoo_df = pd.DataFrame(all_eoo_records)
eoo_df.to_parquet(EOO_PARQUET, index=False)
print(f"\nsaved {EOO_PARQUET} "
      f"({EOO_PARQUET.stat().st_size / 1e3:.1f} KB; "
      f"{len(eoo_df)} species-rows across {eoo_df['strategy'].nunique()} strategies)")

with open(CLEAN_REPORT, "w") as f:
    json.dump(report, f, indent=2, default=str)
print(f"\n--- Clean report -> {CLEAN_REPORT}")
print(json.dumps(report, indent=2, default=str))
