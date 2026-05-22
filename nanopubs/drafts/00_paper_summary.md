# Paper summary

> This is a working scratchpad for the paper-analysis phase. The output of this file feeds the Quote / AIDA / Claim drafts. It is not itself a nanopub.

**Reference paper:** Species richness, hotspots, and the scale dependence of range maps in ecology and conservation

**DOI:** 10.1073/pnas.0704469104

**Authors:** Allen H. Hurlbert and Walter Jetz

**Year:** 2007 (PNAS 104(33): 13384-13389)

## Headline claim

The single sentence in the paper that this replication tests.

> Aggregating expert-drawn range maps onto grids finer than ~2° (~200 km) mischaracterises the spatial pattern of species richness so severely that **up to two-thirds of the resulting "biodiversity hotspots" are misidentified** relative to atlas-survey ground truth.

The verbatim form is in `01_quote.md` (Abstract sentence, page 13384). The "two-thirds misidentified" figure is the headline number — Table 2 on page 13387 makes it concrete: at 0.25° resolution, only **31.4%** of range-map-derived hotspots in southern Africa (n = 70) and **52.2%** in Australia (n = 249) were also identified as hotspots by atlas data. The "two-thirds" framing in the abstract refers to the southern Africa figure (100% − 31.4% ≈ 68.6%).

## Methodology summary

- **Data sources:** Expert-opinion bird **range maps** from regional sources (*Handbook of the Birds of the World*, *The Birds of Africa*, *Birds of Australia*, *The New Atlas of Australian Birds*, *The Atlas of Southern African Birds*) versus **atlas survey data** at 0.25° lat-lon grain for two continents: Australia (Australian bird atlas, 25 × 25 km ≈ 625 km² equal-area cells) and southern Africa (southern African Bird Atlas, 0.25° lat-lon squares across Mozambique, South Africa, Swaziland, Lesotho, Namibia, Zimbabwe). Only breeding ranges; non-passerines and passerines from separate sources; nightjars, owls, raptors, shorebirds excluded for detection-bias reasons.
- **Sample sizes:** **399 species** from Australia and **435 species** from southern Africa (834 species total). Atlas analysis at 0.25° used **n = 2,021 grid cells** for Australia and **n = 1,384** for southern Africa (well-surveyed cells with ≥ 20 surveys per pixel, with a half-pixel constraint at coarser scales).
- **Analysis:** Range maps were overlaid on the 0.25° atlas grid to compute, per species, **range occupancy** = (atlas cells with the species observed) / (atlas cells inside the range map). Atlas and range-map data were then aggregated to coarser resolutions — **0.25°, 0.5°, 1°, 2°, 4°, 8°** — and richness was compared at each scale (Wilcoxon signed-rank test). Hotspots were defined as the **5% richest grid cells** at each resolution; the per-scale overlap between range-map-hotspots and atlas-hotspots was tabulated in Table 2.
- **Headline numerical results:**
  - Average range occupancy: 53% in Australia, 64% in southern Africa at 0.25° (i.e. species were absent from ~36-47% of cells inside their range map).
  - Hotspot overlap (Table 2) at 0.25°: **52.2% Australia (n=249), 31.4% southern Africa (n=70)** — i.e. ~48% / ~69% misidentified. Overlap rises with grain: at 1° it is 60% (Australia) / 77.8% (southern Africa); range-map and atlas richness become statistically indistinguishable at ≥ 4°.
  - Protected-area coverage: only **11.6% (8 of 69)** of range-map hotspots in southern Africa at 0.25° overlapped IUCN protected areas, versus **>20% (14 of 69)** of atlas hotspots — i.e. range maps overstate how well existing reserves cover diversity.

## Replication design choice

Which of the three FORRT Study Types fits this replication?

- [ ] **Reproduction Study** — direct reproduction: same methodology, same tools.
- [x] **Replication Study** — replication with different methodology or conditions.
- [ ] **Reproduction/Replication Study** — both.

**Justification.** Per the locked Phase 1 design decisions (`00_design_decisions.md`), this chain runs a Replication only. The original used WWF / Handbook expert-drawn range maps + two regional bird atlases on **lat-lon grids** (0.25°-8°) circa 2007. The replication uses **modern GBIF occurrence records** (point data, not range maps as a primary source) and **modern IUCN range maps** on **HEALPix-NESTED substrates** at multiple resolutions — an equal-area, sphere-aware DGGS that removes the cell-area distortion intrinsic to lat-lon grids and aligns with the project's DGGS / DOMAIN.md conventions. The empirical question is whether H&J's scale-dependence pattern (two-thirds misidentification at fine grains, convergence at ≥ 2°) re-emerges under these substantially different data and substrate choices, and at what HEALPix `Nside` level the misidentification onsets.

## Notes for downstream drafts

- **Taxon scope.** H&J 2007 is **birds only** (no mammals, no other taxa) — despite the abstract opening "Most studies examining continental-to-global patterns of species richness rely on the overlaying of extent-of-occurrence range maps." The AIDA and Replication Study "what is reproduced" fields must mirror this: the original claim is bird-specific. If the replication uses a non-bird taxon, that is a legitimate scope-shift to flag in the Outcome's Deviations field.
- **Region scope.** Two regional studies (Australia + southern Africa), not a global analysis. The "two-thirds" abstract figure is dominated by the southern Africa result (31.4% overlap → ~68.6% misidentified at 0.25°). Australia at 0.25° was ~48% misidentified — closer to "half" than "two-thirds". The abstract phrase "up to two-thirds" intentionally quotes the worse of the two regions.
- **Hotspot definition.** "Hotspot" in H&J 2007 = the **5% richest grid cells** at a given resolution. This is a *relative-rank* hotspot definition (not a fixed-threshold or rarity-weighted one). Downstream AIDA / Claim wording must preserve this — "hotspot" is operationally defined and varies by grain.
- **Misidentification metric.** The 2/3 figure is **non-overlap of the top-5% sets**, i.e. range-map-hotspots that are *not* atlas-hotspots (and vice versa). This is symmetric set-difference, not asymmetric omission or commission. H&J do separately quantify range-map **commission** (species predicted present but absent from atlas cells inside the range, mean 36-47%) and protected-area coverage — but the headline "two-thirds" refers to the hotspot-set overlap specifically.
- **Resolution where pattern dissolves.** H&J state range-map and atlas richness become statistically indistinguishable (Wilcoxon, P > 0.10) at ≥ 4°, and within 3-5% at 2°. The replication should report whether the analogous HEALPix Nside threshold matches this ~2-4° (≈200-400 km) onset.
- **Symbol.** The abstract uses Unicode "∼" (U+223C TILDE OPERATOR), not ASCII "~" — preserved verbatim in `01_quote.md`.
