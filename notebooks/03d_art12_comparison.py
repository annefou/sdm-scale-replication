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
# # 03d — Article 12 gold-standard rangemap comparison
#
# The verification notebook (`03c`) decomposed the H&J magnitude gap into
# three mechanisms (hull-as-rangemap, atlas observer-effort, top-K choice)
# that together account for most but not all of the gap. The residual
# ~20 percentage points at Nside 256 remained unattributed — possibly
# real biogeographic / data-density difference between modern Iberia and
# 1990s Australia / southern Africa, or possibly more rangemap-substitute
# bias than concave hull can detect.
#
# This notebook runs the gold-standard test: replace the convex/concave
# hull rangemap with **expert-vetted EU Birds Directive Article 12
# distribution polygons** for Iberian bird species (2013-2018 reporting
# period, 10×10 km grid cells in EPSG:3035, CC-BY 4.0 from the EEA,
# 260 species in Spain + Portugal + Gibraltar).
#
# Because Art-12 covers only a subset of our GBIF species set, the
# comparison is restricted to the **species intersection**: atlas
# richness, convex hull rangemap, and concave hull rangemap are ALL
# recomputed on the matched-subset so the apples-to-apples comparison
# isolates the rangemap-substitute effect cleanly.
#
# Outputs:
#
# - `figures/verif_art12_goldstandard.png` — 4 lines per strategy: atlas
#   alone is meaningless without a rangemap, so we plot convex / concave /
#   Art-12 rangemap variants vs matched atlas, plus H&J references.
# - `results/verif6_art12.parquet` — per-(strategy, Nside, rangemap variant)
#   misidentification.
# - `results/verif6_species_match.parquet` — per-species presence in
#   Art-12 vs our GBIF post-2000 sets.

# %%
import json
import warnings
import zipfile
from collections.abc import Iterator
from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pyogrio
import xarray as xr
from healpix_geo import nested as hp_nested
from shapely import concave_hull
from shapely.geometry import MultiPoint, Point, Polygon

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

HOTSPOT_FRACTION = 0.05
CONCAVE_RATIO = 0.3
CONCAVE_SUBSAMPLE_MAX = 10_000
GBIF_CHUNKSIZE = 1_000_000

# Article 12 dataset (EU Birds Directive reporting, 2013-2018).
# Symlinked into the project from Anne's Downloads; CC-BY 4.0 (EEA).
# If the symlink is missing, download from:
#   https://sdi.eea.europa.eu/data/e2face16-f352-4aff-9e4f-0ad1306f89b5
ART12_GPKG = (Path("..") / "data" / "external" / "art12" /
              "ART12_3035_distribution_data_without_sensitive.gpkg").resolve()
ART12_LAYER = "EU_ART12_birds_distribution_2013_2018_without_sensitive_species"

# Mainland Iberia country codes in Art-12. ES = Spain (mainland + Balearics);
# PT = Portugal (mainland); GIB = Gibraltar. Excludes ESIC (Canaries),
# PTAC (Azores), PTMA (Madeira) which are outside the Iberia bbox.
IBERIA_COUNTRIES = {"ES", "PT", "GIB"}

ROOT = Path("..").resolve()
DATA = ROOT / "data"
GBIF_DIR = DATA / "gbif"
CLEAN_DIR = DATA / "clean"
RESULTS_DIR = ROOT / "results"
FIGURES_DIR = ROOT / "figures"

STRATEGY_ZIPS = {
    s: GBIF_DIR / f"birds_iberia_{s}.zip" for s in STRATEGIES
}
STRATEGY_RICHNESS_NC = {
    s: CLEAN_DIR / f"richness_{s}.nc" for s in STRATEGIES
}

STRATEGY_COLORS = {"museum": "#1f77b4", "allbor": "#d62728"}


# %% [markdown]
# ## Helpers

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
    atl = top_k_set(atlas, fraction)
    rm = top_k_set(rangemap, fraction)
    union = atl | rm
    inter = atl & rm
    if not union:
        return 0.0
    return (len(union) - len(inter)) / len(union) * 100.0


def convex_hull_safe(points: np.ndarray) -> Polygon:
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


def concave_hull_safe(points: np.ndarray, ratio: float = CONCAVE_RATIO) -> Polygon:
    if len(points) < 4:
        return convex_hull_safe(points)
    if len(points) > CONCAVE_SUBSAMPLE_MAX:
        rng = np.random.default_rng(42)
        idx = rng.choice(len(points), size=CONCAVE_SUBSAMPLE_MAX, replace=False)
        points = points[idx]
    try:
        ch = concave_hull(MultiPoint(points), ratio=ratio)
        if ch.geom_type == "Polygon" and not ch.is_empty:
            return ch
    except Exception:
        pass
    return convex_hull_safe(points)


def hull_to_cells(hull: Polygon, depth: int) -> np.ndarray:
    if hull.geom_type == "MultiPolygon":
        all_cells = []
        for p in hull.geoms:
            all_cells.append(hull_to_cells(p, depth))
        if not all_cells:
            return np.empty(0, dtype=np.int64)
        return np.unique(np.concatenate(all_cells))
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
        cells = hull_to_cells(hull, depth)
        cells = cells[np.isin(cells, iberian_arr)]
        for c in cells:
            counts[int(c)] = counts.get(int(c), 0) + 1
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
# ## Load Article 12 Iberian subset
#
# Filter to Iberian-peninsula country codes, reproject EPSG:3035 →
# EPSG:4326 (WGS84 lon/lat), extract centroid of each 10 km cell.

# %%
print("=" * 64)
print("Loading Article 12 Iberian subset")
print("=" * 64)
if not ART12_GPKG.exists():
    raise FileNotFoundError(
        f"Article 12 GPKG missing at {ART12_GPKG}. "
        f"Symlink or copy from BotW download; see notebook header."
    )

# pyogrio is faster than fiona for reading large GPKGs.
art12 = pyogrio.read_dataframe(
    ART12_GPKG,
    layer=ART12_LAYER,
    where=f"country IN ({','.join(repr(c) for c in IBERIA_COUNTRIES)})",
)
print(f"Loaded {len(art12):,} Art-12 cells for Iberian countries")
print(f"  Source CRS: {art12.crs}")
print(f"  Countries  : {art12['country'].value_counts().to_dict()}")
print(f"  Species (Art-12 Iberian breeding set): {art12['speciesnameEU'].nunique()}")

# Reproject to WGS84 lon/lat.
art12_wgs = art12.to_crs("EPSG:4326")
# Use REPRESENTATIVE_POINT not centroid — centroid in lon/lat can be wrong
# for a meters-projected rectangle that becomes a slight trapezium when
# reprojected. representative_point() returns a point guaranteed inside.
art12_wgs["lon"] = art12_wgs.geometry.representative_point().x
art12_wgs["lat"] = art12_wgs.geometry.representative_point().y
print(f"  Lon range  : [{art12_wgs.lon.min():.2f}, {art12_wgs.lon.max():.2f}]")
print(f"  Lat range  : [{art12_wgs.lat.min():.2f}, {art12_wgs.lat.max():.2f}]")


# %% [markdown]
# ## Match Art-12 species against our GBIF post-2000 species sets

# %%
art12_species = set(art12_wgs["speciesnameEU"].dropna().unique().tolist())
print(f"\nArt-12 Iberian species set: {len(art12_species)} species")

# Load our post-2000 species sets from the existing diag3 EOO parquet.
diag3_path = RESULTS_DIR / "diag3_post2000_eoo_polygons.parquet"
post2000_eoo = pd.read_parquet(diag3_path)

post2000_species_by_strategy: dict[str, set[str]] = {}
matched_species_by_strategy: dict[str, set[str]] = {}
for s in STRATEGIES:
    sp_set = set(post2000_eoo[post2000_eoo["strategy"] == s]["species"]
                 .unique().tolist())
    post2000_species_by_strategy[s] = sp_set
    matched_species_by_strategy[s] = sp_set & art12_species
    print(f"  {s}: GBIF post-2000 = {len(sp_set)}, "
          f"matched ∩ Art-12 = {len(matched_species_by_strategy[s])}, "
          f"loss = {len(sp_set) - len(matched_species_by_strategy[s])}")

# Species in Art-12 but NOT in our post-2000 GBIF (interesting: rare or
# poorly observed species that the Directive records but citizen science
# doesn't pick up enough of in post-2000).
art12_only = {
    s: art12_species - post2000_species_by_strategy[s] for s in STRATEGIES
}
for s in STRATEGIES:
    print(f"  {s}: Art-12 ∖ post-2000 = {len(art12_only[s])} species")

species_match_rows = []
for sp in sorted(art12_species | set().union(*post2000_species_by_strategy.values())):
    species_match_rows.append({
        "species": sp,
        "in_art12": sp in art12_species,
        "in_post2000_museum": sp in post2000_species_by_strategy["museum"],
        "in_post2000_allbor": sp in post2000_species_by_strategy["allbor"],
    })
species_match_df = pd.DataFrame(species_match_rows)
species_match_df.to_parquet(
    RESULTS_DIR / "verif6_species_match.parquet", index=False,
)
print(f"\nSpecies-match table saved to {RESULTS_DIR / 'verif6_species_match.parquet'}")


# %% [markdown]
# ## Build Iberian HEALPix cell sets

# %%
IBERIA_PIX = {n: iberian_pix(DEPTHS[n], n) for n in NSIDES}
for n in NSIDES:
    print(f"  Nside={n:>3}: {len(IBERIA_PIX[n]):>5,} Iberian cells")


# %% [markdown]
# ## Per-Nside Art-12 rangemap richness
#
# For each Art-12 cell (10 km grid centre), assign it to a HEALPix
# NESTED cell at each Nside via centroid lookup. Per species, union the
# resulting HEALPix cells; per cell, count species = Art-12 rangemap
# richness.

# %%
print("\n" + "=" * 64)
print("Per-Nside Art-12 rangemap richness")
print("=" * 64)

art12_rangemap: dict[str, dict[int, np.ndarray]] = {s: {} for s in STRATEGIES}
for s in STRATEGIES:
    matched_set = matched_species_by_strategy[s]
    art12_sub = art12_wgs[art12_wgs["speciesnameEU"].isin(matched_set)].copy()
    print(f"\n  {s}: Art-12 matched subset = {len(art12_sub):,} cells, "
          f"{art12_sub['speciesnameEU'].nunique()} species")
    lons = art12_sub["lon"].values.astype(float)
    lats = art12_sub["lat"].values.astype(float)
    species = art12_sub["speciesnameEU"].values
    species_to_id = {sp: i for i, sp in enumerate(
        sorted(matched_set))}
    sid = np.fromiter((species_to_id[s_] for s_ in species),
                      dtype=np.int64, count=len(species))
    for n in NSIDES:
        cells = hp_nested.lonlat_to_healpix(
            lons, lats, DEPTHS[n], ELLIPSOID,
        ).astype(np.int64)
        iberian_arr = IBERIA_PIX[n]
        in_iberia = np.isin(cells, iberian_arr)
        kept_cells = cells[in_iberia]
        kept_sid = sid[in_iberia]
        # Unique (cell, species_id) pairs → count per cell = species per cell.
        pairs = np.column_stack([kept_cells, kept_sid])
        if len(pairs) == 0:
            art12_rangemap[s][n] = np.zeros(len(iberian_arr), dtype=np.int64)
            continue
        pairs_u = np.unique(pairs, axis=0)
        uniq_cells, counts = np.unique(pairs_u[:, 0], return_counts=True)
        rangemap = align_counts_to_cells(
            dict(zip(uniq_cells.tolist(), counts.tolist())),
            iberian_arr,
        )
        art12_rangemap[s][n] = rangemap
        print(f"    Nside={n:>3}: "
              f"{int((rangemap > 0).sum()):>5,} cells with rangemap richness > 0  "
              f"(mean={rangemap.mean():.2f}, max={int(rangemap.max())})")


# %% [markdown]
# ## Re-stream GBIF to compute matched-subset atlas + post-2000 hulls
#
# One pass per zip: for each post-2000 record whose species is in the
# matched subset, (a) increment per-(Nside, cell) atlas richness counter
# (deduplicating species per cell), (b) accumulate (lon, lat) for the
# convex/concave hull rebuild.

# %%
print("\n" + "=" * 64)
print("Re-stream GBIF for matched-subset atlas + hulls")
print("=" * 64)

matched_atlas: dict[str, dict[int, dict[int, set[int]]]] = {
    s: {n: {} for n in NSIDES} for s in STRATEGIES
}
matched_points: dict[str, dict[str, list[np.ndarray]]] = {s: {} for s in STRATEGIES}
matched_species_ids: dict[str, dict[str, int]] = {s: {} for s in STRATEGIES}

for s in STRATEGIES:
    print(f"\n  --- {s} ---")
    matched_set = matched_species_by_strategy[s]
    species_to_id = {sp: i for i, sp in enumerate(sorted(matched_set))}
    matched_species_ids[s] = species_to_id

    n_records_total = 0
    n_records_matched = 0
    for ci, chunk in enumerate(iter_gbif_chunks(STRATEGY_ZIPS[s]), start=1):
        n_records_total += len(chunk)
        years = chunk["year"].astype(int).values
        m = chunk.loc[years >= YEAR_SPLIT]
        if len(m) == 0:
            continue
        # Filter to matched species.
        in_matched = m["species"].isin(matched_set)
        m = m.loc[in_matched]
        if len(m) == 0:
            continue
        n_records_matched += len(m)
        lons = m["decimalLongitude"].astype(float).values
        lats = m["decimalLatitude"].astype(float).values
        species = m["species"].values
        sid = np.fromiter((species_to_id[sp] for sp in species),
                          dtype=np.int64, count=len(species))
        # Atlas per Nside.
        for n in NSIDES:
            cells = hp_nested.lonlat_to_healpix(
                lons, lats, DEPTHS[n], ELLIPSOID,
            ).astype(np.int64)
            pairs = np.unique(np.column_stack([cells, sid]), axis=0)
            d = matched_atlas[s][n]
            for c, sp_id in pairs:
                d.setdefault(int(c), set()).add(int(sp_id))
        # Per-species (lon, lat) accumulation for hulls.
        for sp, grp in m.groupby("species", sort=False):
            pts = (grp[["decimalLongitude", "decimalLatitude"]]
                   .astype(float).values)
            matched_points[s].setdefault(sp, []).append(pts)
        if ci % 5 == 0:
            print(f"    chunk {ci:>3}: total = {n_records_total:>11,}, "
                  f"matched = {n_records_matched:>10,}")
    print(f"    [{s}] stream done: {n_records_total:,} total records, "
          f"{n_records_matched:,} from matched species, "
          f"{len(matched_points[s])} species with points accumulated.")


# %% [markdown]
# ## Build matched-subset convex + concave hulls

# %%
print("\n" + "=" * 64)
print("Build matched-subset post-2000 convex + concave hulls")
print("=" * 64)

matched_convex_hulls: dict[str, dict[str, Polygon]] = {s: {} for s in STRATEGIES}
matched_concave_hulls: dict[str, dict[str, Polygon]] = {s: {} for s in STRATEGIES}
for s in STRATEGIES:
    print(f"\n  --- {s}: {len(matched_points[s])} matched species ---")
    for i, (sp, parts) in enumerate(matched_points[s].items(), start=1):
        pts = np.vstack(parts) if len(parts) > 1 else parts[0]
        matched_convex_hulls[s][sp] = convex_hull_safe(pts)
        matched_concave_hulls[s][sp] = concave_hull_safe(pts, ratio=CONCAVE_RATIO)
        if i % 50 == 0 or i == len(matched_points[s]):
            print(f"    built {i}/{len(matched_points[s])} hull pairs")
    matched_points[s].clear()


# %% [markdown]
# ## Compute matched-subset misidentification per (Nside, rangemap variant)

# %%
print("\n" + "=" * 64)
print("Matched-subset misidentification per (Nside, variant)")
print("=" * 64)

verif6_rows = []
for s in STRATEGIES:
    print(f"\n  --- {s} ---")
    for n in NSIDES:
        iberian_arr = IBERIA_PIX[n]
        # Atlas richness from matched-species set count per cell.
        atlas_dict = {c: len(sps) for c, sps in matched_atlas[s][n].items()}
        atlas = align_counts_to_cells(atlas_dict, iberian_arr)

        # Convex hull rangemap (matched subset, post-2000).
        counts_cx = hulls_to_per_cell_count(
            matched_convex_hulls[s], n, iberian_arr,
        )
        rm_convex = align_counts_to_cells(counts_cx, iberian_arr)

        # Concave hull rangemap (matched subset, post-2000).
        counts_cv = hulls_to_per_cell_count(
            matched_concave_hulls[s], n, iberian_arr,
        )
        rm_concave = align_counts_to_cells(counts_cv, iberian_arr)

        # Art-12 expert rangemap (matched subset).
        rm_art12 = art12_rangemap[s][n]

        mis_cx = hotspot_misidentified_pct(atlas, rm_convex)
        mis_cv = hotspot_misidentified_pct(atlas, rm_concave)
        mis_a12 = hotspot_misidentified_pct(atlas, rm_art12)

        verif6_rows.append({
            "strategy": s, "nside": n,
            "n_species_matched": len(matched_species_by_strategy[s]),
            "n_cells_atlas_nonzero": int((atlas > 0).sum()),
            "mean_atlas": round(float(atlas.mean()), 2),
            "mean_rm_convex": round(float(rm_convex.mean()), 2),
            "mean_rm_concave": round(float(rm_concave.mean()), 2),
            "mean_rm_art12": round(float(rm_art12.mean()), 2),
            "misid_convex": round(mis_cx, 2),
            "misid_concave": round(mis_cv, 2),
            "misid_art12": round(mis_a12, 2),
        })
        print(f"    Nside={n:>3}  "
              f"misid: convex={mis_cx:5.1f}%  "
              f"concave={mis_cv:5.1f}%  "
              f"Art-12={mis_a12:5.1f}%")

verif6_df = pd.DataFrame(verif6_rows)
verif6_path = RESULTS_DIR / "verif6_art12.parquet"
verif6_df.to_parquet(verif6_path, index=False)
print(f"\nsaved {verif6_path}")


# %% [markdown]
# ## Decomposition table at Nside 256

# %%
print("\n" + "=" * 64)
print("MATCHED-SUBSET DECOMPOSITION AT NSIDE 256 (H&J 0.25° ≈ 25 km)")
print("=" * 64)
print(f"\n  H&J 2007 Australia              :  47.8 %  misidentified")
print(f"  H&J 2007 Southern Africa        :  68.6 %  misidentified\n")
for s in STRATEGIES:
    r = verif6_df[(verif6_df.strategy == s) & (verif6_df.nside == 256)].iloc[0]
    print(f"  {s} (n={r['n_species_matched']} matched species):")
    print(f"    convex hull (post-2000)       : {r['misid_convex']:5.1f} %")
    print(f"    concave hull (post-2000)      : {r['misid_concave']:5.1f} %")
    print(f"    Art-12 expert polygons        : {r['misid_art12']:5.1f} %  ← gold standard")
    delta = r["misid_convex"] - r["misid_art12"]
    print(f"    Δ convex → Art-12             : {delta:+5.1f} pp")


# %% [markdown]
# ## Figure: scale-dependence comparison
#
# Three curves per strategy (convex / concave / Art-12) on the matched
# species subset, overlaid with H&J references.

# %%
fig, ax = plt.subplots(figsize=(11, 6.5))
for s in STRATEGIES:
    sub = verif6_df[verif6_df.strategy == s].sort_values("nside")
    ax.plot(sub.nside, sub.misid_convex, marker="o", lw=2.2,
            color=STRATEGY_COLORS[s],
            label=f"{s} — convex hull (matched subset)")
    ax.plot(sub.nside, sub.misid_concave, marker="s", lw=2.2,
            linestyle="--", color=STRATEGY_COLORS[s], alpha=0.75,
            label=f"{s} — concave hull (matched subset)")
    ax.plot(sub.nside, sub.misid_art12, marker="^", lw=2.5,
            linestyle="-", color=STRATEGY_COLORS[s], alpha=1.0,
            markersize=10, markeredgecolor="black", markeredgewidth=0.7,
            label=f"{s} — Art-12 expert polygons (gold standard)")

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
ax.set_xlabel("HEALPix Nside (NESTED) / log scale")
ax.set_ylabel("Hotspot misidentification (%)  /  symmetric set non-overlap of top-5%")


def nside_to_km(n):
    return np.sqrt(5.10e8 / (12 * n * n))


def km_to_nside(k):
    return np.sqrt(5.10e8 / (12 * k * k))


sec = ax.secondary_xaxis("top", functions=(nside_to_km, km_to_nside))
sec.set_xlabel("approx. cell side (km)")
ax.set_ylim(0, 100)
ax.set_title(
    "Test 6 — Article 12 gold-standard rangemap vs convex / concave hull substitutes\n"
    "Matched-subset misidentification (260 Iberian breeding species "
    "in both Art-12 and post-2000 GBIF)",
    fontsize=11,
)
ax.legend(loc="lower right", fontsize=7, ncol=2, framealpha=0.92,
          borderaxespad=0.6)
fig.tight_layout()
art12_fig = FIGURES_DIR / "verif_art12_goldstandard.png"
fig.savefig(art12_fig, dpi=150, bbox_inches="tight")
fig.savefig(art12_fig.with_suffix(".pdf"), bbox_inches="tight")
plt.show()
print(f"\nsaved {art12_fig}")
