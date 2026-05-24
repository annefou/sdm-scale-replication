# 02 — AIDA Sentence

> Run the pre-flight checklist in `docs/forrt-form-fields.md` § Pre-flight checklist before drafting.

**Form heading:** *"AIDA Sentence — Make structured scientific claims following the AIDA model"*

## Field-by-field draft

### AIDA sentence (textarea, required)

Atomic, Independent, Declarative, Absolute. One empirical finding. Must end with a full stop.

> _If your draft AIDA contains "and" linking two distinct findings, split into two AIDA nanopubs._

```
Aggregating expert-drawn bird range maps onto spatial grids finer than approximately two degrees misidentifies up to two-thirds of species-richness hotspots relative to atlas survey data.
```

*Atomicity check: one empirical finding — fine-grain aggregation of
range-map data misidentifies richness hotspots. The "two degrees" and
"two-thirds" are quantifiers of that single finding, not separate
findings, so no split is needed. Scope is bird-specific (Hurlbert &
Jetz 2007 is birds only — see `00_paper_summary.md`), and "hotspot" is
the operational top-5%-richest-cells definition. 192 characters.*

### Select related topics/tags (dropdown, optional)

Predefined topic vocabulary — list the labels you intend to pick from the dropdown.

```
biodiversity; species richness; macroecology; spatial scale
```

*Pick whichever of these the platform dropdown actually offers; if the
controlled vocabulary is narrower, prefer "biodiversity" / "species
richness".*

### Relates to this nanopublication (text input, required)

URI of the nanopub the AIDA derives from.

- For paper-rooted chains: the Quote-with-comment URI (from step 01).
- For question-rooted chains: the PICO or PCC URI (from step 01).

Pull the URI from `nanopubs/PUBLISHED.md`.

```
<URI of step 01 (Quote-with-comment) — paste after step 01 is published>
```

### Supported by datasets (repeatable group, optional)

DOIs/URLs of datasets that ground the AIDA claim.

*(skip — optional). The AIDA restates Hurlbert & Jetz 2007's original
claim; its grounding is the source paper itself, which is already cited
via the Quote-with-comment (step 01). The replication's own datasets
(GBIF download DOIs, EU Article 12) ground the Replication Study /
Outcome, not this AIDA.*

### Supported by other publications (repeatable group, optional)

DOIs/URLs of publications that support the AIDA claim — e.g. peer-reviewed methods papers, or the original paper if not already cited via the Quote.

*(skip — optional). Hurlbert & Jetz 2007 is already cited via the
Quote. Leaving both this and "Supported by datasets" empty also avoids
the known platform bug below.*

> **Known platform bug (2026-04-26):** if both *Supported by datasets* AND *Supported by other publications* are populated and publishing fails, fall back to publishing this AIDA via Nanodash. The URI namespace becomes `https://w3id.org/np/...` (still valid and citable).

## Publication note

After publishing, paste the resulting URI into `nanopubs/PUBLISHED.md` step 02.
