# 04 — FORRT Replication Study

> Run the pre-flight checklist in `docs/forrt-form-fields.md` § Pre-flight checklist before drafting.
>
> **Verify code first:** read the actual reproduction script in `notebooks/03_analysis.py` before writing the methodology field. See `docs/verify-before-drafting.md`.

## Field-by-field draft

### Short URI suffix for study ID (text input, required)

Slug. Use kebab-case.

```
hj2007-iberia-healpix-study
```

### Label/name of replication study (text input, required)

Human-readable title.

```
Replication of Hurlbert & Jetz 2007 hotspot scale-dependence in Iberian birds on a HEALPix-NESTED substrate
```

### Study type (dropdown, required)

- [ ] Reproduction Study — direct reproduction: same methodology, same tools.
- [x] **Replication Study** — replication with different methodology or conditions.
- [ ] Reproduction/Replication Study — both.

*Different data (modern GBIF + EU Article 12, not 2007-era WWF/Handbook
expert maps + regional atlases), different substrate (HEALPix-NESTED
equal-area, not lat-lon), different region (Iberia, not Australia /
southern Africa). Per the locked design decisions in
`nanopubs/drafts/00_design_decisions.md`, this is a Replication only —
no Reproduction component.*

### Search for a FORRT claim (search/select, required)

URI of the Claim published in step 03. Pull from `nanopubs/PUBLISHED.md`.

```
<URI of step 03 (FORRT Claim) — paste after step 03 is published>
```

### Describe what part of the claim is reproduced/replicated (textarea, required)

The **scope** of the claim being tested. Which aspect, what's in/out of scope. NOT methodology. NOT results. See `docs/pico-study-outcome-levels.md`.

```
Scope: the scale-dependence of bird species-richness hotspot
identification. The replication tests whether Hurlbert & Jetz's central
finding — that range-map-derived richness hotspots disagree with
finer-resolution survey-derived hotspots, with the disagreement growing
as the grid is refined and dissolving only at coarse grain — re-emerges
for a different region (the Iberian peninsula) under modern occurrence
data and an equal-area sphere-aware substrate.

In scope: the top-5%-richest-cells hotspot definition; the symmetric
non-overlap between range-map-derived and atlas-derived hotspot sets;
how that non-overlap varies across a spatial-resolution ladder; and the
coarse-grain resolution at which the two richness surfaces become
statistically indistinguishable.

Out of scope: Hurlbert & Jetz's secondary findings (per-species range
occupancy / commission rates, and protected-area coverage of hotspots);
and all non-bird taxa — the original claim and this replication are
bird-only.
```

### Describe how the claim is reproduced/replicated (textarea, required)

The **method** in plain prose. Read `notebooks/03_analysis.py` and any config files first. NOT exact numerical results.

```
Iberian bird occurrence records (Spain, Portugal, Andorra, Gibraltar)
were obtained from GBIF as two basis-of-record strategies, each with a
citable download DOI: a "museum" strategy (PRESERVED_SPECIMEN +
MACHINE_OBSERVATION; GBIF download DOI 10.15468/dl.r8pcat) and an
"all-observations" strategy (additionally HUMAN_OBSERVATION, i.e.
citizen-science records; GBIF download DOI 10.15468/dl.e9xv7p).

Records were year-split at 2000. Post-2000 occurrences form the
atlas-equivalent layer (per-cell richness = number of distinct species
observed in the cell). Pre-2000 occurrences form the range-map-
equivalent layer (per species, the convex hull of its occurrences,
whose cell coverage contributes to per-cell range-map richness). Both
layers are binned onto a HEALPix-NESTED ladder at Nside 16, 32, 64,
128, 256 and 512 (cell side approximately 407 km down to 13 km,
bracketing Hurlbert & Jetz's 0.25-8 degree range) using the geographic,
WGS84-aware healpix-geo library, NESTED ordering throughout.

At each resolution, hotspots are the top-5% richest cells (Hurlbert &
Jetz's definition); the headline metric is the symmetric non-overlap of
the atlas-derived and range-map-derived hotspot sets. A Wilcoxon
signed-rank test on the paired per-cell richness provides the
dissolution criterion (statistical indistinguishability at P > 0.10,
matching the original's >= 4 degree threshold).

A verification battery tests robustness: a peninsula-only land mask
(NaturalEarth 10m); a top-K hotspot-threshold sweep (1-25%); a
per-species pre/post convex-hull drift measure (Jaccard distance); an
atlas-richness-versus-observer-effort (per-cell record count)
correlation; and two tighter range-map surrogates — a concave hull,
and EU Birds Directive Article 12 expert distribution polygons (EEA,
2013-2018, 10 km grid, CC-BY 4.0; 260 Iberian breeding species) used as
a gold-standard cross-check on the convex-hull surrogate.

The full pipeline is a Snakemake workflow (download -> clean ->
analysis -> figures) reproducible from a fresh checkout; the
verification battery lives in companion diagnostic notebooks.
```

### Describe any deviations from original methodology (textarea, optional)

What's different from the original method. Verify against the actual code, don't guess.

```
Hurlbert & Jetz 2007 overlaid expert-drawn bird range maps (Handbook of
the Birds of the World; regional atlases) on two structured regional
bird-atlas surveys (Australia, southern Africa) on lat-lon grids at
0.25-8 degrees, circa 2007. This replication deviates on four axes:

- Range-map layer: convex hulls of GBIF occurrences (a surrogate),
  cross-checked against EU Article 12 expert distribution polygons —
  not WWF / Handbook expert range maps.
- Atlas layer: modern GBIF occurrence richness (post-2000, citizen-
  science-dominated for the all-observations strategy) — not a
  dedicated structured atlas survey with controlled effort.
- Substrate: HEALPix-NESTED equal-area cells — not a lat-lon graticule,
  removing the cell-area distortion intrinsic to lat-lon grids.
- Region and era: the Iberian peninsula, 2013-2024 GBIF / 2013-2018
  Article 12 — not Australia or southern Africa, circa 2007.

The two-basis-of-record design (museum vs all-observations) is an
addition to the original: it probes observer-effort sensitivity, a
dimension unavailable to Hurlbert & Jetz before citizen-science data
dominated occurrence records. The consequences of these deviations for
the headline number are quantified in the linked Replication Outcome's
Evidence and Limitations fields.
```

### Search keywords (Wikidata) (multi-select, optional)

Provide labels (not QIDs) — the Wikidata search picks up labels.

- species richness
- biodiversity hotspot
- range map
- HEALPix
- GBIF

### Search discipline (Wikidata) (search, optional)

Provide labels.

- macroecology
- conservation biology
- biogeography

## Publication note

After publishing, paste the resulting URI into `nanopubs/PUBLISHED.md` step 04.
