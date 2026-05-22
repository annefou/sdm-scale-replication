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
# # 02 — Data clean (Iberian birds, HEALPix-NESTED ladder)
#
# Bins the two GBIF inputs from `01_data_download.py` onto a HEALPix
# **NESTED** ladder of Nside in {16, 32, 64, 128, 256, 512}, producing
# per-Nside per-cell species presence/richness:
#
# 1. **Modern (post-2000) GBIF -> per-cell species richness (atlas-eq).**
#    For each occurrence record, compute its HEALPix NESTED pixel ID at
#    each Nside via `healpix_geo.nested.lonlat_to_healpix`. Then
#    per-Nside richness = number of distinct species observed in each cell.
#
# 2. **Historical (pre-2000) GBIF -> per-species convex-hull EOO -> per-cell
#    richness (range-map-eq).** For each species, build the convex hull
#    of its historical occurrence points; for each Nside, identify which
#    HEALPix cells the hull polygon covers; richness = number of
#    species whose hull covers the cell.
#
# Outputs (under `data/clean/`):
#
# - `richness_per_nside.nc` — one NetCDF with dims (`nside`, `cell`) and
#   variables `richness_modern`, `richness_historical`. Sparse: only
#   cells that fall in the Iberia bbox; cells with zero species are
#   present with richness=0 (so the Wilcoxon test in 03 has matched
#   pairs).
# - `species_eoo_polygons.parquet` — per-species WKT polygons + record
#   counts (audit trail for the EOO substitute).
# - `clean_report.json` — counts that 03 sanity-checks against.
#
# **Domain conventions enforced** (`DOMAIN.md`):
#
# - HEALPix indexing is always **NESTED** at every Nside; `healpix-geo`
#   not `healpy`.
# - Intermediate arrays use **NetCDF** + **Parquet**; never `.npz`.

# %%
import json
import zipfile
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
#   NESTED. Corresponding `depth = log2(Nside)` is the value the
#   `healpix-geo` API takes (depth = 4, 5, 6, 7, 8, 9). At Nside=16 the
#   cell side ~220 km; at Nside=512 it's ~7 km — bracketing H&J's
#   0.25°-2° range comfortably (DOMAIN.md / spec).
# - **Iberia bbox** matches the prior sibling chain (-10..4 lon,
#   35..44 lat) so cell sets are comparable.
# - **Ellipsoid** = "WGS84" — geo-aware, not pure sphere.

# %%
NSIDES = [16, 32, 64, 128, 256, 512]
DEPTHS = {n: int(np.log2(n)) for n in NSIDES}

ELLIPSOID = "WGS84"

# Iberia bounding box (lon_min, lat_min, lon_max, lat_max).
IBERIA_LON_MIN, IBERIA_LAT_MIN = -10.0, 35.0
IBERIA_LON_MAX, IBERIA_LAT_MAX = 4.0, 44.0

ROOT = Path("..").resolve()
DATA = ROOT / "data"
GBIF_DIR = DATA / "gbif"
RAW_DIR = DATA / "raw"
CLEAN_DIR = DATA / "clean"
CLEAN_DIR.mkdir(parents=True, exist_ok=True)

GBIF_MODERN_ZIP = GBIF_DIR / "birds_iberia_modern.zip"
GBIF_HISTORICAL_ZIP = GBIF_DIR / "birds_iberia_historical.zip"
SYNTHETIC_FLAG = RAW_DIR / "USING_SYNTHETIC_DEMO_DATA.txt"

RICHNESS_NC = CLEAN_DIR / "richness_per_nside.nc"
EOO_PARQUET = CLEAN_DIR / "species_eoo_polygons.parquet"
CLEAN_REPORT = CLEAN_DIR / "clean_report.json"

SYNTHETIC = SYNTHETIC_FLAG.exists()
print(f"ROOT       = {ROOT}")
print(f"NSIDES     = {NSIDES}")
print(f"SYNTHETIC  = {SYNTHETIC}")

report: dict = {
    "written_on": date.today().isoformat(),
    "synthetic_data": SYNTHETIC,
    "nsides": NSIDES,
    "iberia_bbox": {
        "lon": [IBERIA_LON_MIN, IBERIA_LON_MAX],
        "lat": [IBERIA_LAT_MIN, IBERIA_LAT_MAX],
    },
}


# %% [markdown]
# ## Iberian HEALPix-NESTED cell sets at each Nside
#
# Enumerate all global cells at each depth, transform centres to
# lon/lat via `healpix_geo.nested.healpix_to_lonlat`, keep those whose
# centre falls inside the Iberia bbox. Per the NESTED parent invariant
# (`parent = child >> 2`) cells at coarser Nside are exact unions of
# their fine-Nside children — useful for sanity-checks but not relied
# upon here (each Nside is enumerated independently for robustness).

# %%
def iberian_pix(depth: int, nside: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """All NESTED cells at `depth` whose centre lies in the Iberia bbox.

    Returns (pix, lon, lat) — each shape (n_cells,)."""
    pix_all = np.arange(12 * nside * nside, dtype=np.uint64)
    lon, lat = hp_nested.healpix_to_lonlat(pix_all, depth, ELLIPSOID)
    # healpix-geo returns lon in radians? Check by inspecting range.
    # Per the API doc and tests, healpix-geo returns degrees.
    # Normalise lon to [-180, 180].
    lon = np.where(lon > 180.0, lon - 360.0, lon)
    mask = (
        (lon >= IBERIA_LON_MIN) & (lon <= IBERIA_LON_MAX)
        & (lat >= IBERIA_LAT_MIN) & (lat <= IBERIA_LAT_MAX)
    )
    return pix_all[mask].astype(np.int64), lon[mask].astype(np.float32), lat[mask].astype(np.float32)


# Quick sanity probe — print N cells at each depth.
IBERIA_PIX: dict[int, np.ndarray] = {}
IBERIA_LON: dict[int, np.ndarray] = {}
IBERIA_LAT: dict[int, np.ndarray] = {}
for nside in NSIDES:
    pix, lon, lat = iberian_pix(DEPTHS[nside], nside)
    IBERIA_PIX[nside] = pix
    IBERIA_LON[nside] = lon
    IBERIA_LAT[nside] = lat
    print(f"  nside={nside:>4}  (depth={DEPTHS[nside]}): {len(pix):>7,} cells in Iberia bbox")

report["n_cells_per_nside"] = {n: int(len(IBERIA_PIX[n])) for n in NSIDES}


# %% [markdown]
# ## Load the two GBIF datasets

# %%
def load_gbif_csv(zip_path: Path) -> pd.DataFrame:
    """Extract and read the SIMPLE_CSV inside a GBIF download zip.

    GBIF SIMPLE_CSV is TAB-delimited despite the name. The synthetic
    fallback writes the same TAB schema."""
    if not zip_path.exists():
        raise FileNotFoundError(
            f"Expected GBIF zip at {zip_path} — re-run notebooks/01_data_download.py "
            f"to populate it (real or synthetic)."
        )
    with zipfile.ZipFile(zip_path) as zf:
        candidates = [n for n in zf.namelist() if n.endswith(".csv")]
        if not candidates:
            raise RuntimeError(f"No CSV inside {zip_path}")
        member = candidates[0]
        with zf.open(member) as src:
            df = pd.read_csv(
                src, sep="\t",
                usecols=lambda c: c in {
                    "gbifID", "species", "decimalLatitude",
                    "decimalLongitude", "year", "basisOfRecord",
                    "countryCode",
                },
                dtype={"gbifID": "Int64", "year": "Int64",
                       "countryCode": "string"},
                low_memory=False,
            )
    # Drop rows missing the essentials.
    df = df.dropna(subset=["species", "decimalLatitude", "decimalLongitude"]).copy()
    # Iberia bbox guard (synthetic data is already inside, but real GBIF
    # downloads can include rare overseas-territory points).
    lon = df["decimalLongitude"].astype(float)
    lat = df["decimalLatitude"].astype(float)
    in_bbox = (
        (lon >= IBERIA_LON_MIN) & (lon <= IBERIA_LON_MAX)
        & (lat >= IBERIA_LAT_MIN) & (lat <= IBERIA_LAT_MAX)
    )
    df = df.loc[in_bbox].reset_index(drop=True)
    return df


print("\n--- Loading GBIF zips ---")
df_modern = load_gbif_csv(GBIF_MODERN_ZIP)
df_historical = load_gbif_csv(GBIF_HISTORICAL_ZIP)
print(f"  modern    : {len(df_modern):>10,} records, "
      f"{df_modern['species'].nunique()} species")
print(f"  historical: {len(df_historical):>10,} records, "
      f"{df_historical['species'].nunique()} species")
report["n_records_modern"] = int(len(df_modern))
report["n_records_historical"] = int(len(df_historical))
report["n_species_modern"] = int(df_modern["species"].nunique())
report["n_species_historical"] = int(df_historical["species"].nunique())


# %% [markdown]
# ## Modern occurrences -> per-cell richness at each Nside
#
# For each Nside, assign each modern occurrence to its HEALPix-NESTED
# cell, count the number of distinct species per cell. Cells with zero
# species are NOT pre-populated here; we only emit cells with >=1
# species observed (sparse representation). The merge step below
# right-joins onto the full Iberian-cell index per Nside, filling
# unseen cells with richness=0.

# %%
def occurrences_to_richness(df: pd.DataFrame, nside: int) -> pd.DataFrame:
    """Per-cell unique-species count at one Nside."""
    depth = DEPTHS[nside]
    cells = hp_nested.lonlat_to_healpix(
        df["decimalLongitude"].astype(float).values,
        df["decimalLatitude"].astype(float).values,
        depth, ELLIPSOID,
    ).astype(np.int64)
    species = df["species"].values
    sub = pd.DataFrame({"cell": cells, "species": species})
    return (
        sub.drop_duplicates(["cell", "species"])
           .groupby("cell", as_index=False)
           .size()
           .rename(columns={"size": "richness"})
    )


# %% [markdown]
# ## Historical occurrences -> per-species convex-hull EOO -> per-cell
#
# Per species: compute the convex hull of all its historical points
# (Shapely). For each Nside, find every HEALPix-NESTED cell that the
# hull polygon covers via `healpix_geo.nested.polygon_coverage`. Per
# cell, sum the number of species whose hull covers it -> richness.
#
# Edge case: a species with < 3 points has no real convex hull. For
# 2 points we use a small buffer around the line; for 1 point we use
# a small disc. These are pragmatic substitutes — they preserve the
# species in the richness count without dominating it. Synthetic data
# has 15+ points per species so this branch only matters for real GBIF
# data with rare species.

# %%
def species_hull(points: np.ndarray) -> Polygon:
    """Convex hull of a (lon, lat) point array. Tolerates n<3 by
    buffering. Returns a Shapely Polygon."""
    if len(points) >= 3:
        mp = MultiPoint(points)
        hull = mp.convex_hull
        # convex_hull may return a Point or LineString for collinear /
        # duplicate points — buffer in that case.
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
    """Return the array of NESTED cell IDs covered by `hull` at `depth`.

    healpix-geo's polygon_coverage expects an (n, 2) array of (lon, lat)
    vertices forming a polygon WITHOUT holes."""
    # Get the exterior ring as a (n, 2) numpy array.
    exterior = np.asarray(hull.exterior.coords)[:, :2]
    # polygon_coverage closes the polygon itself; pass the open ring.
    if np.allclose(exterior[0], exterior[-1]):
        exterior = exterior[:-1]
    if len(exterior) < 3:
        return np.empty(0, dtype=np.int64)
    cell_ids, _, _ = hp_nested.polygon_coverage(
        exterior, depth, ellipsoid=ELLIPSOID, flat=True,
    )
    return np.asarray(cell_ids, dtype=np.int64)


print("\n--- Building per-species EOO hulls (historical) ---")
species_groups = df_historical.groupby("species")
n_species = species_groups.ngroups
eoo_records: list[dict] = []
species_hulls: dict[str, Polygon] = {}

for i, (sp, grp) in enumerate(species_groups, start=1):
    pts = grp[["decimalLongitude", "decimalLatitude"]].astype(float).values
    hull = species_hull(pts)
    species_hulls[sp] = hull
    eoo_records.append({
        "species": sp,
        "n_points": int(len(pts)),
        "hull_area_sqdeg": float(hull.area),
        "wkt": hull.wkt,
    })
    if i % 20 == 0 or i == n_species:
        print(f"  built hull {i:>4}/{n_species}  ({sp[:32]}, area={hull.area:.2f} deg^2)")

eoo_df = pd.DataFrame(eoo_records)
eoo_df.to_parquet(EOO_PARQUET, index=False)
print(f"  saved {EOO_PARQUET} "
      f"({EOO_PARQUET.stat().st_size / 1e3:.1f} KB; "
      f"{len(eoo_df)} species)")
report["n_species_with_eoo"] = int(len(eoo_df))


# %% [markdown]
# ## Cross both data sources with each Iberian cell-set
#
# For each Nside, build a long DataFrame of (cell, richness_modern,
# richness_historical). Cells absent from one of the two sources get
# richness=0 there.

# %%
def historical_cell_counts(species_hulls: dict[str, Polygon],
                           nside: int,
                           iberian_set: set[int]) -> pd.DataFrame:
    """Per-cell count of species whose EOO hull covers the cell, restricted
    to cells inside the Iberian set."""
    depth = DEPTHS[nside]
    counts: dict[int, int] = {}
    for sp, hull in species_hulls.items():
        cells = hull_to_cells(hull, depth)
        # Keep only Iberian cells.
        cells = cells[np.isin(cells, list(iberian_set))]
        for c in cells:
            counts[int(c)] = counts.get(int(c), 0) + 1
    if not counts:
        return pd.DataFrame({"cell": [], "richness": []}, dtype=np.int64)
    return pd.DataFrame(
        {"cell": list(counts.keys()),
         "richness": list(counts.values())}
    ).astype({"cell": np.int64, "richness": np.int64})


# Assemble per-Nside per-cell rich aligned across both sources.
print("\n--- Cross-tabulating richness per Nside ---")
records_per_nside: list[xr.Dataset] = []
for nside in NSIDES:
    iberian_pix = IBERIA_PIX[nside]
    iberian_set = set(int(p) for p in iberian_pix)

    # Modern: groupby.
    mod = occurrences_to_richness(df_modern, nside)
    mod = mod[mod["cell"].isin(iberian_set)].set_index("cell")

    # Historical: from hulls.
    hist = historical_cell_counts(species_hulls, nside, iberian_set).set_index("cell")

    # Align on the full Iberian cell index.
    df = pd.DataFrame({"cell": iberian_pix}).set_index("cell")
    df["richness_modern"] = mod["richness"].reindex(df.index, fill_value=0).astype(np.int32)
    df["richness_historical"] = hist["richness"].reindex(df.index, fill_value=0).astype(np.int32)
    df["lon"] = IBERIA_LON[nside]
    df["lat"] = IBERIA_LAT[nside]

    n_cells = len(df)
    mean_mod = df["richness_modern"].mean()
    mean_hist = df["richness_historical"].mean()
    overlap_zero_zero = ((df["richness_modern"] == 0) & (df["richness_historical"] == 0)).sum()
    print(f"  nside={nside:>4}  "
          f"n_cells={n_cells:>6,}  "
          f"mean_richness mod={mean_mod:5.2f}, hist={mean_hist:5.2f}  "
          f"zero-zero cells={overlap_zero_zero:>5,}")

    ds = xr.Dataset(
        data_vars={
            "richness_modern": (("cell",), df["richness_modern"].values,
                                {"long_name": "Per-cell species richness from modern GBIF (atlas-equivalent)",
                                 "units": "n_species"}),
            "richness_historical": (("cell",), df["richness_historical"].values,
                                    {"long_name": "Per-cell species richness from historical EOO hulls (range-map-equivalent)",
                                     "units": "n_species"}),
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
        },
    )
    records_per_nside.append(ds.expand_dims(nside=[nside]))


# %% [markdown]
# ## Persist — one NetCDF per Nside (different cell-counts per Nside
# prevent a single (nside, cell) dataset from being rectangular).
#
# We save each Nside as its own group in the same NetCDF file via the
# `group=` argument. Downstream code (03_analysis.py) iterates the
# groups.

# %%
# Strategy: write each per-Nside Dataset as a separate group in the
# same NetCDF file. This sidesteps the rectangular-shape constraint
# (each Nside has a different n_cells) without splitting across files.
# Note: NetCDF group nesting requires netcdf4 engine.
print(f"\n--- Saving {RICHNESS_NC} (one group per nside) ---")
# Clean any prior file (netcdf4 group write mode='a' needs the file present;
# easier to start fresh).
if RICHNESS_NC.exists():
    RICHNESS_NC.unlink()

for ds in records_per_nside:
    nside = int(ds.nside.values[0])
    # Drop the singleton nside dim — it's the group name.
    ds_to_save = ds.squeeze("nside", drop=True)
    ds_to_save.to_netcdf(
        RICHNESS_NC,
        mode="a" if RICHNESS_NC.exists() else "w",
        group=f"nside_{nside}",
        engine="netcdf4",
        encoding={
            "richness_modern": {"zlib": True, "complevel": 4},
            "richness_historical": {"zlib": True, "complevel": 4},
        },
    )
size_mb = RICHNESS_NC.stat().st_size / 1e6
print(f"  saved {RICHNESS_NC}  ({size_mb:.2f} MB)")
report["richness_nc"] = str(RICHNESS_NC.relative_to(ROOT))
report["richness_nc_size_mb"] = round(size_mb, 2)


# %% [markdown]
# ## Clean report

# %%
with open(CLEAN_REPORT, "w") as f:
    json.dump(report, f, indent=2, default=str)
print(f"\n--- Clean report -> {CLEAN_REPORT}")
print(json.dumps(report, indent=2, default=str))
