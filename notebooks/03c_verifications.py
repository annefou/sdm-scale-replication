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
# # 03c — Verifications (stress-test the gap decomposition)
#
# The decomposition in `notebooks/03b_diagnostics.py` claimed:
#
# 1. **Temporal axis: negligible** (< 1 pp at Nside 256).
# 2. **Few-sample noise: irrelevant** (n_points ≥ 20 filter moves < 1 pp).
# 3. **Hull-as-rangemap: the entire gap** (everything else).
#
# This notebook stress-tests those claims with five independent tests
# that each *could refute* one or more claims. Failure here means we
# revise the decomposition before drafting the Outcome.
#
# Tests:
#
# - **Test 1 — Land mask.** Iberia bbox includes ocean + S. France +
#   N. Morocco. Restrict to cells whose centre is on Iberian-peninsula
#   land (NaturalEarth 10m). If misidentification drops materially, the
#   prior decomposition was confounded by geographic-scope leakage.
# - **Test 2 — Top-K sensitivity sweep.** K ∈ {1, 2, 5, 10, 25}%. If the
#   trend is K-dependent, our 5% number may sit on a statistical cliff.
# - **Test 3 — Per-species hull drift.** For species present in both eras,
#   Jaccard distance between pre-2000 and post-2000 convex hulls. If
#   median drift is large (> 0.3), the temporal-axis claim was wrong.
# - **Test 4 — Atlas vs observer-effort correlation.** Per-cell Pearson r
#   between species count (atlas richness) and record count (observer
#   effort). If r > 0.9, the atlas is partly an observer-effort proxy and
#   the comparison with rangemap is partly meaningless.
# - **Test 5 — Concave hull substitute (shapely 2.0 `concave_hull`).**
#   Tighter polygons than convex hull, same data. If misidentification
#   drops materially, the hull-as-rangemap claim is verified.
#
# Tests 4 + 5 share a single re-stream of each GBIF zip (per chunk:
# accumulate per-(cell, Nside) record counts AND per-species post-2000
# points). ~13 minutes per strategy; ~26 minutes total compute.

# %%
import json
import warnings
import zipfile
from collections.abc import Iterator
from itertools import product
from pathlib import Path

import cartopy.io.shapereader as shpreader
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import xarray as xr
from healpix_geo import nested as hp_nested
from shapely import concave_hull, wkt as shp_wkt
from shapely.geometry import MultiPoint, Point, Polygon, box
from shapely.ops import unary_union

plt.style.use("seaborn-v0_8-whitegrid")
warnings.filterwarnings("ignore", category=RuntimeWarning)


# %% [markdown]
# ## Constants and paths

# %%
STRATEGIES = ["museum", "allbor"]
NSIDES = [16, 32, 64, 128, 256, 512]
DEPTHS = {n: int(np.log2(n)) for n in NSIDES}
ELLIPSOID = "WGS84"
YEAR_SPLIT = 2000

IBERIA_LON_MIN, IBERIA_LAT_MIN = -10.0, 35.0
IBERIA_LON_MAX, IBERIA_LAT_MAX = 4.0, 44.0

HOTSPOT_FRACTIONS = [0.01, 0.02, 0.05, 0.10, 0.25]
DEFAULT_FRACTION = 0.05
CONCAVE_RATIO = 0.3  # 0 = tightest, 1 = convex hull
CONCAVE_SUBSAMPLE_MAX = 10_000  # subsample big species to bound runtime
GBIF_CHUNKSIZE = 1_000_000

ROOT = Path("..").resolve()
DATA = ROOT / "data"
GBIF_DIR = DATA / "gbif"
CLEAN_DIR = DATA / "clean"
RESULTS_DIR = ROOT / "results"
FIGURES_DIR = ROOT / "figures"
FIGURES_DIR.mkdir(parents=True, exist_ok=True)
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

STRATEGY_ZIPS = {
    s: GBIF_DIR / f"birds_iberia_{s}.zip" for s in STRATEGIES
}
STRATEGY_RICHNESS_NC = {
    s: CLEAN_DIR / f"richness_{s}.nc" for s in STRATEGIES
}
EOO_PARQUET = CLEAN_DIR / "species_eoo_polygons.parquet"

STRATEGY_COLORS = {"museum": "#1f77b4", "allbor": "#d62728"}


# %% [markdown]
# ## Helpers (copied from 02 + 03b)

# %%
def iberian_pix(depth: int, nside: int):
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


def top_k_set(richness: np.ndarray, fraction: float) -> set[int]:
    n = len(richness)
    if n == 0:
        return set()
    top_k = max(1, int(np.ceil(fraction * n)))
    idx = np.argpartition(richness, -top_k)[-top_k:]
    return set(int(i) for i in idx)


def hotspot_misidentified_pct(atlas: np.ndarray,
                              rangemap: np.ndarray,
                              fraction: float = DEFAULT_FRACTION) -> float:
    atl = top_k_set(atlas, fraction)
    rm = top_k_set(rangemap, fraction)
    union = atl | rm
    inter = atl & rm
    if not union:
        return 0.0
    return (len(union) - len(inter)) / len(union) * 100.0


def convex_hull(points: np.ndarray) -> Polygon:
    if len(points) >= 3:
        hull = MultiPoint(points).convex_hull
        if hull.geom_type != "Polygon":
            hull = hull.buffer(0.05)
    elif len(points) == 2:
        from shapely.geometry import LineString
        hull = LineString(points).buffer(0.1)
    else:
        hull = Point(points[0]).buffer(0.2)
    return hull


def concave_hull_safe(points: np.ndarray,
                      ratio: float = CONCAVE_RATIO) -> Polygon:
    """Concave hull via shapely 2.0; falls back to convex for tiny n."""
    if len(points) < 4:
        return convex_hull(points)
    if len(points) > CONCAVE_SUBSAMPLE_MAX:
        rng = np.random.default_rng(42)
        idx = rng.choice(len(points), size=CONCAVE_SUBSAMPLE_MAX,
                         replace=False)
        points = points[idx]
    try:
        ch = concave_hull(MultiPoint(points), ratio=ratio)
        if ch.geom_type == "Polygon" and not ch.is_empty:
            return ch
    except Exception:
        pass
    return convex_hull(points)


def hull_to_cells(hull: Polygon, depth: int) -> np.ndarray:
    exterior = np.asarray(hull.exterior.coords)[:, :2]
    if np.allclose(exterior[0], exterior[-1]):
        exterior = exterior[:-1]
    if len(exterior) < 3:
        return np.empty(0, dtype=np.int64)
    cell_ids, _, _ = hp_nested.polygon_coverage(
        exterior, depth, ellipsoid=ELLIPSOID, flat=True,
    )
    return np.asarray(cell_ids, dtype=np.int64)


def hulls_to_per_cell_count(species_hulls: dict[str, Polygon],
                            nside: int,
                            iberian_arr: np.ndarray) -> dict[int, int]:
    depth = DEPTHS[nside]
    counts: dict[int, int] = {}
    for hull in species_hulls.values():
        if hull.geom_type == "MultiPolygon":
            polys = list(hull.geoms)
        else:
            polys = [hull]
        cell_acc: set[int] = set()
        for p in polys:
            cells = hull_to_cells(p, depth)
            cells = cells[np.isin(cells, iberian_arr)]
            cell_acc.update(int(c) for c in cells)
        for c in cell_acc:
            counts[c] = counts.get(c, 0) + 1
    return counts


def align_counts_to_cells(counts: dict[int, int],
                          cells_arr: np.ndarray) -> np.ndarray:
    out = np.zeros(len(cells_arr), dtype=np.int64)
    cell_to_idx = {int(c): i for i, c in enumerate(cells_arr)}
    for cell, n in counts.items():
        idx = cell_to_idx.get(int(cell))
        if idx is not None:
            out[idx] = int(n)
    return out


def iter_gbif_chunks(zip_path: Path,
                     chunksize: int = GBIF_CHUNKSIZE) -> Iterator[pd.DataFrame]:
    if not zip_path.exists():
        raise FileNotFoundError(f"Missing GBIF zip: {zip_path}")
    with zipfile.ZipFile(zip_path) as zf:
        candidates = [n for n in zf.namelist() if n.endswith(".csv")]
        with zf.open(candidates[0]) as src:
            reader = pd.read_csv(
                src, sep="\t",
                usecols=lambda c: c in {
                    "species", "decimalLatitude",
                    "decimalLongitude", "year",
                },
                dtype={"year": "Int64"},
                chunksize=chunksize, on_bad_lines="skip",
            )
            for raw in reader:
                df = raw.dropna(subset=["species", "decimalLatitude",
                                        "decimalLongitude", "year"])
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
# ## Load existing artefacts

# %%
eoo_df = pd.read_parquet(EOO_PARQUET)
print(f"Pre-2000 hulls: {len(eoo_df)} "
      f"{eoo_df['strategy'].value_counts().to_dict()}")

IBERIA_PIX = {}
IBERIA_LON = {}
IBERIA_LAT = {}
for n in NSIDES:
    p, lon, lat = iberian_pix(DEPTHS[n], n)
    IBERIA_PIX[n] = p
    IBERIA_LON[n] = lon
    IBERIA_LAT[n] = lat

richness: dict[str, dict[int, dict[str, np.ndarray]]] = {s: {} for s in STRATEGIES}
for s in STRATEGIES:
    for n in NSIDES:
        ds = xr.open_dataset(
            STRATEGY_RICHNESS_NC[s], group=f"nside_{n}", engine="netcdf4",
        )
        richness[s][n] = {
            "cells": ds["cell"].values.astype(np.int64),
            "atlas": ds["richness_atlas"].values.astype(np.int64),
            "rangemap_temporal": ds["richness_rangemap"].values.astype(np.int64),
        }
        ds.close()


# %% [markdown]
# ## TEST 1 — Land mask
#
# Cells whose centre falls on Iberian-peninsula land (not ocean,
# not France, not Morocco) are the "honest" comparison set: cells where
# both atlas observations and rangemap predictions can be meaningfully
# compared. Cells over water or outside the peninsula tend to have ~0
# atlas richness and non-zero rangemap richness (hulls extend across
# political boundaries) → asymmetric inflation of misidentification.

# %%
print("\n" + "=" * 64)
print("TEST 1 — Land mask (Iberian peninsula only)")
print("=" * 64)

# Load NaturalEarth 10m land polygons, restrict to Iberia bbox, then
# subtract France + Morocco countries to leave Spain+Portugal+Andorra+Gib.
iberia_bbox = box(IBERIA_LON_MIN, IBERIA_LAT_MIN,
                  IBERIA_LON_MAX, IBERIA_LAT_MAX)
land_reader = shpreader.Reader(
    shpreader.natural_earth(resolution="10m", category="physical",
                            name="land")
)
land_geoms = [g.intersection(iberia_bbox) for g in land_reader.geometries()]
land_geoms = [g for g in land_geoms if not g.is_empty]
land_in_bbox = unary_union(land_geoms)

countries_reader = shpreader.Reader(
    shpreader.natural_earth(resolution="10m", category="cultural",
                            name="admin_0_countries")
)
peninsula_country_names = {"Spain", "Portugal", "Andorra", "Gibraltar"}
peninsula_geoms = []
for rec in countries_reader.records():
    name = rec.attributes.get("NAME") or rec.attributes.get("name")
    if name in peninsula_country_names:
        g = rec.geometry.intersection(iberia_bbox)
        if not g.is_empty:
            peninsula_geoms.append(g)
peninsula = unary_union(peninsula_geoms)

print(f"  Iberia bbox area      : {iberia_bbox.area:.2f} sq deg")
print(f"  Land in bbox area     : {land_in_bbox.area:.2f} sq deg")
print(f"  Peninsula land area   : {peninsula.area:.2f} sq deg "
      f"(Spain+Portugal+Andorra+Gibraltar within bbox)")

# Per-Nside on-peninsula mask using centroid containment.
peninsula_mask: dict[int, np.ndarray] = {}
for n in NSIDES:
    lons = IBERIA_LON[n]
    lats = IBERIA_LAT[n]
    mask = np.array([peninsula.contains(Point(float(lo), float(la)))
                     for lo, la in zip(lons, lats)])
    peninsula_mask[n] = mask
    n_total = len(mask)
    n_kept = int(mask.sum())
    print(f"  Nside={n:>3}  on-peninsula: {n_kept:>5,}/{n_total:>5,} cells "
          f"({100*n_kept/n_total:5.1f}%)")

test1_rows = []
for s in STRATEGIES:
    for n in NSIDES:
        mask = peninsula_mask[n]
        atl_full = richness[s][n]["atlas"]
        rm_full = richness[s][n]["rangemap_temporal"]
        mis_full = hotspot_misidentified_pct(atl_full, rm_full)
        if mask.sum() == 0:
            mis_land = float("nan")
        else:
            mis_land = hotspot_misidentified_pct(
                atl_full[mask], rm_full[mask],
            )
        test1_rows.append({
            "strategy": s, "nside": n,
            "n_cells_all": int(len(mask)),
            "n_cells_peninsula": int(mask.sum()),
            "misidentified_pct_all_cells": round(mis_full, 2),
            "misidentified_pct_peninsula_only": round(mis_land, 2),
            "delta_pp": round(mis_full - mis_land, 2),
        })

test1_df = pd.DataFrame(test1_rows)
print("\n  --- Land-mask sensitivity table ---")
print(test1_df.to_string(index=False))


# %% [markdown]
# ## TEST 2 — Top-K sensitivity sweep
#
# Sweep K ∈ {1, 2, 5, 10, 25}% of cells. If the trend is K-monotone or
# the 5% number is on a statistical cliff (e.g., big jump from 5% to 10%),
# the choice of K is doing work we shouldn't credit to the H&J effect.

# %%
print("\n" + "=" * 64)
print("TEST 2 — Top-K sensitivity sweep")
print("=" * 64)

test2_rows = []
for s in STRATEGIES:
    for n in NSIDES:
        atl = richness[s][n]["atlas"]
        rm = richness[s][n]["rangemap_temporal"]
        for k in HOTSPOT_FRACTIONS:
            mis = hotspot_misidentified_pct(atl, rm, k)
            test2_rows.append({
                "strategy": s, "nside": n, "top_k_fraction": k,
                "misidentified_pct": round(mis, 2),
            })
test2_df = pd.DataFrame(test2_rows)
print("\n  At Nside 256 (H&J's 0.25° equivalent):")
piv = test2_df[test2_df["nside"] == 256].pivot(
    index="strategy", columns="top_k_fraction", values="misidentified_pct",
)
print(piv.to_string())


# %% [markdown]
# ## TEST 3 — Per-species hull drift
#
# For each species with both pre-2000 and post-2000 convex hulls, compute
# the Jaccard distance `1 - intersection.area / union.area`. If the
# median drift is small (< 0.2), pre-2000 and post-2000 ranges are
# essentially the same shape and the temporal-axis claim holds. If large
# (> 0.5), ranges have moved materially and my earlier claim was wrong.
#
# Post-2000 convex hulls are computed in the streaming pass below
# (Tests 4 + 5 share that re-stream). This test runs after the stream.


# %% [markdown]
# ## TESTS 4 + 5 setup — single re-stream of each GBIF zip
#
# Per chunk, modern subset only:
#
# - Tests 4 (observer-effort): per-(cell, Nside) accumulate record count.
# - Tests 3 + 5 (concave hull + drift): per-species accumulate (lon, lat).
#
# After all chunks: build post-2000 convex hull AND concave hull per
# species; compute observer-effort correlation; compute hull-based
# rangemap richness for both polygon types per Nside.

# %%
print("\n" + "=" * 64)
print("RE-STREAM for Tests 3, 4, 5  (post-2000 records only)")
print("=" * 64)

# Pre-load pre-2000 hulls per strategy (for Test 3 drift).
pre2000_hulls: dict[str, dict[str, Polygon]] = {s: {} for s in STRATEGIES}
for _, row in eoo_df.iterrows():
    pre2000_hulls[row["strategy"]][row["species"]] = shp_wkt.loads(row["wkt"])

test4_rows = []        # per-cell record count vs species count, per (s, n)
test5_rows = []        # misid: convex vs concave at post-2000
test3_rows = []        # per-species pre-vs-post Jaccard
post2000_hulls_convex: dict[str, dict[str, Polygon]] = {s: {} for s in STRATEGIES}
post2000_hulls_concave: dict[str, dict[str, Polygon]] = {s: {} for s in STRATEGIES}

for s in STRATEGIES:
    print(f"\n  --- Re-streaming {s} ---")
    # Per-cell record count accumulators per Nside.
    record_counts: dict[int, dict[int, int]] = {n: {} for n in NSIDES}
    # Per-species (lon, lat) chunks (post-2000).
    points_modern: dict[str, list[np.ndarray]] = {}
    n_modern = 0
    for ci, chunk in enumerate(iter_gbif_chunks(STRATEGY_ZIPS[s]), start=1):
        years = chunk["year"].astype(int).values
        m = chunk.loc[years >= YEAR_SPLIT]
        if len(m) == 0:
            continue
        n_modern += len(m)
        lons = m["decimalLongitude"].astype(float).values
        lats = m["decimalLatitude"].astype(float).values
        # Test 4: per-Nside per-cell record count.
        for n in NSIDES:
            cells = hp_nested.lonlat_to_healpix(
                lons, lats, DEPTHS[n], ELLIPSOID,
            ).astype(np.int64)
            uniq, counts = np.unique(cells, return_counts=True)
            d = record_counts[n]
            for c, k in zip(uniq, counts):
                d[int(c)] = d.get(int(c), 0) + int(k)
        # Tests 3 + 5: per-species accumulation.
        for sp, grp in m.groupby("species", sort=False):
            pts = (grp[["decimalLongitude", "decimalLatitude"]]
                   .astype(float).values)
            points_modern.setdefault(sp, []).append(pts)
        if ci % 5 == 0:
            print(f"    chunk {ci:>3}: cumulative post-2000 = {n_modern:>11,}")
    print(f"    [{s}] stream done: {n_modern:,} post-2000 records, "
          f"{len(points_modern)} species")

    # --- Test 4: per-cell record-count vs atlas (species) richness ---
    print(f"    [{s}] computing observer-effort correlation per Nside...")
    for n in NSIDES:
        cells_arr = richness[s][n]["cells"]
        atl = richness[s][n]["atlas"]
        recs = align_counts_to_cells(record_counts[n], cells_arr)
        # Only correlate where atlas has records (non-empty cells).
        mask = atl > 0
        if mask.sum() >= 5:
            r = float(np.corrcoef(recs[mask], atl[mask])[0, 1])
        else:
            r = float("nan")
        # Log-log version, since both are highly skewed.
        if mask.sum() >= 5:
            r_log = float(np.corrcoef(
                np.log1p(recs[mask]), np.log1p(atl[mask]),
            )[0, 1])
        else:
            r_log = float("nan")
        test4_rows.append({
            "strategy": s, "nside": n,
            "n_cells_atlas_nonzero": int(mask.sum()),
            "pearson_r_records_vs_species": round(r, 4),
            "pearson_r_log_records_vs_log_species": round(r_log, 4),
        })

    # --- Build post-2000 convex + concave hulls per species ---
    print(f"    [{s}] building post-2000 convex + concave hulls...")
    for i, (sp, parts) in enumerate(points_modern.items(), start=1):
        pts = np.vstack(parts) if len(parts) > 1 else parts[0]
        post2000_hulls_convex[s][sp] = convex_hull(pts)
        post2000_hulls_concave[s][sp] = concave_hull_safe(
            pts, ratio=CONCAVE_RATIO,
        )
        if i % 100 == 0 or i == len(points_modern):
            print(f"      built {i}/{len(points_modern)} hulls")
    points_modern.clear()

    # --- Test 3: pre vs post hull Jaccard distance ---
    print(f"    [{s}] computing pre-vs-post hull drift...")
    pre = pre2000_hulls[s]
    post = post2000_hulls_convex[s]
    shared = set(pre.keys()) & set(post.keys())
    for sp in shared:
        a = pre[sp]
        b = post[sp]
        try:
            u = a.union(b).area
            i_ = a.intersection(b).area
            jacc = 1.0 - (i_ / u) if u > 0 else 0.0
        except Exception:
            jacc = float("nan")
        test3_rows.append({
            "strategy": s, "species": sp,
            "pre_area_sqdeg": float(a.area),
            "post_area_sqdeg": float(b.area),
            "jaccard_distance": round(jacc, 4),
        })

    # --- Test 5: per-Nside rangemap from concave (vs convex) hulls ---
    print(f"    [{s}] computing concave-hull rangemap per Nside...")
    for n in NSIDES:
        iberian_arr = IBERIA_PIX[n]
        counts_concave = hulls_to_per_cell_count(
            post2000_hulls_concave[s], n, iberian_arr,
        )
        rm_concave = align_counts_to_cells(
            counts_concave, richness[s][n]["cells"],
        )
        counts_convex = hulls_to_per_cell_count(
            post2000_hulls_convex[s], n, iberian_arr,
        )
        rm_convex_post = align_counts_to_cells(
            counts_convex, richness[s][n]["cells"],
        )
        atl = richness[s][n]["atlas"]
        rm_convex_pre = richness[s][n]["rangemap_temporal"]
        mis_concave = hotspot_misidentified_pct(atl, rm_concave)
        mis_convex_post = hotspot_misidentified_pct(atl, rm_convex_post)
        mis_convex_pre = hotspot_misidentified_pct(atl, rm_convex_pre)
        test5_rows.append({
            "strategy": s, "nside": n,
            "mean_rm_convex_pre2000": round(float(rm_convex_pre.mean()), 2),
            "mean_rm_convex_post2000": round(float(rm_convex_post.mean()), 2),
            "mean_rm_concave_post2000": round(float(rm_concave.mean()), 2),
            "misid_convex_pre2000": round(mis_convex_pre, 2),
            "misid_convex_post2000": round(mis_convex_post, 2),
            "misid_concave_post2000": round(mis_concave, 2),
            "delta_pp_concave_minus_convex_post":
                round(mis_concave - mis_convex_post, 2),
        })


test3_df = pd.DataFrame(test3_rows)
test4_df = pd.DataFrame(test4_rows)
test5_df = pd.DataFrame(test5_rows)


# %% [markdown]
# ## Print summary tables

# %%
print("\n" + "=" * 64)
print("TEST 3 — Per-species hull drift  (Jaccard distance pre vs post)")
print("=" * 64)
for s in STRATEGIES:
    sub = test3_df[test3_df["strategy"] == s]
    if len(sub) == 0:
        continue
    jd = sub["jaccard_distance"].dropna().values
    print(f"  {s}: n_species={len(jd)}  "
          f"median={np.median(jd):.3f}  mean={jd.mean():.3f}  "
          f"q25={np.percentile(jd, 25):.3f}  q75={np.percentile(jd, 75):.3f}  "
          f"frac>0.5={(jd > 0.5).mean():.2%}  "
          f"frac>0.3={(jd > 0.3).mean():.2%}")

print("\n" + "=" * 64)
print("TEST 4 — Atlas (species count) vs observer effort (record count) correlation")
print("=" * 64)
print(test4_df.to_string(index=False))

print("\n" + "=" * 64)
print("TEST 5 — Concave hull vs convex hull (post-2000)")
print("=" * 64)
print(test5_df.to_string(index=False))


# %% [markdown]
# ## Figures

# %%
# --- Figure 1: land mask sensitivity ---
fig1, ax = plt.subplots(figsize=(10, 5.5))
width = 0.35
xs = np.arange(len(NSIDES))
for i, s in enumerate(STRATEGIES):
    sub = test1_df[test1_df["strategy"] == s].sort_values("nside")
    ax.bar(xs + (i - 0.5) * width,
           sub["misidentified_pct_all_cells"].values,
           width=width * 0.45,
           color=STRATEGY_COLORS[s], alpha=0.9,
           label=f"{s} — all Iberian-bbox cells")
    ax.bar(xs + (i - 0.5) * width + width * 0.45,
           sub["misidentified_pct_peninsula_only"].values,
           width=width * 0.45,
           color=STRATEGY_COLORS[s], alpha=0.45,
           hatch="//",
           label=f"{s} — peninsula land cells only")
ax.set_xticks(xs)
ax.set_xticklabels(NSIDES)
ax.set_xlabel("HEALPix Nside")
ax.set_ylabel("Hotspot misidentification (%)")
ax.set_title("Test 1 — Land mask sensitivity\n"
             "all Iberian-bbox cells (solid) vs peninsula-only (hatched)")
# Place legend below the plot — no internal quadrant is bar-free
# (allbor is at 100% on the left, all bars 90%+ on the right).
ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.12),
          fontsize=8, ncol=4, framealpha=0.92)
ax.set_ylim(0, 105)
fig1.tight_layout()
land_fig = FIGURES_DIR / "verif_land_mask.png"
fig1.savefig(land_fig, dpi=150, bbox_inches="tight")
fig1.savefig(land_fig.with_suffix(".pdf"), bbox_inches="tight")
plt.show()
print(f"\nsaved {land_fig}")


# --- Figure 2: top-K sensitivity ---
fig2, axes = plt.subplots(1, 2, figsize=(14, 4.5), sharey=True)
for ax, s in zip(axes, STRATEGIES):
    sub = test2_df[test2_df["strategy"] == s]
    for n in NSIDES:
        sub_n = sub[sub["nside"] == n].sort_values("top_k_fraction")
        ax.plot(sub_n["top_k_fraction"] * 100,
                sub_n["misidentified_pct"], marker="o",
                lw=1.5, label=f"Nside={n}")
    ax.set_xscale("log")
    ax.set_xlabel("Top-K hotspot fraction (%)")
    ax.set_title(f"{s} — top-K sensitivity")
    ax.axvline(5.0, color="black", linestyle=":", alpha=0.5,
               label="H&J 5%")
    ax.legend(loc="lower left", fontsize=8, ncol=2)
    ax.set_ylim(0, 105)
axes[0].set_ylabel("Misidentification (%)")
fig2.tight_layout()
topk_fig = FIGURES_DIR / "verif_topK_sensitivity.png"
fig2.savefig(topk_fig, dpi=150, bbox_inches="tight")
fig2.savefig(topk_fig.with_suffix(".pdf"), bbox_inches="tight")
plt.show()
print(f"saved {topk_fig}")


# --- Figure 3: per-species drift histogram ---
fig3, axes = plt.subplots(1, 2, figsize=(12, 4.5), sharey=False)
for ax, s in zip(axes, STRATEGIES):
    sub = test3_df[test3_df["strategy"] == s]
    if len(sub) == 0:
        continue
    jd = sub["jaccard_distance"].dropna().values
    ax.hist(jd, bins=30, color=STRATEGY_COLORS[s], alpha=0.7,
            edgecolor="white", lw=0.5)
    ax.axvline(np.median(jd), color="black", linestyle="--", lw=1.5,
               label=f"median = {np.median(jd):.2f}")
    ax.set_xlabel("Jaccard distance (pre-2000 hull vs post-2000 hull)")
    ax.set_ylabel("Number of species")
    ax.set_title(f"{s} — per-species hull drift  (n={len(jd)})")
    ax.legend(loc="upper right", fontsize=9)
fig3.tight_layout()
drift_fig = FIGURES_DIR / "verif_species_drift.png"
fig3.savefig(drift_fig, dpi=150, bbox_inches="tight")
fig3.savefig(drift_fig.with_suffix(".pdf"), bbox_inches="tight")
plt.show()
print(f"saved {drift_fig}")


# --- Figure 4: atlas vs observer-effort correlation ---
fig4, ax = plt.subplots(figsize=(10, 4.5))
for s in STRATEGIES:
    sub = test4_df[test4_df["strategy"] == s].sort_values("nside")
    ax.plot(sub["nside"], sub["pearson_r_records_vs_species"],
            marker="o", lw=2,
            color=STRATEGY_COLORS[s],
            label=f"{s} — Pearson r (raw)")
    ax.plot(sub["nside"], sub["pearson_r_log_records_vs_log_species"],
            marker="s", lw=2, linestyle="--",
            color=STRATEGY_COLORS[s], alpha=0.6,
            label=f"{s} — Pearson r (log–log)")
ax.set_xscale("log", base=2)
ax.set_xticks(NSIDES)
ax.set_xticklabels(NSIDES)
ax.set_xlabel("HEALPix Nside / log scale")
ax.set_ylabel("Pearson r")
ax.set_ylim(0, 1.05)
ax.set_title("Test 4 — Atlas (species count) vs observer effort (record count)")
ax.axhline(0.9, color="red", linestyle=":", alpha=0.5,
           label="r = 0.9 (concerning threshold)")
ax.legend(loc="lower right", fontsize=8)
fig4.tight_layout()
obs_fig = FIGURES_DIR / "verif_observer_effort.png"
fig4.savefig(obs_fig, dpi=150, bbox_inches="tight")
fig4.savefig(obs_fig.with_suffix(".pdf"), bbox_inches="tight")
plt.show()
print(f"saved {obs_fig}")


# --- Figure 5: concave vs convex hull ---
fig5, ax = plt.subplots(figsize=(11, 6))
for s in STRATEGIES:
    sub = test5_df[test5_df["strategy"] == s].sort_values("nside")
    ax.plot(sub["nside"], sub["misid_convex_pre2000"],
            marker="o", lw=2.2, color=STRATEGY_COLORS[s],
            label=f"{s} — convex hull pre-2000 (canonical)")
    ax.plot(sub["nside"], sub["misid_convex_post2000"],
            marker="s", lw=2.2, linestyle="--",
            color=STRATEGY_COLORS[s], alpha=0.7,
            label=f"{s} — convex hull post-2000 (same-era)")
    ax.plot(sub["nside"], sub["misid_concave_post2000"],
            marker="^", lw=2.2, linestyle=":",
            color=STRATEGY_COLORS[s], alpha=0.85,
            label=f"{s} — concave hull post-2000 (ratio={CONCAVE_RATIO})")
hj_table2 = {
    "Australia": {0.25: 47.8, 0.5: 44.0, 1.0: 40.0, 2.0: 20.0, 4.0: 5.0},
    "Southern Africa": {0.25: 68.6, 0.5: 63.0, 1.0: 22.2, 2.0: 15.0, 4.0: 5.0},
}
hj_nside_for_deg = {0.25: 256, 0.5: 128, 1.0: 64, 2.0: 32, 4.0: 16}
hj_colors = {"Australia": "#ff7f0e", "Southern Africa": "#2ca02c"}
hj_markers = {"Australia": "v", "Southern Africa": "^"}
for region, table in hj_table2.items():
    xs_ = [hj_nside_for_deg[d] for d in table.keys()]
    ys_ = list(table.values())
    ax.plot(xs_, ys_, marker=hj_markers[region], markersize=8, lw=1.2,
            linestyle=":", color=hj_colors[region], alpha=0.7,
            label=f"H&J 2007 {region}")
ax.set_xscale("log", base=2)
ax.set_xticks(NSIDES)
ax.set_xticklabels(NSIDES)
ax.set_xlabel("HEALPix Nside / log scale")
ax.set_ylabel("Hotspot misidentification (%)")
ax.set_ylim(0, 100)
ax.set_title("Test 5 — Concave hull substitute  vs  convex hull "
             "(both polygon types from post-2000 GBIF)")
ax.legend(loc="lower right", fontsize=7, ncol=2, framealpha=0.92)
fig5.tight_layout()
concave_fig = FIGURES_DIR / "verif_concave_vs_convex.png"
fig5.savefig(concave_fig, dpi=150, bbox_inches="tight")
fig5.savefig(concave_fig.with_suffix(".pdf"), bbox_inches="tight")
plt.show()
print(f"saved {concave_fig}")


# %% [markdown]
# ## Save tables

# %%
test1_df.to_parquet(RESULTS_DIR / "verif1_land_mask.parquet", index=False)
test2_df.to_parquet(RESULTS_DIR / "verif2_topK.parquet", index=False)
test3_df.to_parquet(RESULTS_DIR / "verif3_drift.parquet", index=False)
test4_df.to_parquet(RESULTS_DIR / "verif4_observer_effort.parquet", index=False)
test5_df.to_parquet(RESULTS_DIR / "verif5_concave.parquet", index=False)
print("\nsaved verif*.parquet under results/")


# %% [markdown]
# ## Decomposition update at Nside 256 (after verifications)
#
# The single most important number: what's the misidentification at H&J's
# 0.25° equivalent under each verification variant?

# %%
print("\n" + "=" * 64)
print("UPDATED DECOMPOSITION AT NSIDE 256")
print("=" * 64)

for s in STRATEGIES:
    t1 = test1_df[(test1_df["strategy"] == s) & (test1_df["nside"] == 256)].iloc[0]
    t5 = test5_df[(test5_df["strategy"] == s) & (test5_df["nside"] == 256)].iloc[0]
    t3 = test3_df[test3_df["strategy"] == s]
    drift_med = float(t3["jaccard_distance"].median()) if len(t3) else float("nan")
    t4 = test4_df[(test4_df["strategy"] == s) & (test4_df["nside"] == 256)].iloc[0]
    print(f"\n  {s}:")
    print(f"    canonical (convex pre, all cells)        : "
          f"{t1['misidentified_pct_all_cells']:5.1f} %")
    print(f"    peninsula-only mask                       : "
          f"{t1['misidentified_pct_peninsula_only']:5.1f} %  "
          f"(Δ = {t1['delta_pp']:+5.1f} pp)")
    print(f"    convex hull, post-2000 (same-era)        : "
          f"{t5['misid_convex_post2000']:5.1f} %")
    print(f"    concave hull, post-2000 (tighter polygon): "
          f"{t5['misid_concave_post2000']:5.1f} %  "
          f"(Δ vs convex post = {t5['delta_pp_concave_minus_convex_post']:+5.1f} pp)")
    print(f"    median per-species hull drift (Jaccard)  : "
          f"{drift_med:.3f}")
    print(f"    atlas vs observer-effort Pearson r (log) : "
          f"{t4['pearson_r_log_records_vs_log_species']:.3f}")

print(f"\n  H&J 2007 Australia                         :  47.8 %")
print(f"  H&J 2007 Southern Africa                   :  68.6 %")
