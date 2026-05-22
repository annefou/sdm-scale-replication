# Phase 1 design decisions — locked 2026-05-22

Answers to the 5 open questions raised in `nanopubs/imported/CHAIN_SUMMARY.md`. These shape every downstream draft (`01_quote.md`, AIDA, Claim, Study, Outcome, CiTO) and the Phase 2 notebook pipeline.

## 1. Headline claim anchor

The new chain anchors on **Hurlbert & Jetz (2007)'s "≈ two-thirds of richness hotspots are misidentified" claim** — the empirical scale-dependence finding that range-map-derived richness hotspots disagree substantially with finer-resolution truth at the grain sizes commonly used in macroecology / conservation prioritisation.

The exact verbatim sentence for `01_quote.md` is to be selected during Phase 1 from the paper PDF. The Quote-with-comment template requires verbatim text — paraphrase is forbidden (see `docs/verify-before-drafting.md`).

## 2. Design — Replication only, no Reproduction component

**Replication (different data + different substrate)**, not Reproduction. Rationale: the original H&J analysis used 1°/0.5°/0.25° lat-lon grids with WWF range maps + atlas data circa 2007. Re-running on the original inputs adds little; the empirically valuable test is whether the *same scale-dependence pattern* re-emerges on:

- **Modern GBIF occurrence data** (point records, not range maps).
- **Modern IUCN range maps** (where applicable for the target taxon).
- **HEALPix-NESTED substrates** at multiple resolutions (the DOMAIN.md / prior-chain default).

The taxon, region, and exact substrate ladder are to be fixed during Phase 1 paper analysis and Phase 2 data download.

## 3. Chain topology — fresh sibling chain, NOT Synthesis-extension

This chain stands as a **fresh sibling** on Hurlbert & Jetz 2007. It does **not** extend the cross-taxon Bombus + Lizards Synthesis (`RAcDYOu65z09jUbDwd_c2OxGI9KUPZmLszxUlLVOyzt3M`).

Rationale: the prior Synthesis is a thermal-extinction-mechanism story (Soroye/Sinervo); the new chain is a sampling-grain / range-map-quality story (Hurlbert & Jetz). They share the scale-dependence theme but are not the same empirical claim. Bundling them now would entangle two distinct argument threads. A later cross-Synthesis can aggregate both if the new chain's results align.

## 4. CiTO scope — H&J only

The CiTO Citation nanopub (step 06) cites **only Hurlbert & Jetz 2007** (`10.1073/pnas.0704469104`). The 8 SDM-resolution Quote-with-comment scaffold nanopubs (Guisan 2007, Manzoor 2018, Araújo 2019, Brambilla 2024, Cohen & Jetz 2023, Zurell 2020, Moudrý 2023 — listed in `CITATION.cff` lines 50-75) are referenced in:

- `CITATION.cff` `references:` — durable provenance for the scaffold.
- The Replication Study's "Background" / "Methodology" field — narrative context for the scaffold.

But they are **not** re-cited in the CiTO step. Keeping the CiTO atomic on H&J makes the chain's contract with the upstream paper unambiguous.

## 5. Research Software nanopub — deferred

**No** Research Software nanopub at this stage. This repo produces an analysis, not a reusable `pip install`-able tool. Per the FORRT vs Research Software layered-architecture rule in `CLAUDE.md`, a Research Software nanopub describes a *separable* reusable software artefact; one-off analysis repos cite their FORRT Claim via `CITATION.cff` instead.

If later iterations of this repo factor out a HEALPix-aware SDM-scale-diagnostic library that other projects can depend on, the Research Software nanopub becomes appropriate. Not now.

## Next step

Phase 1 paper analysis. Drop the H&J PDF into `paper/` (already done), then run the `paper-analyst` agent to extract:

- The verbatim "≈ two-thirds of hotspots misidentified" sentence into `nanopubs/drafts/01_quote.md`.
- A short methodology summary (data sources, grids, taxon, headline numerical result) into `nanopubs/drafts/00_paper_summary.md`.
