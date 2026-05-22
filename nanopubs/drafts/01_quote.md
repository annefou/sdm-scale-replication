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

> _Read the PDF first. Don't paraphrase from memory. See `docs/verify-before-drafting.md`._

```
At resolutions less than 2° (∼200 km), range maps overestimate the area of occupancy of individual species and mischaracterize spatial patterns of species richness, resulting in up to two-thirds of biodiversity hotspots being misidentified.
```

Character count: 240 / 500.

### Comment (textarea, required)

Subtitle: *"Our interpretation or explanation of why this quotation is relevant."*

Why this quote matters and what the replication tests. Connect the paper's claim to the work this repo does. Don't repeat the quote.

```
Hurlbert & Jetz showed nearly two decades ago that the grain at which expert-drawn range maps are aggregated controls whether the resulting richness hotspots are real. Their test used WWF range maps overlaid on bird atlas survey data across Australia and southern Africa at 0.25°-8° lat-lon grids. The intervening 18 years have brought modern occurrence data (GBIF), updated IUCN range maps, and DGGS substrates (HEALPix-NESTED) that no longer carry the area-distortion of lat-lon grids. This replication closes the empirical loop on the eight SDM-resolution scaffold Quote-with-comments (Guisan 2007, Manzoor 2018, Araújo 2019, Brambilla 2024, Cohen & Jetz 2023, Zurell 2020, Moudrý 2023): does the scale-dependent hotspot misidentification re-emerge with modern data on an equal-area sphere-aware substrate, and at what HEALPix resolution does it onset?
```

## Publication note

After publishing, paste the resulting URI into `nanopubs/PUBLISHED.md` step 01.
