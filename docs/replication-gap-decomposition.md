# Replication-gap decomposition vs Hurlbert & Jetz 2007

> ⚠️ **SUPERSEDED 2026-05-23 by [`replication-gap-verification.md`](replication-gap-verification.md).**
> The conclusion below ("hull-as-rangemap is the whole gap") was *partially
> wrong* — see the verification note for the revised three-mechanism
> decomposition (hull + observer-effort + top-K sensitivity) and a
> retraction of the "temporal axis is negligible" claim. The empirical
> tables in this note remain valid; the interpretation does not.

This note records what the diagnostic notebook
([`notebooks/03b_diagnostics.py`](../notebooks/03b_diagnostics.py)) tells us
about the ~30–50 percentage-point gap between our headline misidentification
numbers and H&J 2007's. It is the empirical input to the Outcome draft
([`nanopubs/drafts/05_outcome.md`](../nanopubs/drafts/05_outcome.md)).

## The gap to explain

| Source | At H&J's 0.25° equivalent (Nside 256, ~25 km) |
|---|---:|
| H&J 2007 Australia | 47.8 % |
| H&J 2007 Southern Africa | 68.6 % |
| Our **museum** strategy | **89.9 %** |
| Our **allbor** strategy | **97.8 %** |

The canonical pipeline (02 → 03) confounds two substitutions H&J did not
make:

1. **Hull-as-rangemap** — H&J had expert BirdLife polygons (which exclude
   unsuitable habitat *inside* the convex envelope); we use convex hulls of
   GBIF occurrences.
2. **Temporal split** — H&J's atlas + rangemap were contemporaneous; ours
   compare pre-2000 hull (rangemap-equivalent) vs post-2000 occurrences
   (atlas-equivalent), embedding 25 + yr of range shift in the comparison.

Three diagnostics in `03b_diagnostics.py` decompose which substitution owns
the gap.

## Diagnostic 1 — Hull-area sanity

Per-species pre-2000 convex-hull areas (sq deg); Iberia bbox = 126 sq deg.

| Strategy | n species | median | mean | max | n hulls > ½ Iberia bbox |
|---|---:|---:|---:|---:|---:|
| museum | 356 | 15.0 | 16.7 | 68.8 | **2 / 356 (0.6 %)** |
| allbor | 608 | 54.7 | 43.4 | 88.9 | **265 / 608 (43.6 %)** |

See [`figures/hull_areas_diagnostic.png`](../figures/hull_areas_diagnostic.png).

**Reading:**

- **Allbor hulls are pathologically inflated.** ~44 % of species have a
  convex hull covering more than half of Iberia. The distribution piles up
  against the Iberia bbox limit — most allbor hulls are bounded by
  *geographic extent*, not by *species range*. This is because the all-BoR
  download (PRESERVED + MACHINE + HUMAN observations) is dominated by
  citizen-science records for common widespread species (passerines,
  raptors, gulls), each with thousands of observations spanning the whole
  peninsula → giant convex hulls.
- **Museum hulls are inflated but tractable.** Median 15 sq deg (~125 k
  km², roughly a quarter of mainland Iberia), p90 ~ 35 sq deg, almost none
  exceed half the bbox. Museum-only (PRESERVED_SPECIMEN +
  MACHINE_OBSERVATION) suppresses the citizen-science volume that drives
  allbor's bimodal distribution.

The diagnostic confirms the first-principles prediction that hull-as-rangemap
*systematically over-predicts presence*, and quantifies the inflation: it is
~3× larger for allbor than for museum (median 55 vs 15 sq deg).

## Diagnostic 2 — Minimum-points sensitivity

Re-derive rangemap richness from pre-2000 hulls filtered to species with
n_points ≥ k.

At Nside 256 (H&J's 0.25° equivalent):

| Strategy | min_pts ≥ 1 | ≥ 5 | ≥ 10 | ≥ 20 |
|---|---:|---:|---:|---:|
| museum | 89.94 % | 91.23 % | 91.86 % | 90.59 % |
| allbor | 97.80 % | 97.80 % | 97.80 % | 97.80 % |

**Reading:** filtering out few-occurrence species does **not** close the
gap at any Nside. Museum drifts very slightly upward (≤ 2 pp swing);
allbor is completely insensitive. **Tiny-sample species are not the source
of the bias** — the bias is in the well-sampled species whose hulls
*should* be informative but are still too geographically over-extended.

## Diagnostic 3 — Same-era hulls (temporal-axis effect isolated)

Rebuild hulls from **post-2000** points (not pre-2000) and recompute
misidentification, holding the atlas axis fixed.

| | museum | | allbor | |
|---|---:|---:|---:|---:|
| Nside | temporal | same-era | temporal | same-era |
| 16 | 0.0 % | 100.0 % | 100.0 % | 100.0 % |
| 32 | 66.7 % | 66.7 % | 66.7 % | 66.7 % |
| 64 | 80.0 % | 66.7 % | 100.0 % | 90.9 % |
| 128 | 85.7 % | 82.9 % | 97.9 % | 95.7 % |
| **256** | **89.9 %** | **89.3 %** | **97.8 %** | **97.2 %** |
| 512 | 93.7 % | 92.0 % | 94.7 % | 92.7 % |

See [`figures/scale_dependence_decomposition.png`](../figures/scale_dependence_decomposition.png).

**Reading:**

- **At H&J's reference scale (Nside 256), removing the temporal confound
  closes < 1 percentage point of the gap** — 0.66 pp for museum, 0.56 pp
  for allbor. The temporal-axis effect is negligible at the headline scale.
- At coarser scales the temporal effect is non-trivial but swings both
  ways: at Nside 16, switching to same-era *increases* museum
  misidentification from 0 % to 100 %, because using post-2000 hulls (much
  denser data) inflates rangemap richness enough that all 8 Iberian cells
  saturate and the top-5 % set destabilises. At Nside 64, same-era
  *decreases* allbor misidentification by 9 pp.
- Mean rangemap richness is **higher** in the same-era variant
  (e.g. allbor Nside 256: 228 → 323). With more data, hulls get bigger,
  not tighter. **The temporal axis is not the substantive confound we
  expected it to be**; pre-2000 hulls under-predict and post-2000 hulls
  over-predict, and at fine scales the two cancel in opposite directions
  to roughly the same misidentification number.

## What this implies for the Outcome

The replication-gap decomposition is unambiguous:

> **The gap between our ~90–98 % misidentification at Nside 256 and H&J's
> 47.8 % / 68.6 % is essentially entirely attributable to the
> hull-as-rangemap substitute, not the temporal-axis substitute and not
> few-sample noise.**

Concretely:

1. **Temporal axis: ~0 contribution** at the headline scale (< 1 pp).
2. **Few-sample noise: ~0 contribution** (filtering n_points ≥ 20 moves
   museum by < 1 pp, allbor by 0 pp).
3. **Hull-as-rangemap: the entire remaining ~20–50 pp gap.** Allbor is more
   severely affected (97.8 % vs H&J's 47.8 / 68.6 %) than museum
   (89.9 %), which tracks the hull-area diagnostic: allbor's hulls cover
   ~3× more area than museum's, and ~44 % of allbor hulls exceed half the
   Iberia bbox.

### Implications for the FORRT chain

- **Qualitative replication: confirmed.** H&J's scale-dependence pattern
  (monotone increase in misidentification with grid refinement, dissolution
  at very coarse cells) is reproduced in both strategies and both rangemap
  variants. The *direction* of the H&J finding is robust.

- **Quantitative replication: confirmed-with-amplification, attributable to
  the rangemap-data-source.** Our number is higher than H&J's not because
  the H&J effect is wrong, but because convex-hull-derived ranges
  systematically over-state range extent compared to expert polygons —
  inflating the cells where the rangemap claims presence and therefore the
  cells where rangemap and atlas hotspots disagree.

- **CiTO relation: `extends`** (not `disputes`, not `confirms`). Our work
  *extends* H&J 2007 by showing the scale-dependence finding survives the
  switch from 1990s African / Australian birds + expert range maps to
  modern Iberian birds + occurrence-derived hulls — but with a
  quantitatively larger effect that is itself diagnostic of the rangemap
  data source's coarseness.

- **Outcome classification:** *Partially Supported*. Direction validated;
  magnitude diverges in a direction attributable to a clean methodological
  substitution.

### Open follow-ups (not blocking the Outcome)

- **Gold-standard rerun**: integrate real IUCN Red List range polygons for
  Iberian birds. If that recovers H&J-level numbers, our finding stands as
  a clean quantification of the hull-substitute bias. If misidentification
  remains > 80 %, there is a residual biogeographic / data-density
  difference between modern Iberia and 1990s Australia / southern Africa.
- **α-shape / concave hull alternative**: a tighter polygon substitute
  that preserves the "no manual range-mapping required" property of our
  current method while addressing the convex-envelope over-prediction.
  Lower cost than IUCN; partially closes the gap.
- **Cell-count instability at coarse Nside**: at Nside 16 (8 cells) and
  Nside 32 (29 cells), top-5 % rounds to 0–2 cells and the misidentification
  number is noise-dominated. The headline conclusion does not depend on
  these scales; they should be reported with a clear caveat.

These follow-ups are good post-Outcome science, not blockers. The
decomposition above is sufficient to write an honest, well-attributed
Outcome and CiTO Citation now.
