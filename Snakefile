# Snakefile — orchestrates the H&J 2007 scale-replication pipeline
# (two BoR strategies: museum + allbor, year-split at cleaning stage).
#
# Four notebooks, four rules:
#
#   01_data_download  -> data/gbif/birds_iberia_{museum,allbor}.zip
#                        + data/raw/sources.json
#   02_data_clean     -> data/clean/richness_{museum,allbor}.nc
#                        + species_eoo_polygons.parquet (with strategy col)
#                        + clean_report.json
#   03_analysis       -> results/scale_dependence.parquet (long form, with
#                        strategy col) + hotspot_cells.parquet
#                        + headline.json (per-strategy)
#   04_figures        -> figures/main_result.{png,pdf}
#                        + iberia_hotspots_nside128.{png,pdf} (2x2 grid)
#
# Usage:
#   pixi run snakemake --cores 1            # run everything
#   pixi run snakemake --cores 1 -n         # dry run
#   pixi run snakemake --cores 1 download   # only fetch GBIF zips
#   pixi run snakemake --cores 1 clean      # 01 + 02
#   pixi run snakemake --cores 1 analysis   # 01 + 02 + 03
#   pixi run snakemake --cores 1 figures    # 01 + 02 + 03 + 04

NOTEBOOKS = "notebooks"
DATA = "data"
RESULTS = "results"
FIGURES = "figures"

STRATEGIES = ["museum", "allbor"]


rule all:
    input:
        f"{FIGURES}/main_result.png",
        f"{FIGURES}/iberia_hotspots_nside128.png",
        f"{RESULTS}/scale_dependence.parquet",
        f"{RESULTS}/headline.json",


# ---------- 01: Data download ----------
# Self-contained: fetches two strategy GBIF Iberian-bird occurrence zips,
# one per BoR strategy (museum vs allbor). Three modes (see notebook):
#   1. Pre-minted GBIF keys (Strategy A defaults to DOI 10.15468/dl.r8pcat).
#   2. GBIF_USER/GBIF_PWD/GBIF_EMAIL env vars -> mint via the GBIF API.
#   3. Per-strategy synthetic demo fallback (deterministic).
# The source registry at data/raw/sources.json is always written.
rule download:
    output:
        f"{DATA}/raw/sources.json",
        f"{DATA}/gbif/birds_iberia_museum.zip",
        f"{DATA}/gbif/birds_iberia_allbor.zip",
    log:
        f"{RESULTS}/logs/01_data_download.log",
    shell:
        "mkdir -p $(dirname {log}) && "
        "cd " + NOTEBOOKS + " && "
        "jupytext --to notebook 01_data_download.py && "
        "jupyter execute --inplace 01_data_download.ipynb 2>&1 | tee ../{log}"


# ---------- 02: Data clean ----------
# Per strategy: load the zip, split rows by year (year>=2000 = atlas-eq,
# year<2000 = rangemap-eq via per-species convex-hull EOO), then bin both
# onto HEALPix NESTED at Nside in {16,32,64,128,256,512}. One NetCDF per
# strategy (groups by Nside); one parquet of EOO polygons across both
# strategies; one report JSON.
rule clean:
    input:
        f"{DATA}/gbif/birds_iberia_museum.zip",
        f"{DATA}/gbif/birds_iberia_allbor.zip",
    output:
        museum_nc = f"{DATA}/clean/richness_museum.nc",
        allbor_nc = f"{DATA}/clean/richness_allbor.nc",
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
# Per (strategy, Nside): top-5% hotspot set overlap (H&J Table 2 analogue)
# + Wilcoxon signed-rank test on per-cell richness pairs. Outputs long-form
# parquets and a per-strategy headline JSON.
rule analysis:
    input:
        f"{DATA}/clean/richness_museum.nc",
        f"{DATA}/clean/richness_allbor.nc",
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
# main_result: two-curve misidentified% vs Nside with H&J references.
# iberia_hotspots_nside128: 2x2 grid (rows = strategies, cols =
# atlas/rangemap). Synthetic strategies carry a translucent banner.
rule figures:
    input:
        scale = f"{RESULTS}/scale_dependence.parquet",
        hotspots = f"{RESULTS}/hotspot_cells.parquet",
        museum_nc = f"{DATA}/clean/richness_museum.nc",
        allbor_nc = f"{DATA}/clean/richness_allbor.nc",
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
