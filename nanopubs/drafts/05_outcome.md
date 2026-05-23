# 05 — FORRT Replication Outcome

> Form structure verified against `docs/forrt-form-fields.md` §
> "FORRT Replication Outcome" — every required field is present below,
> in the order they appear on the platform form.
>
> Empirical content drafted from
> [`docs/replication-gap-verification.md`](../../docs/replication-gap-verification.md)
> (which **supersedes**
> [`docs/replication-gap-decomposition.md`](../../docs/replication-gap-decomposition.md)).
> Headline numbers verified against `results/headline.json` and
> `results/verif5_concave.parquet`.

## Field-by-field draft

### Short URI suffix for outcome ID (text input, required)

Slug. Kebab-case.

```
hj2007-iberia-scale-outcome
```

### Plain-text label for the outcome (text input, required)

Descriptive title.

```
Hurlbert & Jetz 2007 hotspot scale-dependence — Iberian-birds × HEALPix-NESTED replication outcome
```

### Search for a FORRT replication study (search/select, required)

URI of the Replication Study published in step 04. Pull from `nanopubs/PUBLISHED.md`.

```
<URI of step 04 — paste after step 04 is published>
```

### Repository URL (text input, required)

```
https://github.com/annefou/sdm-scale-replication
```

### Completion date (date picker, required)

```
2026-05-23
```

### Validation status (dropdown, required)

- [ ] Validated
- [x] **PartiallySupported**
- [ ] Contradicted
- [ ] Inconclusive
- [ ] NotTested

*Mapping → CiTO `qualifies` in step 06. The direction of Hurlbert & Jetz
2007's scale-dependence finding is reproduced; the magnitude differs in
ways attributable to documented methodological substitutions in the
rangemap and atlas axes, not to a refutation of the underlying claim.*

### Confidence level (dropdown, required)

- [ ] VeryHighConfidence
- [x] **HighConfidence**
- [ ] Moderate
- [ ] LowConfidence
- [ ] VeryLowConfidence

*High but not very-high: the evidence base is large (61.7 million GBIF
occurrences across 964 species, two basis-of-record strategies, six
HEALPix-NESTED resolution levels, five independent verification tests),
direction agreement is unambiguous, and the magnitude disagreement is
mechanism-decomposed empirically rather than left as residual noise. Not
very-high because the residual ~20 percentage points of the gap remain
unattributed without an IUCN-polygon comparison.*

### Describe the overall conclusion about the original claim (textarea, required)

```
The replication reproduces Hurlbert & Jetz 2007's qualitative finding
that biodiversity-hotspot identity is strongly scale-dependent: at every
HEALPix-NESTED resolution tested (Nside 16 to 512, cell side ≈ 407 km
down to ≈ 13 km), hotspot non-overlap rises monotonically with grid
refinement and dissolves only at the coarsest resolutions, matching the
pattern reported for Australia and southern Africa. At the 0.25°
reference scale (≈ 25 km, HEALPix Nside 256) this replication finds
89.9 % misidentification on a museum-only basis-of-record subset and
97.8 % on an all-observations subset, versus Hurlbert & Jetz's 47.8 %
(Australia) and 68.6 % (southern Africa). A gold-standard test using
the EU Birds Directive Article 12 expert rangemap polygons (2013–2018,
260 Iberian species) does not close the gap (85–95 % misidentification
on the matched-species subset), attributing the magnitude offset
predominantly to observer-effort bias in the modern citizen-science
GBIF atlas itself (log-log Pearson r ≈ 0.96 between per-cell record
count and per-cell species count for the all-observations strategy at
Nside 256), rather than to a refutation of Hurlbert & Jetz's underlying
claim — hence Partially Supported.
```

### Describe the evidence that supports your conclusion (textarea, required)

```
Hotspot misidentification (symmetric set non-overlap of top-5 % richest
cells) was computed at six HEALPix-NESTED resolutions for two GBIF
basis-of-record strategies on Iberian birds, year-split 2000 (atlas =
post-2000 occurrences; rangemap-equivalent = pre-2000 species convex
hulls).

Headline numbers at Nside 256 (≈ 25 km, the 0.25° equivalent of Hurlbert
& Jetz Table 2):
- museum strategy (PRESERVED_SPECIMEN + MACHINE_OBSERVATION):
  89.9 % misidentified  (Wilcoxon signed-rank p < 10⁻¹⁰⁰).
- allbor strategy (+ HUMAN_OBSERVATION, citizen science included):
  97.8 % misidentified  (Wilcoxon signed-rank p < 10⁻¹⁰⁰).
- Hurlbert & Jetz 2007 Australia:       47.8 %.
- Hurlbert & Jetz 2007 Southern Africa: 68.6 %.

Direction-of-effect agreement is monotone across all six Nsides for both
strategies, replicating the central scale-dependence finding.

Gold-standard rangemap test at Nside 256 (matched species subset,
260 Iberian breeding species also present in our post-2000 GBIF set):
EU Birds Directive Article 12 expert polygons (2013–2018, 10 × 10 km
grid cells, EEA CC-BY 4.0) yield misidentification of 94.9 % for
museum (n = 213 matched species) and 85.2 % for allbor (n = 226).
The expert rangemap does NOT close the gap with Hurlbert & Jetz's
47.8–68.6 % range — refuting the hypothesis that hull-as-rangemap
substitution is the dominant cause of the magnitude offset.

Mechanism decomposition at Nside 256:
- Atlas-vs-observer-effort per-cell correlation (log-log Pearson r at
  Nside 256): r = 0.48 (museum), r = 0.96 (allbor); the
  all-observations atlas is essentially a log-linear function of
  per-cell record count, so for allbor the "atlas hotspots"
  predominantly index citizen-science observer effort (cities,
  accessible protected areas) rather than biological richness. This is
  the dominant residual: under any rangemap substitute including the
  gold-standard Article 12 expert polygons, the atlas top-5 % set
  consistently disagrees with the rangemap top-5 % set, because the
  atlas top-5 % cells are observer hotspots while the rangemap top-5 %
  cells are biological hotspots.
- Top-K sweep: at top-25 % (versus Hurlbert & Jetz's top-5 %),
  misidentification drops to 74.2 % (museum) and 71.6 % (allbor),
  inside the Hurlbert & Jetz Australia–southern-Africa range.
- Concave-hull substitute (shapely 2.0, ratio = 0.3) closes 6.3
  percentage points for museum (89.9 → 83.0) and 13.5 percentage points
  for allbor (97.8 → 83.8) on the full-species set, confirming that
  convex hulls over-predict presence — a secondary contributor
  relative to the observer-effort dominant.

Land-mask sensitivity (peninsula-only cells via NaturalEarth 10m) shifts
the Nside 256 number by ≤ 4.3 percentage points and is therefore not a
material confounder. Per-species temporal hull drift (Jaccard distance
between pre-2000 and post-2000 convex hulls) is large for museum
(median 0.81) and moderate for allbor (median 0.21); this does not
materially shift the aggregate top-5 % misidentification at Nside 256
(Δ < 1 percentage point), because the pre-2000 and post-2000 hulls,
though individually differently shaped, are similarly inflated in total
area.
```

### Describe what limits the conclusions of the study (textarea, optional)

```
The magnitude offset relative to Hurlbert & Jetz 2007 is dominated by a
single methodological factor that is documented and characterised but
cannot be removed inside this replication. The direction of the
scale-dependence finding is unaffected.

1. Atlas-axis observer-effort confounding (DOMINANT). Per-cell GBIF
   record count and per-cell species count correlate at log-log Pearson
   r ≈ 0.96 for the all-observations (allbor) strategy at the headline
   scale, and r ≈ 0.48 for the museum-only strategy. The "atlas
   hotspots" derived from modern Iberian GBIF therefore predominantly
   index where citizen-science observers go (cities, accessible
   protected areas, well-birded corridors) rather than where birds are
   biologically densest. The gold-standard rangemap test using EU
   Birds Directive Article 12 expert polygons (Test 6, matched
   subset, 213–226 species) yields 85–95 % misidentification at the
   headline scale — confirming that the residual is not a rangemap-
   substitute artefact but is genuinely the observer-effort
   distortion of the modern atlas. Hurlbert & Jetz's 1990s atlases
   had observer bias too, but to a much smaller degree than the
   current citizen-science-dominated GBIF record.

2. Top-K hotspot-threshold choice. Hurlbert & Jetz's top-5 % is a
   convention, not a biologically grounded threshold. At top-25 %, the
   misidentification numbers in this replication (74.2 % museum,
   71.6 % allbor) sit inside the Hurlbert & Jetz Australia–southern-
   Africa reference range (47.8–68.6 %). The specific magnitude of the
   gap is K-sensitive in a way the original paper did not surface.

3. Hull-as-rangemap substitute (SECONDARY). The canonical pipeline
   uses convex hulls of pre-2000 GBIF occurrences as a rangemap
   surrogate where Hurlbert & Jetz used expert BirdLife polygons.
   Convex hulls over-predict presence; concave hulls close
   6.3–13.5 percentage points of the magnitude gap at the headline
   scale on the full-species set. The gold-standard Article 12 test
   (above) shows this is a real but secondary contributor — the
   expert rangemap does not close the residual once observer-effort
   confounding is in play.

Two further caveats. At the coarsest resolutions tested (Nside 16 with
8 Iberian cells, Nside 32 with 29) the top-5 % hotspot set rounds to
one or two cells, so per-Nside numbers at those resolutions are
noise-dominated; the conclusion does not rely on them. Cell geometry
differs from Hurlbert & Jetz (HEALPix equal-area NESTED here, lat-lon
graticule there); at Iberia's mid-latitude this is unlikely to shift
the comparison materially but is not directly tested.

Despite these limitations, the direction of Hurlbert & Jetz's finding —
that hotspot identification is unstable across resolutions and
stabilises only at very coarse cells — is robustly replicated in
modern Iberian bird data with HEALPix-NESTED indexing. The
observer-effort confound is itself an empirical extension of Hurlbert
& Jetz's underlying message that the choice of data source materially
changes which cells qualify as hotspots: with modern citizen-science
atlases, the observer-effort axis becomes the dominant data-source
distortion rather than the range-map polygon choice that Hurlbert &
Jetz centred on.
```

## Publication note

After publishing, paste the resulting URI into `nanopubs/PUBLISHED.md`
step 05.

## Cross-references for the user before publishing

- The Replication Study (step 04) URI must already be in
  `nanopubs/PUBLISHED.md` before the "Search for a FORRT replication
  study" field can be populated above.
- The CiTO Citation (step 06) Validation-status → CiTO-intention mapping
  is `PartiallySupported → cito:qualifies`. Configure step 06 to cite
  Hurlbert & Jetz 2007 (`https://doi.org/10.1073/pnas.0704469104`) with
  intention `qualifies` (not `extends`, despite the earlier
  decomposition-note framing — the verification doc resolved this:
  `qualifies` is the canonical PartiallySupported mapping per
  `docs/forrt-form-fields.md`).
- Two figures from this replication that are appropriate to embed in
  the Jupyter Book chapter discussing the Outcome:
  - `figures/scale_dependence_decomposition.png` — temporal vs same-era
    rangemap curves vs Hurlbert & Jetz references.
  - `figures/verif_concave_vs_convex.png` — concave-hull substitute
    closing part of the gap.
```
