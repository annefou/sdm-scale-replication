# 01 — Quote-with-comment (paper-rooted chains)

> Run the pre-flight checklist in `docs/forrt-form-fields.md` § Pre-flight checklist before drafting.
>
> If this is a question-rooted chain, use `01_pico.md` or `01_pcc.md` instead — see `docs/chain-decision-tree.md`.
>
> **After choosing the chain shape, delete the two step-1 alternates you aren't using.** Once you've decided this chain is paper-rooted and keep `01_quote.md`, run:
> ```bash
> rm nanopubs/drafts/01_pico.md nanopubs/drafts/01_pcc.md
> ```

**Form heading:** *"Annotate a paper quotation — Annotating a paper quotation with personal interpretation"*

## Field-by-field draft

### Cited DOI (text input)

Format: starts with `10.` — bare DOI, **NOT** `https://doi.org/...` form.

```
10.1073/pnas.0704469104
```

### Quote mode (radio button)

- [x] **Quote whole text (less than 500 characters)**
- [ ] Quote start/end *(use this if the quote exceeds 500 chars)*

### Quoted Text (textarea, required)

Verbatim from the paper PDF in `paper/` (Abstract, page 13384). Character-for-character. ≤ 500 chars in whole-text mode.

> _Verified character-for-character against the PDF abstract (page 13384) on 2026-05-23, including the U+223C "∼" tilde operator and the "2°" degree sign. See `docs/verify-before-drafting.md`._

```
At resolutions less than 2° (∼200 km), range maps overestimate the area of occupancy of individual species and mischaracterize spatial patterns of species richness, resulting in up to two-thirds of biodiversity hotspots being misidentified.
```

Character count: 237 / 500.

### Comment (textarea, required)

Subtitle: *"Our interpretation or explanation of why this quotation is relevant."*

Why this quote matters and what the replication tests. Connect the paper's claim to the work this repo does. Don't repeat the quote.

```
Hurlbert & Jetz showed that the grain at which expert-drawn bird range maps are aggregated controls whether the resulting richness hotspots are real: finer than ~2°, up to two-thirds are misidentified relative to atlas-survey ground truth. This replication tests whether that scale-dependence re-emerges for Iberian birds using modern GBIF occurrence data on an equal-area HEALPix-NESTED substrate — which removes the cell-area distortion of lat-lon grids — and what drives the magnitude of the range-map/atlas hotspot disagreement.
```

*Comment length ≈ 480 / 500 chars. Corrected from the Phase-1 draft:
(1) Hurlbert & Jetz used expert range maps from the Handbook of the
Birds of the World + regional atlases, NOT "WWF range maps"; (2) the
replication uses GBIF-occurrence convex hulls + EU Article 12 expert
polygons, NOT "IUCN range maps"; (3) dropped the seven-paper SDM
scaffold list (it reads as marketing and is preserved in `CITATION.cff`
per `00_design_decisions.md`, not re-stated in the chain).*

## Publication note

After publishing, paste the resulting URI into `nanopubs/PUBLISHED.md` step 01.
