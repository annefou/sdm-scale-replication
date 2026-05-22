# Snakefile — orchestrates the H&J 2007 scale-replication pipeline.
#
# Four notebooks, four rules:
#
#   01_data_download  -> data/gbif/{modern,historical}.zip + data/raw/sources.json
#   02_data_clean     -> data/clean/richness_per_nside.nc + species_eoo_polygons.parquet
#   03_analysis       -> results/scale_dependence.parquet + hotspot_cells.parquet + headline.json
#   04_figures        -> figures/main_result.png + iberia_hotspots_nside128.png
#
# Usage:
#   pixi run snakemake --cores 1           # run everything
#   pixi run snakemake --cores 1 -n        # dry run
#   pixi run snakemake --cores 1 download  # only fetch GBIF zips
#   pixi run snakemake --cores 1 clean     # 01 + 02
#   pixi run snakemake --cores 1 analysis  # 01 + 02 + 03
#   pixi run snakemake --cores 1 figures   # 01 + 02 + 03 + 04

NOTEBOOKS = "notebooks"
DATA = "data"
RESULTS = "results"
FIGURES = "figures"


rule all:
    input:
        f"{FIGURES}/main_result.png",
        f"{FIGURES}/iberia_hotspots_nside128.png",
        f"{RESULTS}/scale_dependence.parquet",
        f"{RESULTS}/headline.json",


# ---------- 01: Data download ----------
# Self-contained: fetches modern (post-2000) and historical (pre-2000)
# GBIF Iberian-bird occurrence zips. Three modes (see notebook):
#   1. Pre-minted GBIF keys hardcoded in the notebook -> fetch zip by URL.
#   2. GBIF_USER/GBIF_PWD/GBIF_EMAIL env vars -> mint a fresh download.
#   3. Synthetic demo fallback -> deterministic Iberian bird data.
# The source registry at data/raw/sources.json is always written and
# is the rule's declared output.
rule download:
    output:
        f"{DATA}/raw/sources.json",
        f"{DATA}/gbif/birds_iberia_modern.zip",
        f"{DATA}/gbif/birds_iberia_historical.zip",
    log:
        f"{RESULTS}/logs/01_data_download.log",
    shell:
        "mkdir -p $(dirname {log}) && "
        "cd " + NOTEBOOKS + " && "
        "jupytext --to notebook 01_data_download.py && "
        "jupyter execute --inplace 01_data_download.ipynb 2>&1 | tee ../{log}"


# ---------- 02: Data clean ----------
# Bins both GBIF datasets onto HEALPix-NESTED at Nside in
# {16, 32, 64, 128, 256, 512}. Modern -> per-cell richness from points.
# Historical -> per-species convex-hull EOO -> per-cell richness from
# polygons. Persists one NetCDF file with one group per Nside.
rule clean:
    input:
        f"{DATA}/gbif/birds_iberia_modern.zip",
        f"{DATA}/gbif/birds_iberia_historical.zip",
    output:
        richness = f"{DATA}/clean/richness_per_nside.nc",
        eoo = f"{DATA}/clean/species_eoo_polygons.parquet",
        report = f"{DATA}/clean/clean_report.json",
    log:
        f"{RESULTS}/logs/02_data_clean.log",
    shell:
        "mkdir -p $(dirname {log}) {DATA}/clean && "
        "cd " + NOTEBOOKS + " && "
        "jupytext --to notebook 02_data_clean.py && "
        "jupyter execute --inplace 02_data_clean.ipynb 2>&1 | tee ../{log}"


# ---------- 03: Analysis ----------
# Per Nside: top-5% hotspot set overlap (H&J Table 2) + Wilcoxon signed-
# rank test on per-cell richness (H&J's >=4° indistinguishability check).
rule analysis:
    input:
        f"{DATA}/clean/richness_per_nside.nc",
    output:
        scale = f"{RESULTS}/scale_dependence.parquet",
        hotspots = f"{RESULTS}/hotspot_cells.parquet",
        headline = f"{RESULTS}/headline.json",
    log:
        f"{RESULTS}/logs/03_analysis.log",
    shell:
        "mkdir -p $(dirname {log}) " + RESULTS + " && "
        "cd " + NOTEBOOKS + " && "
        "jupytext --to notebook 03_analysis.py && "
        "jupyter execute --inplace 03_analysis.ipynb 2>&1 | tee ../{log}"


# ---------- 04: Figures ----------
# Two figures: scale-dependence main_result.png + Iberia hotspot map.
rule figures:
    input:
        scale = f"{RESULTS}/scale_dependence.parquet",
        hotspots = f"{RESULTS}/hotspot_cells.parquet",
        richness = f"{DATA}/clean/richness_per_nside.nc",
    output:
        main_png = f"{FIGURES}/main_result.png",
        main_pdf = f"{FIGURES}/main_result.pdf",
        map_png = f"{FIGURES}/iberia_hotspots_nside128.png",
        map_pdf = f"{FIGURES}/iberia_hotspots_nside128.pdf",
    log:
        f"{RESULTS}/logs/04_figures.log",
    shell:
        "mkdir -p $(dirname {log}) " + FIGURES + " && "
        "cd " + NOTEBOOKS + " && "
        "jupytext --to notebook 04_figures.py && "
        "jupyter execute --inplace 04_figures.ipynb 2>&1 | tee ../{log}"
