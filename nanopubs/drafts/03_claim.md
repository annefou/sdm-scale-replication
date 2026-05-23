# 03 — FORRT Claim

> Run the pre-flight checklist in `docs/forrt-form-fields.md` § Pre-flight checklist before drafting.

**Form heading:** *"FORRT Claim — Declare an original claim according to FORRT, linking it to an AIDA sentence with a specific FORRT type."*

## Field-by-field draft

### Short URI suffix as claim ID (text input, required)

Slug becomes part of the nanopub URI. Use kebab-case.

```
hj2007-hotspot-scale-dependence
```

### Label of the claim (text input, required)

A descriptive title (not a sentence). Used for searches/discovery.

```
Scale-dependent misidentification of bird richness hotspots from range maps (Hurlbert & Jetz 2007)
```

### Search for an AIDA sentence (search/select, required)

URI of the AIDA published in step 02. Pull from `nanopubs/PUBLISHED.md`.

> _If the AIDA was published via Nanodash (`w3id.org/np/...` namespace), the platform's search may not find it — paste the URI manually._

```
<URI of step 02 (AIDA) — paste after step 02 is published>
```

### Type of FORRT claim (dropdown, required)

Pick one. See `docs/claim-type-vocabulary.md` for the seven options and how to choose.

- [ ] computational performance
- [ ] scalability
- [ ] data quality
- [ ] data governance
- [x] **descriptive pattern**
- [ ] model performance
- [ ] statistical significance

*Hurlbert & Jetz 2007 asserts an observed empirical relationship —
the spatial pattern of richness hotspots depends on the grain at which
range-map data is aggregated. This is a `descriptive pattern` claim
(per `docs/claim-type-vocabulary.md`, the same genre as the Soroye 2020
thermal-exposure precedent). Statistical significance (Wilcoxon) is the
*evidence* for the pattern, not the claim itself, so `statistical
significance` is not the right type.*

### Source URI (text input, optional)

Full URL form: `https://doi.org/...` (NOT bare DOI).

```
https://doi.org/10.1073/pnas.0704469104
```

## Publication note

After publishing, paste the resulting URI into `nanopubs/PUBLISHED.md` step 03.
