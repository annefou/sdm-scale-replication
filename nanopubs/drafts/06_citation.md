# 06 — CiTO Citation

> Run the pre-flight checklist in `docs/forrt-form-fields.md` § Pre-flight checklist before drafting.
>
> Citation Type derived from
> [`nanopubs/drafts/05_outcome.md`](05_outcome.md) — Validation status =
> `PartiallySupported` → CiTO `qualifies` (the canonical mapping per
> `docs/forrt-form-fields.md`). Scope locked per
> `nanopubs/drafts/00_design_decisions.md`: this chain cites **only**
> Hurlbert & Jetz 2007.

**Description:** *"Declare citations between papers or other works, using Citation Typing Ontology"*

## Field-by-field draft

### Identifier for the citing creative work (text input, required)

URI of the Outcome published in step 05. Pull from `nanopubs/PUBLISHED.md`.

```
<URI of step 05 — paste after step 05 is published>
```

### List citations (repeatable group, required ≥1)

#### Citation 1 — Hurlbert & Jetz 2007

##### Citation Type (dropdown)

- [ ] confirms        *(would apply if Validation status = Validated)*
- [x] **qualifies**   *(applies — Validation status = PartiallySupported)*
- [ ] disputes        *(would apply if Validation status = Contradicted)*
- [ ] extends
- [ ] usesMethodIn
- [ ] citesAsAuthority
- [ ] obtainsBackgroundFrom
- [ ] discusses
- [ ] citesAsDataSource
- [ ] containsAssertionFrom
- [ ] includesQuotationFrom
- [ ] reviews
- [ ] critiques
- [ ] credits

```
qualifies
```

*Justification: the Outcome reproduces Hurlbert & Jetz's qualitative
scale-dependence finding (direction agreement, monotone across the full
HEALPix-NESTED resolution ladder) but reports a magnitude offset that is
decomposed into three documented methodological substitutions (rangemap
polygon, atlas observer-effort, top-K threshold). `qualifies` is the
CiTO intention that records "I'm citing this work and modifying or
restricting its applicability" — exactly the Partially-Supported
scenario. `confirms` would over-state the magnitude agreement;
`disputes` would mis-state the direction agreement; `extends` would
imply we've taken the claim beyond its original scope, but our scope is
the same finding tested under different data and methods, which is the
canonical qualification scenario.*

##### DOI or other URL of the cited work (text input)

```
https://doi.org/10.1073/pnas.0704469104
```

#### Additional citations (optional)

*Not applicable for this chain.* Scope locked per
`nanopubs/drafts/00_design_decisions.md` (2026-05-22):
> "CiTO step: cites only Hurlbert & Jetz 2007. The 8 SDM-resolution
> scaffold Quote-with-comments stay in `CITATION.cff` + Study Background;
> they are NOT re-cited at step 06."

Methods / tooling / scaffold references live in:
- `CITATION.cff` (formal citation metadata),
- The Replication Study (step 04) "Methodology" / "Deviations" fields,
- The repository's README and Jupyter Book chapters,

— not in the FORRT chain's CiTO step.

## Publication note

After publishing, paste the resulting URI into `nanopubs/PUBLISHED.md`
step 06.

This completes the six-step FORRT chain. Optional next layers — both
deferred for this replication per the design-decisions memo:

- **Research Software** (`drafts/07_research_software.md`) — deferred.
  Revisit if a separable, pip-installable HEALPix-aware SDM-scale
  diagnostic library emerges from this work.
- **Research Synthesis** (`drafts/08_synthesis.md`) — not applicable.
  This is a fresh sibling chain on Hurlbert & Jetz 2007, not a synthesis
  across multiple Outcomes.
