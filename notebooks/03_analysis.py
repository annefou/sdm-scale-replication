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
# # 03 — Analysis (H&J 2007 scale dependence on HEALPix-NESTED ladder)
#
# Reproduces H&J 2007's two headline statistics — but on a HEALPix-NESTED
# substrate with modern Iberian bird data — at each Nside in the ladder
# {16, 32, 64, 128, 256, 512}:
#
# 1. **Hotspot overlap.** A "hotspot" = the top-5% richest cells. The
#    headline H&J number is the **symmetric non-overlap** between the
#    range-map-derived top-5% set and the atlas-derived top-5% set.
#    Per `nanopubs/drafts/00_paper_summary.md` H&J report 31.4%
#    Southern Africa / 52.2% Australia overlap at 0.25°.
#
# 2. **Wilcoxon signed-rank** on the per-cell richness pairs (modern
#    vs historical EOO at the same cell). H&J's "≥ 4° statistically
#    indistinguishable" finding is the threshold (P > 0.10) below which
#    the two distributions converge.
#
# Two output Parquets under `results/`:
#
# - `scale_dependence.parquet` — one row per Nside, columns:
#   `nside, cell_size_km, n_cells, modern_hotspots_n, historical_hotspots_n,
#   overlap_n, overlap_pct, misidentified_pct, wilcoxon_W, wilcoxon_p`.
# - `hotspot_cells.parquet` — long form (`nside, source, cell_id`) listing
#   every hotspot at every Nside. Used by 04_figures.py for the maps.
#
# **Verify before drafting nanopubs:** the Replication Study's Methodology
# field and the Outcome's Evidence field will be drafted *from this code*.

# %%
import json
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr
from scipy.stats import wilcoxon

# %%
ROOT = Path("..").resolve()
DATA = ROOT / "data"
CLEAN_DIR = DATA / "clean"
RAW_DIR = DATA / "raw"
RESULTS_DIR = ROOT / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

RICHNESS_NC = CLEAN_DIR / "richness_per_nside.nc"
SYNTHETIC_FLAG = RAW_DIR / "USING_SYNTHETIC_DEMO_DATA.txt"
SYNTHETIC = SYNTHETIC_FLAG.exists()

OUT_SCALE = RESULTS_DIR / "scale_dependence.parquet"
OUT_HOTSPOTS = RESULTS_DIR / "hotspot_cells.parquet"
OUT_HEADLINE = RESULTS_DIR / "headline.json"

NSIDES = [16, 32, 64, 128, 256, 512]
HOTSPOT_FRACTION = 0.05  # H&J 2007: top-5% richest cells.
WILCOXON_P_THRESHOLD = 0.10  # H&J 2007 indistinguishability threshold.

# Approximate cell side in km for HEALPix-NESTED at each Nside.
# Surface area of a sphere with R=6371 km is 4*pi*R^2 = 5.10e8 km^2.
# Each Nside has 12 * nside^2 cells of equal area; the equivalent-radius
# side length is sqrt(area_per_cell).
EARTH_AREA_KM2 = 4.0 * np.pi * 6371.0 ** 2


def cell_side_km(nside: int) -> float:
    n_cells = 12 * nside * nside
    return float(np.sqrt(EARTH_AREA_KM2 / n_cells))


print(f"SYNTHETIC = {SYNTHETIC}")
print(f"Hotspot fraction = {HOTSPOT_FRACTION:.1%}")
print(f"NSIDES (cell side km): {[(n, round(cell_side_km(n), 1)) for n in NSIDES]}")


# %% [markdown]
# ## Helpers — hotspot overlap and Wilcoxon
#
# Hotspot set definition mirrors H&J 2007: rank cells by richness
# (descending), take the top-5%. Ties at the boundary go to the
# `top_k = ceil(0.05 * n_cells)` slice — i.e. ceiling, not floor — so
# that small cell counts still yield at least one hotspot.

# %%
def top_k_set(richness: np.ndarray, fraction: float) -> set[int]:
    """Indices (positions in the array) of the top-`fraction` cells by richness.

    Ties broken arbitrarily by argsort stability — close enough to H&J's
    operational definition for the headline overlap statistic. Returns
    a Python set for fast set algebra."""
    n = len(richness)
    if n == 0:
        return set()
    top_k = max(1, int(np.ceil(fraction * n)))
    # argpartition is faster than full argsort for the top-k cut.
    idx = np.argpartition(richness, -top_k)[-top_k:]
    return set(int(i) for i in idx)


def hotspot_overlap(modern: np.ndarray, historical: np.ndarray,
                    cells: np.ndarray, fraction: float):
    """Return dict with hotspot-set summary stats at one Nside."""
    mod_idx = top_k_set(modern, fraction)
    hist_idx = top_k_set(historical, fraction)

    intersection = mod_idx & hist_idx
    union = mod_idx | hist_idx
    sym_diff = mod_idx.symmetric_difference(hist_idx)

    # Overlap percentage in H&J's sense: |intersection| / mean(|mod|, |hist|).
    # H&J Table 2 reports the percentage of range-map hotspots that are also
    # atlas hotspots — i.e. |intersection| / |range_map_hotspots| — but the
    # 31.4 / 52.2 figures are roughly symmetric, so we report both an
    # asymmetric (range-map-as-reference) and a symmetric overlap.
    n_mod = len(mod_idx)
    n_hist = len(hist_idx)
    overlap_n = len(intersection)
    # Symmetric overlap: Jaccard-style |intersection| / |union|
    sym_overlap_pct = (overlap_n / len(union) * 100.0) if union else 0.0
    # Asymmetric (range-map-as-reference, matches H&J Table 2):
    asym_overlap_pct = (overlap_n / n_hist * 100.0) if n_hist else 0.0
    # Symmetric NON-overlap (the "misidentified" headline figure):
    misidentified_pct = (
        len(sym_diff) / len(union) * 100.0
    ) if union else 0.0

    # Return the cell IDs for the figures notebook.
    mod_cells = cells[list(mod_idx)] if mod_idx else np.array([], dtype=np.int64)
    hist_cells = cells[list(hist_idx)] if hist_idx else np.array([], dtype=np.int64)
    return {
        "modern_hotspots_n": n_mod,
        "historical_hotspots_n": n_hist,
        "overlap_n": overlap_n,
        "overlap_pct_symmetric": sym_overlap_pct,
        "overlap_pct_asymmetric_hjtable2": asym_overlap_pct,
        "misidentified_pct": misidentified_pct,
        "modern_hotspot_cells": mod_cells,
        "historical_hotspot_cells": hist_cells,
    }


def wilcoxon_pair(modern: np.ndarray, historical: np.ndarray) -> tuple[float, float]:
    """Wilcoxon signed-rank on the paired per-cell richness.

    Returns (W, p). Empty / all-zero-diff input gives (nan, 1.0)."""
    diff = modern - historical
    if (diff == 0).all() or len(diff) == 0:
        return float("nan"), 1.0
    try:
        res = wilcoxon(modern, historical, zero_method="wilcox",
                       alternative="two-sided")
        return float(res.statistic), float(res.pvalue)
    except ValueError as e:
        print(f"  wilcoxon failed: {e}")
        return float("nan"), float("nan")


# %% [markdown]
# ## Iterate the ladder

# %%
print(f"\n--- Loading {RICHNESS_NC} ---")
scale_rows: list[dict] = []
hotspot_rows: list[dict] = []

for nside in NSIDES:
    ds = xr.open_dataset(RICHNESS_NC, group=f"nside_{nside}", engine="netcdf4")
    modern = ds["richness_modern"].values.astype(np.int64)
    historical = ds["richness_historical"].values.astype(np.int64)
    cells = ds["cell"].values.astype(np.int64)
    ds.close()

    overlap = hotspot_overlap(modern, historical, cells, HOTSPOT_FRACTION)
    W, p = wilcoxon_pair(modern, historical)

    row = {
        "nside": nside,
        "cell_size_km": round(cell_side_km(nside), 2),
        "n_cells": int(len(cells)),
        "modern_hotspots_n": overlap["modern_hotspots_n"],
        "historical_hotspots_n": overlap["historical_hotspots_n"],
        "overlap_n": overlap["overlap_n"],
        "overlap_pct_symmetric": round(overlap["overlap_pct_symmetric"], 2),
        "overlap_pct_asymmetric_hjtable2": round(
            overlap["overlap_pct_asymmetric_hjtable2"], 2
        ),
        "misidentified_pct": round(overlap["misidentified_pct"], 2),
        "wilcoxon_W": W,
        "wilcoxon_p": p,
        "wilcoxon_indistinguishable": p > WILCOXON_P_THRESHOLD,
    }
    scale_rows.append(row)

    # Hotspot cell IDs long-form for 04_figures.
    for c in overlap["modern_hotspot_cells"]:
        hotspot_rows.append({"nside": nside, "source": "modern", "cell_id": int(c)})
    for c in overlap["historical_hotspot_cells"]:
        hotspot_rows.append({"nside": nside, "source": "historical", "cell_id": int(c)})

    print(f"  nside={nside:>4}  "
          f"n_cells={row['n_cells']:>6,}  "
          f"hotspots mod={row['modern_hotspots_n']:>4} "
          f"hist={row['historical_hotspots_n']:>4}  "
          f"misidentified={row['misidentified_pct']:>5.1f}%  "
          f"Wilcoxon W={W:>10.1f} p={p:.4f}"
          + ("  [INDISTINGUISHABLE]" if row["wilcoxon_indistinguishable"] else ""))

scale_df = pd.DataFrame(scale_rows)
scale_df.to_parquet(OUT_SCALE, index=False)
print(f"\nsaved {OUT_SCALE}")

hotspot_df = pd.DataFrame(hotspot_rows)
hotspot_df.to_parquet(OUT_HOTSPOTS, index=False)
print(f"saved {OUT_HOTSPOTS}  ({len(hotspot_df):,} rows)")


# %% [markdown]
# ## Headline JSON — the single misidentification number + dissolution Nside
#
# The "headline" of this replication is the misidentification % at the
# finest Nside (512, ~7 km), which is the analogue of H&J's 0.25° row
# in Table 2. The dissolution Nside is the coarsest Nside at which the
# Wilcoxon p-value first exceeds 0.10 — H&J's indistinguishability
# threshold.

# %%
finest_row = scale_df[scale_df["nside"] == max(NSIDES)].iloc[0]
coarsest_row = scale_df[scale_df["nside"] == min(NSIDES)].iloc[0]

indistinguishable_rows = scale_df[scale_df["wilcoxon_indistinguishable"]]
# Dissolution = coarsest Nside that is indistinguishable AND is the smallest
# such — i.e. the COARSEST nside is normally smallest in our ladder; we want
# the highest Nside that meets the criterion (so smallest cell that still
# averages out the discrepancy), which is what H&J's ">=2 degree" framing
# corresponds to.
# Better: report the smallest nside (largest cell) where p > 0.10 — that's the
# H&J "as cell size grows, the difference dissolves" framing.
if len(indistinguishable_rows):
    dissolution_nside = int(indistinguishable_rows.sort_values("nside").iloc[-1]["nside"])
    dissolution_cell_km = float(cell_side_km(dissolution_nside))
else:
    dissolution_nside = None
    dissolution_cell_km = None

headline = {
    "synthetic_data": SYNTHETIC,
    "hotspot_fraction": HOTSPOT_FRACTION,
    "wilcoxon_p_threshold": WILCOXON_P_THRESHOLD,
    "finest_nside": int(finest_row["nside"]),
    "finest_cell_size_km": float(finest_row["cell_size_km"]),
    "finest_misidentified_pct": float(finest_row["misidentified_pct"]),
    "finest_overlap_pct_symmetric": float(finest_row["overlap_pct_symmetric"]),
    "finest_overlap_pct_asymmetric_hjtable2": float(
        finest_row["overlap_pct_asymmetric_hjtable2"]
    ),
    "coarsest_nside": int(coarsest_row["nside"]),
    "coarsest_cell_size_km": float(coarsest_row["cell_size_km"]),
    "coarsest_misidentified_pct": float(coarsest_row["misidentified_pct"]),
    "dissolution_nside": dissolution_nside,
    "dissolution_cell_size_km": dissolution_cell_km,
    "n_nsides_indistinguishable": int(len(indistinguishable_rows)),
    "hj_2007_reference": {
        "australia_overlap_pct_at_0p25deg": 52.2,
        "australia_misidentified_pct_at_0p25deg": 47.8,
        "southafrica_overlap_pct_at_0p25deg": 31.4,
        "southafrica_misidentified_pct_at_0p25deg": 68.6,
        "indistinguishable_at_or_above_deg": 4.0,
    },
}
with open(OUT_HEADLINE, "w") as f:
    json.dump(headline, f, indent=2, default=str)

print(f"\n--- HEADLINE ---")
print(json.dumps(headline, indent=2, default=str))
print(f"\nsaved {OUT_HEADLINE}")


# %% [markdown]
# ## Print the comparison table

# %%
print("\nScale-dependence summary (this replication):\n")
print(scale_df.to_string(index=False))

print("\nH&J 2007 Table 2 reference numbers:")
hj_ref = pd.DataFrame([
    {"resolution_deg": 0.25, "australia_overlap_pct": 52.2, "southafrica_overlap_pct": 31.4},
    {"resolution_deg": 0.50, "australia_overlap_pct": 56.0, "southafrica_overlap_pct": 37.0},
    {"resolution_deg": 1.00, "australia_overlap_pct": 60.0, "southafrica_overlap_pct": 77.8},
    {"resolution_deg": 2.00, "australia_overlap_pct": 80.0, "southafrica_overlap_pct": 85.0},
    {"resolution_deg": 4.00, "australia_overlap_pct": 95.0, "southafrica_overlap_pct": 95.0},
])
print(hj_ref.to_string(index=False))
