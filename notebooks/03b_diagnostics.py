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
# # 03b — Diagnostics (replication-gap decomposition vs H&J 2007)
#
# Our main pipeline (03_analysis) reports per-Nside hotspot misidentification
# of **89.9 %** (museum) / **97.8 %** (allbor) at H&J's 0.25° equivalent
# (Nside 256, ~25 km). H&J 2007 reported **47.8 %** (Australia) / **68.6 %**
# (southern Africa) at the same scale. This notebook decomposes the gap.
#
# Two substitutions are confounded in the canonical pipeline:
#
# 1. **Hull-as-rangemap** — H&J had expert BirdLife polygons (which exclude
#    unsuitable habitat *inside* the convex envelope); we use convex hulls
#    of GBIF occurrences, which systematically over-predict presence.
# 2. **Temporal split** — H&J's atlas and rangemap were contemporaneous;
#    our "rangemap" is pre-2000 GBIF, our "atlas" is post-2000 GBIF. 25 + yr
#    of range shifts (climate, land-use) conflate with the method effect.
#
# Three free diagnostics (all using data already on disk):
#
# - **Diag 1 — Hull area sanity.** Distribution of per-species hull areas
#   from `species_eoo_polygons.parquet`, compared to the Iberia bbox.
# - **Diag 2 — Minimum-points sensitivity.** Filter hulls by n_points
#   threshold k ∈ {1, 5, 10, 20}, recompute rangemap richness + hotspot
#   misidentification. Tests whether few-occurrence species drive the bias.
# - **Diag 3 — Same-era hulls.** Re-stream the GBIF zip, build hulls from
#   *post-2000* occurrences (not pre-2000), recompute rangemap richness +
#   hotspot misidentification. Removes the temporal confound while keeping
#   the hull substitute. The residual gap = pure hull-as-rangemap effect.
#
# Outputs:
#
# - `figures/scale_dependence_decomposition.png` — 4 curves per strategy
#   (temporal + same-era) overlaid on H&J references.
# - `figures/hull_areas_diagnostic.png` — per-strategy hull-area histogram.
# - `results/diag2_min_points_sensitivity.parquet`
# - `results/diag3_same_era.parquet`
# - `results/diag3_post2000_eoo_polygons.parquet`
#
# The user reads these + writes `docs/replication-gap-decomposition.md`
# from the numbers.

# %%
import json
import zipfile
from collections.abc import Iterator
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import xarray as xr
from healpix_geo import nested as hp_nested
from shapely import wkt as shp_wkt
from shapely.geometry import MultiPoint, Polygon

plt.style.use("seaborn-v0_8-whitegrid")

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

# Iberia bbox approximate area: 14° lon × 9° lat at 40°N
# 1° lat ≈ 111 km, 1° lon at 40°N ≈ 85 km → bbox ≈ 1.19 M km²
# Iberia mainland actual area ≈ 580,000 km² (well-known)
IBERIA_BBOX_SQDEG = (IBERIA_LON_MAX - IBERIA_LON_MIN) * (IBERIA_LAT_MAX - IBERIA_LAT_MIN)
SQDEG_TO_KM2_AT_40N = 111.0 * 85.0  # rough conversion for narrative only

ROOT = Path("..").resolve()
DATA = ROOT / "data"
GBIF_DIR = DATA / "gbif"
CLEAN_DIR = DATA / "clean"
RESULTS_DIR = ROOT / "results"
FIGURES_DIR = ROOT / "figures"
FIGURES_DIR.mkdir(parents=True, exist_ok=True)
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

STRATEGY_ZIPS = {
    "museum": GBIF_DIR / "birds_iberia_museum.zip",
    "allbor": GBIF_DIR / "birds_iberia_allbor.zip",
}
STRATEGY_RICHNESS_NC = {
    s: CLEAN_DIR / f"richness_{s}.nc" for s in STRATEGIES
}
EOO_PARQUET = CLEAN_DIR / "species_eoo_polygons.parquet"

HOTSPOT_FRACTION = 0.05  # H&J 2007
MIN_POINTS_LEVELS = [1, 5, 10, 20]
GBIF_CHUNKSIZE = 1_000_000

STRATEGY_COLORS = {"museum": "#1f77b4", "allbor": "#d62728"}

print(f"IBERIA_BBOX_SQDEG = {IBERIA_BBOX_SQDEG:.1f} sq deg "
      f"(~{IBERIA_BBOX_SQDEG * SQDEG_TO_KM2_AT_40N / 1e6:.2f} M km²)")


# %% [markdown]
# ## Helpers (copied from 02_data_clean + 03_analysis)
#
# Self-contained so we don't need to import from the jupytext notebooks
# (which would execute their top-level code).

# %%
def iberian_pix(depth: int, nside: int):
    pix_all = np.arange(12 * nside * nside, dtype=np.uint64)
    lon, lat = hp_nested.healpix_to_lonlat(pix_all, depth, ELLIPSOID)
    lon = np.where(lon > 180.0, lon - 360.0, lon)
    mask = (
        (lon >= IBERIA_LON_MIN) & (lon <= IBERIA_LON_MAX)
        & (lat >= IBERIA_LAT_MIN) & (lat <= IBERIA_LAT_MAX)
    )
    return pix_all[mask].astype(np.int64)


def species_hull(points: np.ndarray) -> Polygon:
    if len(points) >= 3:
        hull = MultiPoint(points).convex_hull
        if hull.geom_type != "Polygon":
            hull = hull.buffer(0.05)
    elif len(points) == 2:
        from shapely.geometry import LineString
        hull = LineString(points).buffer(0.1)
    else:
        from shapely.geometry import Point
        hull = Point(points[0]).buffer(0.2)
    return hull


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
    """Per-cell count of species whose hull covers the cell."""
    depth = DEPTHS[nside]
    counts: dict[int, int] = {}
    for hull in species_hulls.values():
        cells = hull_to_cells(hull, depth)
        cells = cells[np.isin(cells, iberian_arr)]
        for c in cells:
            counts[int(c)] = counts.get(int(c), 0) + 1
    return counts


def align_counts_to_cells(counts: dict[int, int],
                          cells_arr: np.ndarray) -> np.ndarray:
    """Map a {cell_id: count} dict onto the canonical Iberian cell ordering."""
    out = np.zeros(len(cells_arr), dtype=np.int64)
    cell_to_idx = {int(c): i for i, c in enumerate(cells_arr)}
    for cell, n in counts.items():
        idx = cell_to_idx.get(int(cell))
        if idx is not None:
            out[idx] = int(n)
    return out


def top_k_set(richness: np.ndarray, fraction: float) -> set[int]:
    n = len(richness)
    if n == 0:
        return set()
    top_k = max(1, int(np.ceil(fraction * n)))
    idx = np.argpartition(richness, -top_k)[-top_k:]
    return set(int(i) for i in idx)


def hotspot_misidentified_pct(atlas: np.ndarray,
                              rangemap: np.ndarray,
                              fraction: float = HOTSPOT_FRACTION) -> float:
    """Symmetric non-overlap of top-`fraction` hotspot sets (H&J-style)."""
    atl = top_k_set(atlas, fraction)
    rm = top_k_set(rangemap, fraction)
    union = atl | rm
    inter = atl & rm
    if not union:
        return 0.0
    return (len(union) - len(inter)) / len(union) * 100.0


def iter_gbif_chunks(zip_path: Path,
                     chunksize: int = GBIF_CHUNKSIZE) -> Iterator[pd.DataFrame]:
    """Stream a GBIF SIMPLE_CSV zip in NA-dropped, bbox-filtered chunks."""
    if not zip_path.exists():
        raise FileNotFoundError(f"Missing GBIF zip: {zip_path}")
    with zipfile.ZipFile(zip_path) as zf:
        candidates = [n for n in zf.namelist() if n.endswith(".csv")]
        if not candidates:
            raise RuntimeError(f"No CSV inside {zip_path}")
        with zf.open(candidates[0]) as src:
            reader = pd.read_csv(
                src, sep="\t",
                usecols=lambda c: c in {
                    "gbifID", "species", "decimalLatitude",
                    "decimalLongitude", "year", "basisOfRecord",
                },
                dtype={"gbifID": "Int64", "year": "Int64"},
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
#
# The canonical pipeline outputs from 02_data_clean + 03_analysis: per-Nside
# atlas + temporal-rangemap richness arrays, and pre-2000 hull WKTs.

# %%
eoo_df = pd.read_parquet(EOO_PARQUET)
print(f"Loaded EOO polygons: {len(eoo_df)} rows  "
      f"{eoo_df['strategy'].value_counts().to_dict()}")

IBERIA_PIX = {n: iberian_pix(DEPTHS[n], n) for n in NSIDES}

# Per-strategy per-Nside richness arrays (canonical pipeline output).
richness: dict[str, dict[int, dict[str, np.ndarray]]] = {
    s: {} for s in STRATEGIES
}
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
print(f"Loaded per-Nside richness arrays for {len(STRATEGIES)} strategies × "
      f"{len(NSIDES)} Nsides.")


# %% [markdown]
# ## Diagnostic 1 — Hull-area sanity
#
# How big are the per-species pre-2000 hulls? If many of them exceed the
# Iberia bbox itself, the hull substitute is fundamentally broken; if they
# are bimodal (few-point species → tiny buffered points; many-point species
# → giant hulls), the bias is structural.

# %%
print("\n" + "=" * 64)
print("DIAGNOSTIC 1 — Hull-area sanity (pre-2000 hulls)")
print("=" * 64)

diag1_rows = []
for s in STRATEGIES:
    sub = eoo_df[eoo_df["strategy"] == s]
    areas = sub["hull_area_sqdeg"].values
    n_huge = int((areas > IBERIA_BBOX_SQDEG / 2).sum())
    n_iberia_plus = int((areas > IBERIA_BBOX_SQDEG).sum())
    n_tiny = int((areas < 0.5).sum())  # <0.5 sq deg ~ <4000 km²
    row = {
        "strategy": s,
        "n_species": len(sub),
        "median_sqdeg": float(np.median(areas)),
        "mean_sqdeg": float(areas.mean()),
        "p90_sqdeg": float(np.percentile(areas, 90)),
        "max_sqdeg": float(areas.max()),
        "n_huge_gt_halfbbox": n_huge,
        "n_exceeds_bbox": n_iberia_plus,
        "n_tiny_lt_0p5sqdeg": n_tiny,
    }
    diag1_rows.append(row)
    print(f"\n  {s}: {len(sub)} species with pre-2000 hulls")
    print(f"    median area : {row['median_sqdeg']:6.2f} sq deg  "
          f"(~{row['median_sqdeg'] * SQDEG_TO_KM2_AT_40N:,.0f} km²)")
    print(f"    mean area   : {row['mean_sqdeg']:6.2f} sq deg")
    print(f"    p90 area    : {row['p90_sqdeg']:6.2f} sq deg")
    print(f"    max area    : {row['max_sqdeg']:6.2f} sq deg  "
          f"(Iberia bbox = {IBERIA_BBOX_SQDEG:.1f} sq deg)")
    print(f"    n hulls > 0.5 × Iberia bbox area: {n_huge}/{len(sub)} "
          f"({100*n_huge/len(sub):.1f}%)")
    print(f"    n hulls > full Iberia bbox     : {n_iberia_plus}/{len(sub)} "
          f"({100*n_iberia_plus/len(sub):.1f}%)")
    print(f"    n tiny (<0.5 sq deg, n_points small): "
          f"{n_tiny}/{len(sub)} ({100*n_tiny/len(sub):.1f}%)")

diag1_df = pd.DataFrame(diag1_rows)

# Histogram per strategy.
fig1, axes = plt.subplots(1, 2, figsize=(12, 4.5), sharey=False)
for ax, s in zip(axes, STRATEGIES):
    sub = eoo_df[eoo_df["strategy"] == s]
    ax.hist(sub["hull_area_sqdeg"].values, bins=40,
            color=STRATEGY_COLORS[s], alpha=0.75, edgecolor="white", lw=0.5)
    ax.axvline(IBERIA_BBOX_SQDEG, color="red", linestyle="--", lw=1.5,
               label=f"Iberia bbox = {IBERIA_BBOX_SQDEG:.0f} sq deg")
    ax.axvline(IBERIA_BBOX_SQDEG / 2, color="orange", linestyle=":", lw=1.2,
               label=f"½ Iberia bbox")
    ax.set_xlabel("Pre-2000 hull area (sq deg)")
    ax.set_ylabel("Number of species")
    ax.set_title(f"{s}: per-species hull-area distribution "
                 f"(n={len(sub)} species)")
    ax.legend(loc="upper right", fontsize=8)
fig1.tight_layout()
hull_fig = FIGURES_DIR / "hull_areas_diagnostic.png"
fig1.savefig(hull_fig, dpi=150, bbox_inches="tight")
fig1.savefig(hull_fig.with_suffix(".pdf"), bbox_inches="tight")
plt.show()
print(f"\nsaved {hull_fig}")


# %% [markdown]
# ## Diagnostic 2 — Minimum-points sensitivity
#
# Filter pre-2000 hulls by `n_points ≥ k` for k ∈ {1, 5, 10, 20}. Re-derive
# rangemap richness per cell from the filtered hull set, recompute hotspot
# misidentification %. If the gap closes when small-sample hulls are
# excluded, few-occurrence species are noise; if not, the bias is in
# well-sampled species too.

# %%
print("\n" + "=" * 64)
print("DIAGNOSTIC 2 — Minimum-points sensitivity (pre-2000 hulls filtered)")
print("=" * 64)

diag2_rows = []
for s in STRATEGIES:
    sub_all = eoo_df[eoo_df["strategy"] == s].copy()
    print(f"\n  --- {s} (max {len(sub_all)} pre-2000 hulls) ---")
    for mp in MIN_POINTS_LEVELS:
        sub = sub_all[sub_all["n_points"] >= mp]
        if len(sub) == 0:
            continue
        species_hulls = {
            row["species"]: shp_wkt.loads(row["wkt"])
            for _, row in sub.iterrows()
        }
        for n in NSIDES:
            counts = hulls_to_per_cell_count(
                species_hulls, n, IBERIA_PIX[n],
            )
            rm = align_counts_to_cells(counts, richness[s][n]["cells"])
            atl = richness[s][n]["atlas"]
            mis = hotspot_misidentified_pct(atl, rm)
            diag2_rows.append({
                "strategy": s, "nside": n, "min_pts": mp,
                "n_species_kept": len(sub),
                "mean_rangemap_richness": round(float(rm.mean()), 2),
                "misidentified_pct": round(mis, 2),
            })
        print(f"    min_pts={mp:>2}  n_species={len(sub):>4}  "
              + "  ".join(
                  f"Nside={r['nside']:>3}:{r['misidentified_pct']:5.1f}%"
                  for r in diag2_rows[-len(NSIDES):]
              ))

diag2_df = pd.DataFrame(diag2_rows)
diag2_path = RESULTS_DIR / "diag2_min_points_sensitivity.parquet"
diag2_df.to_parquet(diag2_path, index=False)
print(f"\nsaved {diag2_path}")


# %% [markdown]
# ## Diagnostic 3 — Same-era hulls (re-stream)
#
# Re-stream each GBIF zip, accumulate per-species **post-2000** point sets,
# build post-2000 convex hulls, recompute rangemap richness per Nside.
# Compare hotspot misidentification vs the canonical (pre-2000) rangemap.
# This isolates the *hull-as-rangemap* effect from the *temporal-axis*
# effect: same-era values represent the misidentification with the temporal
# confound removed.

# %%
print("\n" + "=" * 64)
print("DIAGNOSTIC 3 — Same-era hulls (re-stream zip, post-2000 hulls)")
print("=" * 64)

diag3_rows = []
same_era_eoo_rows = []
same_era_hulls: dict[str, dict[str, Polygon]] = {}

for s in STRATEGIES:
    print(f"\n  --- Re-streaming {s} for post-2000 hulls ---")
    points_modern: dict[str, list[np.ndarray]] = {}
    n_modern = 0
    n_chunks = 0
    for ci, chunk in enumerate(iter_gbif_chunks(STRATEGY_ZIPS[s]), start=1):
        n_chunks += 1
        years = chunk["year"].astype(int).values
        is_modern = years >= YEAR_SPLIT
        m = chunk.loc[is_modern]
        if len(m) == 0:
            continue
        n_modern += len(m)
        for sp, grp in m.groupby("species", sort=False):
            pts = (grp[["decimalLongitude", "decimalLatitude"]]
                   .astype(float).values)
            points_modern.setdefault(sp, []).append(pts)
        if ci % 5 == 0:
            print(f"    chunk {ci:>3}: cumulative post-2000 records = "
                  f"{n_modern:>11,}")
    print(f"    [{s}] stream done: {n_chunks} chunks, "
          f"{n_modern:,} post-2000 records, "
          f"{len(points_modern)} species with post-2000 hulls")

    hulls_modern: dict[str, Polygon] = {}
    for sp, parts in points_modern.items():
        pts = np.vstack(parts) if len(parts) > 1 else parts[0]
        hull = species_hull(pts)
        hulls_modern[sp] = hull
        same_era_eoo_rows.append({
            "strategy": s,
            "species": sp,
            "n_points": int(len(pts)),
            "hull_area_sqdeg": float(hull.area),
        })
    same_era_hulls[s] = hulls_modern
    points_modern.clear()  # free per-species point arrays

    print(f"    [{s}] computing same-era rangemap richness per Nside...")
    for n in NSIDES:
        counts = hulls_to_per_cell_count(hulls_modern, n, IBERIA_PIX[n])
        rm_modern = align_counts_to_cells(counts, richness[s][n]["cells"])
        atl = richness[s][n]["atlas"]
        rm_temporal = richness[s][n]["rangemap_temporal"]
        mis_same_era = hotspot_misidentified_pct(atl, rm_modern)
        mis_temporal = hotspot_misidentified_pct(atl, rm_temporal)
        diag3_rows.append({
            "strategy": s,
            "nside": n,
            "mean_rangemap_temporal": round(float(rm_temporal.mean()), 2),
            "mean_rangemap_same_era": round(float(rm_modern.mean()), 2),
            "misidentified_pct_temporal": round(mis_temporal, 2),
            "misidentified_pct_same_era": round(mis_same_era, 2),
            "delta_pp_temporal_minus_same_era":
                round(mis_temporal - mis_same_era, 2),
        })
        print(f"      Nside={n:>3}  "
              f"temporal={mis_temporal:5.1f}%  "
              f"same-era={mis_same_era:5.1f}%  "
              f"Δ={mis_temporal - mis_same_era:+5.1f} pp")

diag3_df = pd.DataFrame(diag3_rows)
diag3_path = RESULTS_DIR / "diag3_same_era.parquet"
diag3_df.to_parquet(diag3_path, index=False)
print(f"\nsaved {diag3_path}")

same_era_eoo_df = pd.DataFrame(same_era_eoo_rows)
same_era_path = RESULTS_DIR / "diag3_post2000_eoo_polygons.parquet"
same_era_eoo_df.to_parquet(same_era_path, index=False)
print(f"saved {same_era_path}")


# %% [markdown]
# ## Composite decomposition figure
#
# Two curves per strategy (temporal + same-era), overlaid with H&J Table 2
# references. The vertical gap between the temporal and same-era lines is
# the temporal-axis effect; the residual gap between same-era and H&J is
# the hull-as-rangemap effect (plus any biogeographic / data-density
# differences).

# %%
fig, ax = plt.subplots(figsize=(11, 6.5))

for s in STRATEGIES:
    sub = diag3_df[diag3_df["strategy"] == s].sort_values("nside")
    ax.plot(sub["nside"], sub["misidentified_pct_temporal"],
            marker="o", markersize=8, lw=2.2,
            color=STRATEGY_COLORS[s],
            label=f"{s}: temporal hull (pre-2000 hull vs post-2000 atlas)")
    ax.plot(sub["nside"], sub["misidentified_pct_same_era"],
            marker="s", markersize=8, lw=2.2, linestyle="--",
            color=STRATEGY_COLORS[s], alpha=0.75,
            label=f"{s}: same-era hull (post-2000 hull vs post-2000 atlas)")

hj_table2 = {
    "Australia": {0.25: 47.8, 0.5: 44.0, 1.0: 40.0, 2.0: 20.0, 4.0: 5.0},
    "Southern Africa": {0.25: 68.6, 0.5: 63.0, 1.0: 22.2, 2.0: 15.0, 4.0: 5.0},
}
hj_nside_for_deg = {0.25: 256, 0.5: 128, 1.0: 64, 2.0: 32, 4.0: 16}
hj_colors = {"Australia": "#ff7f0e", "Southern Africa": "#2ca02c"}
hj_markers = {"Australia": "v", "Southern Africa": "^"}
for region, table in hj_table2.items():
    xs = [hj_nside_for_deg[d] for d in table.keys()]
    ys = list(table.values())
    ax.plot(xs, ys, marker=hj_markers[region], markersize=8, lw=1.2,
            linestyle=":", color=hj_colors[region], alpha=0.7,
            label=f"H&J 2007 {region} (Table 2 reference)")

ax.set_xscale("log", base=2)
ax.set_xticks(NSIDES)
ax.set_xticklabels(NSIDES)
ax.set_xlabel("HEALPix Nside (NESTED)  /  log scale")
ax.set_ylabel("Hotspot misidentification (%)\nsymmetric set non-overlap of top-5%")


def nside_to_km(n):
    return np.sqrt(5.10e8 / (12 * n * n))


def km_to_nside(k):
    return np.sqrt(5.10e8 / (12 * k * k))


sec = ax.secondary_xaxis("top", functions=(nside_to_km, km_to_nside))
sec.set_xlabel("approx. cell side (km)")
ax.set_ylim(0, 100)
ax.set_title(
    "Replication-gap decomposition — temporal vs same-era hull substitute\n"
    "Iberian birds × HEALPix NESTED × two GBIF basis-of-record strategies",
    fontsize=11,
)
ax.legend(loc="lower right", fontsize=8, framealpha=0.92, borderaxespad=0.6)

fig.tight_layout()
decomp_fig = FIGURES_DIR / "scale_dependence_decomposition.png"
fig.savefig(decomp_fig, dpi=150, bbox_inches="tight")
fig.savefig(decomp_fig.with_suffix(".pdf"), bbox_inches="tight")
plt.show()
print(f"\nsaved {decomp_fig}")


# %% [markdown]
# ## Decomposition table at H&J's 0.25° equivalent (Nside 256)

# %%
print("\n" + "=" * 64)
print("DECOMPOSITION AT NSIDE=256 (H&J's 0.25° equivalent, ~25 km cells)")
print("=" * 64)
print(f"\n  H&J 2007 Australia      : 47.8 %  misidentified")
print(f"  H&J 2007 Southern Africa: 68.6 %  misidentified\n")

for s in STRATEGIES:
    sub3 = diag3_df[(diag3_df["strategy"] == s) & (diag3_df["nside"] == 256)]
    if len(sub3) == 0:
        continue
    r3 = sub3.iloc[0]
    print(f"  {s} temporal hull (canonical pipeline) : "
          f"{r3['misidentified_pct_temporal']:5.1f} %")
    print(f"  {s} same-era hull  (temporal confound removed): "
          f"{r3['misidentified_pct_same_era']:5.1f} %  "
          f"(Δ = {r3['delta_pp_temporal_minus_same_era']:+5.1f} pp vs temporal)")
    sub2 = diag2_df[(diag2_df["strategy"] == s) & (diag2_df["nside"] == 256)]
    for _, r2 in sub2.sort_values("min_pts").iterrows():
        print(f"  {s} temporal hull, min_pts ≥ {int(r2['min_pts']):>2}        : "
              f"{r2['misidentified_pct']:5.1f} %  "
              f"(n_species={int(r2['n_species_kept'])})")
    print()


# %% [markdown]
# ## Save the diagnostic summary table

# %%
summary_path = RESULTS_DIR / "diag_summary_nside256.parquet"
rows = []
for s in STRATEGIES:
    r3 = diag3_df[(diag3_df["strategy"] == s)
                  & (diag3_df["nside"] == 256)].iloc[0]
    rows.append({
        "strategy": s,
        "variant": "temporal hull (canonical)",
        "misidentified_pct_at_nside256": r3["misidentified_pct_temporal"],
        "n_species_kept": None,
    })
    rows.append({
        "strategy": s,
        "variant": "same-era hull (post-2000 both axes)",
        "misidentified_pct_at_nside256": r3["misidentified_pct_same_era"],
        "n_species_kept": None,
    })
    for mp in MIN_POINTS_LEVELS:
        r2 = diag2_df[(diag2_df["strategy"] == s)
                      & (diag2_df["nside"] == 256)
                      & (diag2_df["min_pts"] == mp)]
        if len(r2):
            r2 = r2.iloc[0]
            rows.append({
                "strategy": s,
                "variant": f"temporal hull, min_pts ≥ {mp}",
                "misidentified_pct_at_nside256": r2["misidentified_pct"],
                "n_species_kept": int(r2["n_species_kept"]),
            })
summary_df = pd.DataFrame(rows)
summary_df.to_parquet(summary_path, index=False)
print(summary_df.to_string(index=False))
print(f"\nsaved {summary_path}")
