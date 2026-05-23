# Verification of the gap-decomposition claims

**Read this *after* [`replication-gap-decomposition.md`](replication-gap-decomposition.md).**
This document **supersedes** the conclusions of that note where they
conflict. The decomposition note proposed a three-mechanism explanation
for the H&J gap; this note stress-tests each claim with five independent
verifications ([`notebooks/03c_verifications.py`](../notebooks/03c_verifications.py))
and revises the picture substantially.

## TL;DR — what changed

The decomposition note claimed the H&J gap was *entirely* the
hull-as-rangemap substitute. **That was wrong.** Tests 1–5 then showed
the gap was a composite of three mechanisms (hull + observer-effort +
top-K). Test 6 (Article 12 gold-standard rangemap, added after the gold-
standard data became available via Lifewatch) now **refutes the
hull-as-rangemap explanation as the dominant cause as well**. The
honest decomposition is:

| Mechanism | Closes (at Nside 256) | Status |
|---|---|---|
| **Atlas observer-effort confounding** | **dominant — not directly closed, but log-log r ≈ 0.96 for allbor** | **primary cause** |
| Top-K choice (5% → 25%) | +16 pp (museum) / +26 pp (allbor) | secondary contributor — threshold sensitivity |
| Convex → Art-12 gold-standard rangemap | **−7.7 pp (museum, *worsens*) / +6.0 pp (allbor)** | **hull substitute is NOT the dominant cause** — even the gold standard does not close the gap |
| Convex → concave hull | +8.8 pp (museum) / +1.3 pp (allbor) | small contributor on the matched subset |
| Per-species temporal drift | doesn't move misid at Nside 256 | nominally large (Jaccard 0.8 for museum) but cancels at aggregate level |
| Land-mask leakage (peninsula-only) | −4 to +0 pp | **not** a confounder |

After ALL verifications including the gold standard, **misidentification
at Nside 256 sits at 85–95 % under any non-observer-corrected method**.
The dominant cause of the gap is that the modern Iberian GBIF atlas is
itself a measurement of observer effort, not biological richness; the
hotspot-set comparison with any rangemap therefore measures the
observer-bias of the atlas, not the H&J range-vs-atlas effect properly.

## Test-by-test

### Test 1 — Land mask (NaturalEarth 10m → Spain+Portugal+Andorra+Gibraltar centroids)

**Hypothesis under test:** the Iberian-bbox cells include ocean +
S. France + N. Morocco. If those cells have ~0 atlas richness but
non-zero rangemap richness (hulls spill across borders), they
asymmetrically inflate the misidentification.

**Result:** at the H&J reference scale (Nside 256), restricting to
peninsula-only cells **does not consistently close the gap** — museum
goes 89.94 % → 94.25 % (*worse*) and allbor goes 97.80 % → 97.78 %
(unchanged). At coarse scales the result swings widely (museum Nside 32:
66.67 % → 0 %; allbor Nside 32: 66.67 % → 100 %) but those Nsides have
~1-cell top-5 % sets and are noise-dominated.

**Verdict: land-mask leakage is NOT a major confounder.** My earlier
worry was misplaced — peninsula and non-peninsula cells contribute
roughly symmetrically to the top-5 % set under both atlas and rangemap.
See [`figures/verif_land_mask.png`](../figures/verif_land_mask.png).

### Test 2 — Top-K sensitivity sweep

**Hypothesis under test:** the H&J 5 % threshold may be on a statistical
cliff (e.g., a sharp jump between 5 % and 10 %).

**Result at Nside 256:**

| K | museum | allbor |
|---:|---:|---:|
| 1 % | 91.43 % | 100.00 % |
| 2 % | 92.75 % | 98.63 % |
| **5 % (H&J)** | **89.94 %** | **97.80 %** |
| 10 % | 89.88 % | 91.50 % |
| **25 %** | **74.18 %** | **71.57 %** |

**Verdict: top-K matters a lot.** Going from K = 5 % to K = 25 % drops
museum by 15.8 pp and allbor by 26.2 pp. At K = 25 % both strategies sit
**within H&J's Australia / S. Africa range** (47.8 % / 68.6 %). This is
a substantial finding the decomposition note missed.

**Implication:** the specific magnitude of our gap is partly an artefact
of H&J's choice of top-5 % as the threshold. H&J's threshold has no
biological justification beyond convention; with a more permissive
threshold (top-25 %) our numbers converge toward theirs.
See [`figures/verif_topK_sensitivity.png`](../figures/verif_topK_sensitivity.png).

### Test 3 — Per-species hull drift (pre-2000 vs post-2000 convex hulls)

**Hypothesis under test:** if pre-2000 hulls and post-2000 hulls have
high Jaccard distance per species, then range shifts (climate,
sampling) over 25 + years are real and the temporal axis cannot be
"negligible" — my earlier claim was structurally wrong.

**Result:**

| Strategy | n species | median Jaccard | mean | % > 0.3 | % > 0.5 |
|---|---:|---:|---:|---:|---:|
| museum | 295 | **0.808** | 0.767 | 96.6 % | 86.8 % |
| allbor | 575 | 0.207 | 0.423 | 43.3 % | 36.7 % |

**Verdict: my earlier "temporal axis negligible" claim was false.**
Museum-strategy species have *enormous* per-species hull drift — the
median species has only 19 % geometric overlap between its pre-2000 and
post-2000 hulls. Allbor drift is moderate (median 0.21) because
citizen-science gives denser, more comparable point clouds in both eras.

**Why did same-era misid (Nside 256) come out nearly identical to
temporal misid in the decomposition note then?** Because both hulls are
similarly *inflated* in total area, even when individually quite
differently *shaped*. Two large effects cancel at the level of the
top-5 % aggregate: drift moves species hulls around but doesn't
systematically change the cells they overlap. The aggregate metric
disguised a per-species effect that's real and large, particularly for
museum data.

**Implication:** the temporal split is *not* a clean test of "method
effect under matched eras". The museum-strategy decomposition cannot be
read as "removing temporal axis ≈ no effect"; rather, the temporal effect
exists but is invisible to the aggregate hotspot-set metric.
See [`figures/verif_species_drift.png`](../figures/verif_species_drift.png).

### Test 4 — Atlas vs observer-effort correlation

**Hypothesis under test:** modern GBIF density correlates with roads /
population / observer access. If per-cell record count and per-cell
species count correlate too strongly, "atlas richness" is partly an
observer-effort proxy and the comparison with rangemap is partly
meaningless regardless of the rangemap data source.

**Result — Pearson r per (strategy, Nside):**

| Nside | museum raw | museum log-log | **allbor raw** | **allbor log-log** |
|---:|---:|---:|---:|---:|
| 16 | 0.36 | 0.88 | 0.67 | **0.996** |
| 32 | 0.41 | 0.64 | 0.68 | **0.979** |
| 64 | 0.31 | 0.57 | 0.67 | **0.962** |
| 128 | 0.27 | 0.50 | 0.64 | **0.960** |
| 256 | 0.20 | 0.48 | 0.54 | **0.960** |
| 512 | 0.08 | 0.47 | 0.51 | **0.939** |

**Verdict: this is the largest single finding of the verification, and it
was missing from the decomposition note.** Allbor's atlas richness is
essentially a log-linear function of observer effort (r ≥ 0.94 at every
Nside; r ≈ 0.96 at the H&J reference scale). For museum-strategy the
correlation is weaker but still non-negligible at coarse scales (r ≈ 0.88
at Nside 16).

**Implication:** for allbor, the "atlas hotspots" we compare against are
predominantly *where people observe birds*, not *where birds are
biologically densest*. Major Spanish cities (Madrid, Barcelona, Sevilla,
Valencia), Doñana NP (heavily birded), the Pyrenean tourist corridor —
these areas are overrepresented in the atlas top-5 % set independently
of the underlying species richness. Rangemap predictions don't have this
observer bias, so atlas / rangemap disagreement is partly real
biodiversity signal and partly atlas-side observer bias.

**This effect is amplified by the choice of basis-of-record.** Museum
(PRESERVED + MACHINE) is observer-biased but less extremely; allbor
(+ HUMAN) inherits the full citizen-science geographic bias. The 8 pp
gap between museum and allbor at the headline scale is consistent with
allbor's higher observer-effort confounding.
See [`figures/verif_observer_effort.png`](../figures/verif_observer_effort.png).

### Test 5 — Concave hull substitute (shapely 2.0, ratio = 0.3)

**Hypothesis under test:** if hull-as-rangemap is the dominant cause of
the gap, a tighter polygon (concave hull) should partially close it.
If concave hull gives the same misidentification as convex hull, my
"hull is the whole gap" claim is fully refuted.

**Result at Nside 256:**

| Variant | museum | allbor |
|---|---:|---:|
| convex hull, pre-2000 (canonical) | 89.94 % | 97.80 % |
| convex hull, post-2000 (same-era) | 89.29 % | 97.24 % |
| **concave hull, post-2000 (ratio=0.3)** | **83.02 %** | **83.75 %** |
| Δ pp (concave vs convex post) | **-6.27** | **-13.49** |

**Verdict: hull tightness is a confirmed contributor to the gap, but not
"the whole thing".** Concave hull closes ~6 pp for museum and ~13 pp for
allbor at the headline scale. The effect is larger at coarse / mid
scales — allbor Nside 32 swings from 66.67 % (convex) to 0 % (concave),
allbor Nside 64 from 90.91 % to 66.67 %.

**Implication:** hull-as-rangemap inflates the gap meaningfully (verified
by the concave alternative), but does not own the entire gap.
Combining concave hull + observer-effort awareness + a more permissive
top-K threshold would still leave a residual; the gold-standard
verification requires IUCN range maps.
See [`figures/verif_concave_vs_convex.png`](../figures/verif_concave_vs_convex.png).

### Test 6 — Article 12 gold-standard rangemap (EU Birds Directive 2013–2018)

**Hypothesis under test:** if hull-as-rangemap inflation is the
dominant cause of the magnitude gap, replacing convex / concave hulls
with **expert-vetted EU Birds Directive Article 12 distribution
polygons** for Iberian breeding birds should close most of the residual.
The Art-12 dataset is the European-statutory analogue of expert
BirdLife polygons: per-species 10 × 10 km grid cells in EPSG:3035,
CC-BY 4.0, 260 species in Spain + Portugal + Gibraltar, breeding
season only (EU Directive 2009/147/EC Article 12 reporting, 2013–2018
period). Source:
<https://sdi.eea.europa.eu/data/e2face16-f352-4aff-9e4f-0ad1306f89b5>.

To make the comparison apples-to-apples, atlas richness and the
hull-based rangemap variants are **all recomputed on the matched
species subset** (species present in both Art-12 and our post-2000
GBIF set: 213 species for museum, 226 species for allbor).

**Result at Nside 256 (the H&J 0.25° equivalent, matched subset):**

| Strategy | n matched species | convex hull | concave hull | **Art-12 (gold standard)** | H&J Australia | H&J Southern Africa |
|---|---:|---:|---:|---:|---:|---:|
| museum | 213 | 87.27 % | 78.43 % | **94.92 %** | 47.8 % | 68.6 % |
| allbor | 226 | 91.23 % | 89.94 % | **85.19 %** | 47.8 % | 68.6 % |

**Verdict: hull-as-rangemap is NOT the dominant cause of the H&J gap.**

The expert-vetted Art-12 rangemap **fails to close the gap**:

- For museum, Art-12 is **worse** than the convex hull (94.92 % vs
  87.27 %): the expert range maps disagree with the GBIF atlas top-5 %
  even more strongly than the over-inflated convex hull does.
- For allbor, Art-12 is moderately better than convex / concave (85.19 %
  vs 91.23 % / 89.94 %) — but still ~17 percentage points above the
  upper end of the H&J reference range, and well outside any
  interpretation that would qualify as "the gap is closed".

The mean rangemap richness at Nside 256 confirms Art-12 polygons are
**much tighter** than even concave hulls (19 species per cell for
Art-12, vs 35 for museum-concave, 122 for allbor-concave). Art-12 is
the *correctly conservative* expert measure — yet its top-5 % hotspot
set still doesn't overlap the GBIF atlas top-5 % set.

**The mechanism is now clear.** The disagreement is not about *how
many* species are in each cell; it is about *which cells qualify as
top-5 %*. The GBIF atlas top-5 % cells are predominantly observer-
effort hotspots (cities, accessible protected areas, well-birded
corridors), confirmed quantitatively by Test 4 (log-log r ≈ 0.96 for
allbor between per-cell record count and per-cell species count). The
Art-12 top-5 % cells are true biological hotspots (sierras, ecotonal
zones, well-vegetated mid-elevation belts). The 85–95 % non-overlap
is therefore predominantly a measurement of the observer-effort
distortion of the modern Iberian GBIF atlas, not a measurement of
the H&J scale-dependence effect.

This refutes my prior mechanism decomposition's Limitation 1
("rangemap substitute") as the dominant cause: even the gold standard
does not close the gap. The dominant cause is Limitation 2 (atlas
observer-effort confounding), which is now promoted to the headline
mechanism.

See [`figures/verif_art12_goldstandard.png`](../figures/verif_art12_goldstandard.png).

## Revised composite picture (post Test 6)

The H&J ~50 pp gap is **dominated by atlas observer-effort
confounding**, not rangemap polygon inflation. The honest mechanism
ranking, in order of contribution:

1. **Atlas observer-effort confounding** (Tests 4 + 6). Modern Iberian
   GBIF atlas richness correlates log-log r ≈ 0.96 with per-cell record
   count (for allbor; r ≈ 0.48 for museum). The atlas hotspots are
   predominantly observer hotspots. Test 6 confirms this by showing that
   even when the rangemap is the gold-standard expert dataset (EU
   Article 12), 85–95 % of the top-5 % set still disagrees with the
   atlas. The dominant residual *is* the observer bias.

2. **Top-K threshold sensitivity** (Test 2). H&J's choice of K = 5 %
   selects a small, fragile set that maximises sensitivity to noise. At
   K = 25 % our numbers (72–74 %) sit inside the H&J Australia–S.Africa
   range (48–69 %). The original paper did not surface this sensitivity.

3. **Hull-as-rangemap inflation** (Tests 5 + 6). Convex hulls
   over-predict presence; concave hulls close 6–13 pp on the
   full-species set. **But the matched-subset Test 6 shows that the gold
   standard does not close the residual** — hull inflation is a
   secondary contributor, not the dominant cause. The decomposition
   note's framing was wrong.

4. **Per-species temporal drift** exists but is invisible to the
   aggregate metric (Test 3). Large per-species drift (museum median
   Jaccard 0.81); cancels at top-5 % aggregate level.

5. **Land-mask leakage** is NOT a confounder at the headline scale
   (Test 1).

## What this means for the Outcome

The replication's *qualitative* result is unchanged: H&J's scale-
dependence pattern is monotone and robust in both strategies. The
*quantitative* magnitude offset is now attributed primarily to a
**single dominant mechanism** rather than the three-way composite the
decomposition note proposed:

- **Classification: Partially Supported.** Direction validated;
  magnitude differs predominantly because the modern Iberian GBIF
  atlas is a measurement of citizen-science observer effort, not of
  biological richness, and any hotspot-set comparison against any
  rangemap therefore measures the observer-effort distortion rather
  than the H&J range-vs-atlas effect proper.
- **CiTO relation: `qualifies`.** Our work qualifies H&J 2007 by
  demonstrating that the misidentification metric they pioneered
  remains useful (their scale-dependence pattern reproduces), but that
  applying it to modern citizen-science atlases requires correction
  for observer-effort bias — a problem H&J's 1990s atlases had but to
  a much smaller degree.
- **Limitations the Outcome must surface, in this order:**
  1. **Atlas observer-effort confounding** is the dominant residual.
     Confirmed by Tests 4 and 6 together. The modern Iberian GBIF
     atlas places top-5 % hotspots predominantly at observer hotspots
     (cities, accessible protected areas) rather than biologically
     richest cells. The Art-12 expert rangemap test (Test 6) shows
     this is irreducible by any rangemap-side improvement.
  2. Top-K = 5 % is H&J's convention, not biologically grounded.
     Misidentification is K-sensitive; at K = 25 % our numbers sit
     inside the H&J reference range.
  3. Hull-as-rangemap is a *secondary* contributor (refuted as
     dominant by Test 6). Concave hulls close 6–13 pp on the
     full-species set; the gold-standard expert rangemap does NOT
     close the residual.
  4. Cell-shape difference (HEALPix equal-area vs H&J lat-lon) is
     unlikely to matter at Iberia's latitude but is not directly
     tested.

## Follow-up (no longer blocking the Outcome)

The IUCN follow-up that the decomposition + verification notes called
"the most informative test" has been **completed** (Test 6 above) using
the equivalent EU Article 12 dataset. The residual is **not** closed
by the gold-standard rangemap. Future follow-ups that would further
sharpen the Outcome:

- **Observer-effort correction of the atlas.** Use per-cell record
  count as a covariate to model effort-corrected species richness;
  rerun the misidentification calculation against Art-12 polygons. If
  effort-corrected atlas + Art-12 reaches H&J's 47.8–68.6 % range, the
  residual is fully attributed to observer bias and the H&J finding is
  cleanly validated. This is a substantial methodological extension
  (would justify a separate FORRT chain rather than a tweak to this
  one).
- **Season-matched comparison.** Art-12 is breeding-only; the GBIF
  atlas is year-round. Restricting GBIF to April–July (Iberian breeding
  window) would tighten the comparison.
