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
# # 03 — Analysis (H&J 2007 scale dependence, two BoR strategies)
#
# Reproduces H&J 2007's two headline statistics for **each strategy**
# (museum vs allbor) across the HEALPix-NESTED ladder
# Nside in {16, 32, 64, 128, 256, 512}:
#
# 1. **Hotspot overlap.** A "hotspot" = the top-5% richest cells. The
#    headline number is the **symmetric non-overlap** between the
#    rangemap-derived top-5% set (from per-species EOO hulls of pre-2000
#    occurrences) and the atlas-derived top-5% set (from post-2000
#    occurrences). H&J Table 2 reports 31.4% (southern Africa) /
#    52.2% (Australia) overlap at 0.25°.
#
# 2. **Wilcoxon signed-rank** on the per-cell richness pairs. H&J's
#    "≥ 4° statistically indistinguishable" threshold (P > 0.10) is the
#    dissolution criterion. The "dissolution Nside" per strategy is the
#    largest Nside (smallest cell) at which p > 0.10.
#
# Outputs (under `results/`):
#
# - `scale_dependence.parquet` — long-form: one row per (strategy, nside).
# - `hotspot_cells.parquet` — long-form: (strategy, nside, source, cell_id).
# - `headline.json` — per-strategy headline numbers + H&J reference.
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

STRATEGIES = ["museum", "allbor"]
STRATEGY_RICHNESS_NC = {
    s: CLEAN_DIR / f"richness_{s}.nc" for s in STRATEGIES
}
STRATEGY_SYNTH_FLAGS = {
    "museum": RAW_DIR / "USING_SYNTHETIC_DEMO_DATA_museum.txt",
    "allbor": RAW_DIR / "USING_SYNTHETIC_DEMO_DATA_allbor.txt",
}
SYNTHETIC = {s: STRATEGY_SYNTH_FLAGS[s].exists() for s in STRATEGIES}

OUT_SCALE = RESULTS_DIR / "scale_dependence.parquet"
OUT_HOTSPOTS = RESULTS_DIR / "hotspot_cells.parquet"
OUT_HEADLINE = RESULTS_DIR / "headline.json"

NSIDES = [16, 32, 64, 128, 256, 512]
HOTSPOT_FRACTION = 0.05      # H&J 2007: top-5% richest cells.
WILCOXON_P_THRESHOLD = 0.10  # H&J 2007 indistinguishability threshold.

EARTH_AREA_KM2 = 4.0 * np.pi * 6371.0 ** 2


def cell_side_km(nside: int) -> float:
    n_cells = 12 * nside * nside
    return float(np.sqrt(EARTH_AREA_KM2 / n_cells))


print(f"STRATEGIES = {STRATEGIES}")
print(f"SYNTHETIC = {SYNTHETIC}")
print(f"Hotspot fraction = {HOTSPOT_FRACTION:.1%}")
print(f"NSIDES (cell side km): "
      f"{[(n, round(cell_side_km(n), 1)) for n in NSIDES]}")


# %% [markdown]
# ## Helpers — hotspot overlap and Wilcoxon

# %%
def top_k_set(richness: np.ndarray, fraction: float) -> set[int]:
    """Positions of the top-`fraction` cells by richness (descending)."""
    n = len(richness)
    if n == 0:
        return set()
    top_k = max(1, int(np.ceil(fraction * n)))
    idx = np.argpartition(richness, -top_k)[-top_k:]
    return set(int(i) for i in idx)


def hotspot_overlap(atlas: np.ndarray, rangemap: np.ndarray,
                    cells: np.ndarray, fraction: float):
    """Hotspot-set summary stats at one Nside."""
    atl_idx = top_k_set(atlas, fraction)
    rm_idx = top_k_set(rangemap, fraction)

    intersection = atl_idx & rm_idx
    union = atl_idx | rm_idx
    sym_diff = atl_idx.symmetric_difference(rm_idx)

    n_atl = len(atl_idx)
    n_rm = len(rm_idx)
    overlap_n = len(intersection)
    sym_overlap_pct = (overlap_n / len(union) * 100.0) if union else 0.0
    # H&J Table 2: |intersection| / |rangemap_hotspots|, asymmetric.
    asym_overlap_pct = (overlap_n / n_rm * 100.0) if n_rm else 0.0
    misidentified_pct = (
        len(sym_diff) / len(union) * 100.0
    ) if union else 0.0

    atl_cells = cells[list(atl_idx)] if atl_idx else np.array([], dtype=np.int64)
    rm_cells = cells[list(rm_idx)] if rm_idx else np.array([], dtype=np.int64)
    return {
        "atlas_hotspots_n": n_atl,
        "rangemap_hotspots_n": n_rm,
        "overlap_n": overlap_n,
        "overlap_pct_symmetric": sym_overlap_pct,
        "overlap_pct_asymmetric_hjtable2": asym_overlap_pct,
        "misidentified_pct": misidentified_pct,
        "atlas_hotspot_cells": atl_cells,
        "rangemap_hotspot_cells": rm_cells,
    }


def wilcoxon_pair(atlas: np.ndarray, rangemap: np.ndarray) -> tuple[float, float]:
    """Wilcoxon signed-rank on the paired per-cell richness."""
    diff = atlas - rangemap
    if (diff == 0).all() or len(diff) == 0:
        return float("nan"), 1.0
    try:
        res = wilcoxon(atlas, rangemap, zero_method="wilcox",
                       alternative="two-sided")
        return float(res.statistic), float(res.pvalue)
    except ValueError as e:
        print(f"  wilcoxon failed: {e}")
        return float("nan"), float("nan")


# %% [markdown]
# ## Iterate (strategy, Nside)

# %%
scale_rows: list[dict] = []
hotspot_rows: list[dict] = []

for strategy in STRATEGIES:
    nc_path = STRATEGY_RICHNESS_NC[strategy]
    print(f"\n{'='*60}")
    print(f"=== Strategy: {strategy}  (synthetic={SYNTHETIC[strategy]}) ===")
    print(f"=== NetCDF  : {nc_path}")
    print(f"{'='*60}")

    for nside in NSIDES:
        ds = xr.open_dataset(nc_path, group=f"nside_{nside}", engine="netcdf4")
        atlas = ds["richness_atlas"].values.astype(np.int64)
        rangemap = ds["richness_rangemap"].values.astype(np.int64)
        cells = ds["cell"].values.astype(np.int64)
        ds.close()

        overlap = hotspot_overlap(atlas, rangemap, cells, HOTSPOT_FRACTION)
        W, p = wilcoxon_pair(atlas, rangemap)

        row = {
            "strategy": strategy,
            "nside": nside,
            "cell_size_km": round(cell_side_km(nside), 2),
            "n_cells": int(len(cells)),
            "atlas_hotspots_n": overlap["atlas_hotspots_n"],
            "rangemap_hotspots_n": overlap["rangemap_hotspots_n"],
            "overlap_n": overlap["overlap_n"],
            "overlap_pct_symmetric": round(overlap["overlap_pct_symmetric"], 2),
            "overlap_pct_asymmetric_hjtable2": round(
                overlap["overlap_pct_asymmetric_hjtable2"], 2
            ),
            "misidentified_pct": round(overlap["misidentified_pct"], 2),
            "wilcoxon_W": W,
            "wilcoxon_p": p,
            "indistinguishable_at_p10": bool(p > WILCOXON_P_THRESHOLD),
            "synthetic": SYNTHETIC[strategy],
        }
        scale_rows.append(row)

        for c in overlap["atlas_hotspot_cells"]:
            hotspot_rows.append({"strategy": strategy, "nside": nside,
                                 "source": "atlas", "cell_id": int(c)})
        for c in overlap["rangemap_hotspot_cells"]:
            hotspot_rows.append({"strategy": strategy, "nside": nside,
                                 "source": "rangemap", "cell_id": int(c)})

        print(f"  nside={nside:>4}  "
              f"n_cells={row['n_cells']:>6,}  "
              f"hotspots atlas={row['atlas_hotspots_n']:>4} "
              f"rm={row['rangemap_hotspots_n']:>4}  "
              f"misidentified={row['misidentified_pct']:>5.1f}%  "
              f"Wilcoxon W={W:>10.1f} p={p:.4f}"
              + ("  [INDISTINGUISHABLE]" if row["indistinguishable_at_p10"]
                 else ""))


scale_df = pd.DataFrame(scale_rows)
scale_df.to_parquet(OUT_SCALE, index=False)
print(f"\nsaved {OUT_SCALE}  ({len(scale_df)} rows)")

hotspot_df = pd.DataFrame(hotspot_rows)
hotspot_df.to_parquet(OUT_HOTSPOTS, index=False)
print(f"saved {OUT_HOTSPOTS}  ({len(hotspot_df):,} rows)")


# %% [markdown]
# ## Per-strategy headline JSON
#
# For each strategy, report:
# - finest-Nside misidentification % (the headline equivalent of H&J's
#   0.25° row in Table 2; Nside=256 maps to ~25 km ≈ 0.25°).
# - dissolution Nside (largest Nside where Wilcoxon p > 0.10).
# - per-Nside misidentification % + Wilcoxon p (compact dict).

# %%
def strategy_headline(strategy: str) -> dict:
    sub = scale_df[scale_df["strategy"] == strategy].sort_values("nside")
    finest = sub[sub["nside"] == max(NSIDES)].iloc[0]
    coarsest = sub[sub["nside"] == min(NSIDES)].iloc[0]
    indist = sub[sub["indistinguishable_at_p10"]]
    if len(indist):
        # H&J's "as cell size grows, difference dissolves" framing — we
        # want the LARGEST Nside (smallest cell) that still meets p>0.10
        # (closest to the headline 0.25° row from below).
        dissolution_nside = int(indist.sort_values("nside").iloc[-1]["nside"])
        dissolution_cell_km = float(cell_side_km(dissolution_nside))
    else:
        dissolution_nside = None
        dissolution_cell_km = None

    per_nside_summary = {
        int(r["nside"]): {
            "cell_size_km": float(r["cell_size_km"]),
            "misidentified_pct": float(r["misidentified_pct"]),
            "wilcoxon_p": float(r["wilcoxon_p"]),
            "indistinguishable_at_p10": bool(r["indistinguishable_at_p10"]),
        }
        for _, r in sub.iterrows()
    }

    return {
        "strategy": strategy,
        "synthetic_data": SYNTHETIC[strategy],
        "finest_nside": int(finest["nside"]),
        "finest_cell_size_km": float(finest["cell_size_km"]),
        "finest_misidentified_pct": float(finest["misidentified_pct"]),
        "finest_overlap_pct_symmetric": float(finest["overlap_pct_symmetric"]),
        "finest_overlap_pct_asymmetric_hjtable2": float(
            finest["overlap_pct_asymmetric_hjtable2"]
        ),
        "coarsest_nside": int(coarsest["nside"]),
        "coarsest_cell_size_km": float(coarsest["cell_size_km"]),
        "coarsest_misidentified_pct": float(coarsest["misidentified_pct"]),
        "dissolution_nside": dissolution_nside,
        "dissolution_cell_size_km": dissolution_cell_km,
        "n_nsides_indistinguishable": int(len(indist)),
        "per_nside": per_nside_summary,
    }


headline = {
    "hotspot_fraction": HOTSPOT_FRACTION,
    "wilcoxon_p_threshold": WILCOXON_P_THRESHOLD,
    "strategies": {s: strategy_headline(s) for s in STRATEGIES},
    "hj_2007_reference": {
        "australia_overlap_pct_at_0p25deg": 52.2,
        "australia_misidentified_pct_at_0p25deg": 47.8,
        "southafrica_overlap_pct_at_0p25deg": 31.4,
        "southafrica_misidentified_pct_at_0p25deg": 68.6,
        "indistinguishable_at_or_above_deg": 4.0,
        "note": ("H&J 2007 used lat-lon grids at 0.25 deg ~= 25-28 km "
                 "near the equator. Closest HEALPix-NESTED Nside is 256 "
                 f"(~{round(cell_side_km(256), 1)} km cell side)."),
    },
}
with open(OUT_HEADLINE, "w") as f:
    json.dump(headline, f, indent=2, default=str)

print(f"\n--- HEADLINE ---")
print(json.dumps(headline, indent=2, default=str))
print(f"\nsaved {OUT_HEADLINE}")


# %% [markdown]
# ## Print the comparison tables

# %%
print("\nScale-dependence summary (this replication, both strategies):\n")
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
