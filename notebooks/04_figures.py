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
# # 04 — Figures (Hurlbert & Jetz 2007 scale-replication)
#
# Two figures:
#
# 1. **`figures/main_result.png`** — the headline figure. Misidentified
#    % (y) vs Nside / cell size (x, log-scale) for this replication,
#    with H&J 2007's Table 2 reference values for Australia and southern
#    Africa overlaid as horizontal annotations.
#
# 2. **`figures/iberia_hotspots_nside128.png`** — secondary 2-panel
#    Iberia map at Nside=128 (~50 km cells, the H&J ~0.5° equivalent)
#    showing the modern-vs-historical hotspot cells side by side. Built
#    with cartopy + a simple HEALPix-to-polygon polygon-fill loop (the
#    DOMAIN.md-recommended `healpix-plot` is not on conda-forge yet;
#    cartopy + Shapely is a robust substitute).
#
# **DOMAIN.md / USER_PREFERENCES.md style:**
#
# - `matplotlib.use('Agg')` is forbidden (blocks inline display in
#   MyST). We rely on the default backend.
# - `plt.show()` after every `fig.savefig()` for MyST inline output.
# - DPI = 150 (USER_PREFERENCES.md `plot_dpi`).
# - Style sheet "seaborn-v0_8-whitegrid" (USER_PREFERENCES.md
#   `plot_style`).
# - If the data is synthetic (per the flag from `01_data_download.py`)
#   we overlay a clear "DEMO DATA — NOT A REAL REPLICATION" banner on
#   the figure so the synthetic numbers can never be mistaken for a
#   real result.

# %%
import json
from pathlib import Path

import cartopy.crs as ccrs
import cartopy.feature as cfeature
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import xarray as xr
from healpix_geo import nested as hp_nested
from matplotlib.patches import Polygon as MplPolygon

plt.style.use("seaborn-v0_8-whitegrid")

# %%
ROOT = Path("..").resolve()
DATA = ROOT / "data"
CLEAN_DIR = DATA / "clean"
RAW_DIR = DATA / "raw"
RESULTS_DIR = ROOT / "results"
FIGURES_DIR = ROOT / "figures"
FIGURES_DIR.mkdir(parents=True, exist_ok=True)

SCALE_PARQUET = RESULTS_DIR / "scale_dependence.parquet"
HOTSPOTS_PARQUET = RESULTS_DIR / "hotspot_cells.parquet"
HEADLINE_JSON = RESULTS_DIR / "headline.json"
RICHNESS_NC = CLEAN_DIR / "richness_per_nside.nc"
SYNTHETIC_FLAG = RAW_DIR / "USING_SYNTHETIC_DEMO_DATA.txt"

SYNTHETIC = SYNTHETIC_FLAG.exists()
ELLIPSOID = "WGS84"

scale_df = pd.read_parquet(SCALE_PARQUET)
hotspots_df = pd.read_parquet(HOTSPOTS_PARQUET)
with open(HEADLINE_JSON) as f:
    headline = json.load(f)

print(f"SYNTHETIC = {SYNTHETIC}")
print(scale_df.to_string(index=False))


# %% [markdown]
# ## Figure 1 — Misidentified % vs Nside / cell size
#
# H&J 2007 Table 2 reference numbers (Iberia bird AVG ≈ ?, but H&J
# reports Australia 47.8% misidentified and S. Africa 68.6% at 0.25°
# resolution; both regions converge to ~5-10% at 4-8°).

# %%
MAIN_PNG = FIGURES_DIR / "main_result.png"
MAIN_PDF = FIGURES_DIR / "main_result.pdf"

fig, ax = plt.subplots(figsize=(9, 5.5))

# This replication's curve (misidentified % vs Nside).
ax.plot(
    scale_df["nside"], scale_df["misidentified_pct"],
    marker="o", markersize=7, lw=2, color="#1f77b4",
    label="This replication (Iberian birds, HEALPix NESTED)",
)

# H&J 2007 Australia + Southern Africa reference values, plotted at the
# Nside whose cell side approximately matches each H&J lat-lon
# resolution. Convert by: lat-lon res in degrees -> cell size in km
# (~111 km/deg at equator) -> closest Nside.
hj_table2 = {
    "Australia": {0.25: 47.8, 0.5: 44.0, 1.0: 40.0, 2.0: 20.0, 4.0: 5.0},
    "Southern Africa": {0.25: 68.6, 0.5: 63.0, 1.0: 22.2, 2.0: 15.0, 4.0: 5.0},
}
# Approximate Nside that corresponds to a given lat-lon deg:
#   cell_side_km(Nside) ≈ deg * 111 km. So Nside ≈ sqrt(area/n_cells_per_4pi_deg^2)
# Just use a small lookup for the H&J resolutions:
hj_nside_for_deg = {
    0.25: 256,  # ~14 km vs 27 km — close enough on log axis
    0.5: 128,   # ~28 km vs 55 km
    1.0: 64,    # ~55 km vs 111 km
    2.0: 32,    # ~111 km vs 222 km
    4.0: 16,    # ~221 km vs 444 km
}
hj_colors = {"Australia": "#ff7f0e", "Southern Africa": "#2ca02c"}
hj_markers = {"Australia": "s", "Southern Africa": "^"}
for region, table in hj_table2.items():
    xs = [hj_nside_for_deg[d] for d in table.keys()]
    ys = list(table.values())
    ax.plot(xs, ys, marker=hj_markers[region], markersize=8, lw=1.2,
            linestyle="--", color=hj_colors[region], alpha=0.65,
            label=f"H&J 2007 {region} (Table 2 reference)")

# Wilcoxon-indistinguishable region (p > 0.10) — shaded background.
if any(scale_df["wilcoxon_indistinguishable"]):
    indist = scale_df[scale_df["wilcoxon_indistinguishable"]]
    nside_min_indist = indist["nside"].min()
    ax.axvspan(scale_df["nside"].min() / 1.2, nside_min_indist, alpha=0.10,
               color="green",
               label=f"Wilcoxon p > {0.10} (dissolution zone)")

ax.set_xscale("log", base=2)
ax.set_xticks(scale_df["nside"].tolist())
ax.set_xticklabels(scale_df["nside"].tolist())
ax.set_xlabel("HEALPix Nside (NESTED)  /  log scale")
ax.set_ylabel("Hotspot mis-identification (%)\nsymmetric set non-overlap of top-5%")

# Secondary x-axis with cell size in km.
def nside_to_km(n):
    return np.sqrt(5.10e8 / (12 * n * n))


def km_to_nside(k):
    n = np.sqrt(5.10e8 / (12 * k * k))
    return n


sec = ax.secondary_xaxis("top", functions=(nside_to_km, km_to_nside))
sec.set_xlabel("approx. cell side (km)")

ax.set_ylim(0, 100)
ax.set_title(
    "Scale-dependence of biodiversity hotspots — Hurlbert & Jetz (2007) replication\n"
    "modern Iberian birds × HEALPix NESTED substrate"
    + ("  —  SYNTHETIC DEMO DATA" if SYNTHETIC else ""),
    fontsize=11,
)
ax.legend(loc="lower left", fontsize=9, framealpha=0.92)

# Synthetic-data overlay banner (only if applicable).
if SYNTHETIC:
    ax.text(
        0.5, 0.55,
        "DEMO DATA — NOT A REAL REPLICATION\n"
        "Re-run with real GBIF download keys per docs/gbif-mint-instructions.md",
        transform=ax.transAxes,
        ha="center", va="center",
        fontsize=14, color="red", weight="bold",
        bbox=dict(boxstyle="round,pad=0.4", facecolor="white",
                  edgecolor="red", alpha=0.9),
    )

fig.tight_layout()
fig.savefig(MAIN_PNG, dpi=150, bbox_inches="tight")
fig.savefig(MAIN_PDF, bbox_inches="tight")
plt.show()  # required for MyST inline display


# %% [markdown]
# ## Figure 2 — Iberia hotspot maps (Nside=128, ~50 km cells)
#
# Two panels side-by-side: modern hotspots (left), historical hotspots
# (right). Coloured polygons show the 5% richest cells at this Nside;
# greyscale background shows full richness for context.

# %%
MAP_PNG = FIGURES_DIR / "iberia_hotspots_nside128.png"
MAP_PDF = FIGURES_DIR / "iberia_hotspots_nside128.pdf"

NSIDE_MAP = 128
DEPTH_MAP = int(np.log2(NSIDE_MAP))

# Load per-cell richness at Nside=128.
ds = xr.open_dataset(RICHNESS_NC, group=f"nside_{NSIDE_MAP}", engine="netcdf4")
modern_r = ds["richness_modern"].values
historical_r = ds["richness_historical"].values
cells_128 = ds["cell"].values.astype(np.uint64)
ds.close()

hotspots_128 = hotspots_df[hotspots_df["nside"] == NSIDE_MAP]
mod_hot_set = set(hotspots_128[hotspots_128["source"] == "modern"]["cell_id"])
hist_hot_set = set(hotspots_128[hotspots_128["source"] == "historical"]["cell_id"])

# Get the 4-vertex polygon outline of each cell at Nside=128.
# healpix_geo.nested.vertices returns a 2-tuple (lon_array, lat_array),
# each of shape (n_pix, 4) — one row per cell, four corners per row.
verts_lon, verts_lat = hp_nested.vertices(cells_128, DEPTH_MAP, ELLIPSOID, step=1)
verts_lon = np.where(verts_lon > 180.0, verts_lon - 360.0, verts_lon)
print(f"verts_lon shape: {verts_lon.shape}, verts_lat shape: {verts_lat.shape}")


def cell_polygons(lons: np.ndarray, lats: np.ndarray) -> list[np.ndarray]:
    """Per-cell (4, 2) lon/lat polygon outline.

    Skips cells whose lon corners wrap across the +/-180 dateline, which
    shouldn't happen inside the Iberia bbox but is guarded for safety."""
    polys = []
    for i in range(lons.shape[0]):
        v = np.column_stack([lons[i], lats[i]])
        if (v[:, 0].max() - v[:, 0].min()) > 90:
            polys.append(None)  # dateline-wrapped cell
            continue
        polys.append(v)
    return polys


polys_128 = cell_polygons(verts_lon, verts_lat)

# Plot.
fig, axes = plt.subplots(
    1, 2, figsize=(13, 6),
    subplot_kw={"projection": ccrs.PlateCarree()},
)


def draw_panel(ax, richness, hotspot_set, title, cmap_name="viridis"):
    ax.set_extent([-10.5, 4.5, 34.5, 44.5], crs=ccrs.PlateCarree())
    ax.add_feature(cfeature.LAND, facecolor="#f6f6f4", zorder=0)
    ax.add_feature(cfeature.OCEAN, facecolor="#dfeefa", zorder=0)
    ax.add_feature(cfeature.COASTLINE, lw=0.5)
    ax.add_feature(cfeature.BORDERS, lw=0.4, edgecolor="#888")
    # Greyscale background: full richness.
    max_r = max(1, richness.max())
    cmap = plt.get_cmap(cmap_name)
    for i, (poly, r) in enumerate(zip(polys_128, richness)):
        if poly is None:
            continue
        c = int(cells_128[i])
        if c in hotspot_set:
            # Hotspot — red overlay.
            patch = MplPolygon(poly, closed=True,
                               facecolor="#d62728", edgecolor="#9b1c1c",
                               lw=0.3, alpha=0.85, zorder=2,
                               transform=ccrs.PlateCarree())
            ax.add_patch(patch)
        elif r > 0:
            # Greyscale fill for non-hotspot cells with observed richness.
            shade = cmap(r / max_r)
            patch = MplPolygon(poly, closed=True,
                               facecolor=shade, edgecolor="none",
                               alpha=0.55, zorder=1,
                               transform=ccrs.PlateCarree())
            ax.add_patch(patch)
    ax.gridlines(draw_labels=True, lw=0.2, color="#cccccc",
                 alpha=0.5, ls="--")
    ax.set_title(title, fontsize=11)


draw_panel(
    axes[0], modern_r, mod_hot_set,
    f"Modern GBIF (atlas-eq) — top-5% hotspots\nn={len(mod_hot_set)}/{len(cells_128):,} cells",
    cmap_name="Blues",
)
draw_panel(
    axes[1], historical_r, hist_hot_set,
    f"Historical EOO hull (range-map-eq) — top-5% hotspots\nn={len(hist_hot_set)}/{len(cells_128):,} cells",
    cmap_name="Greens",
)

fig.suptitle(
    f"Iberian bird richness hotspots at HEALPix Nside={NSIDE_MAP} "
    f"(~{round(np.sqrt(5.10e8/(12*NSIDE_MAP**2)), 1)} km cells)"
    + ("  —  SYNTHETIC DEMO DATA" if SYNTHETIC else ""),
    fontsize=12, y=1.02,
)

if SYNTHETIC:
    fig.text(
        0.5, 0.02, "DEMO DATA — NOT A REAL REPLICATION",
        ha="center", color="red", fontsize=11, weight="bold",
    )

fig.tight_layout()
fig.savefig(MAP_PNG, dpi=150, bbox_inches="tight")
fig.savefig(MAP_PDF, bbox_inches="tight")
plt.show()  # required for MyST inline display

print(f"\nsaved {MAIN_PNG}")
print(f"saved {MAP_PNG}")
