---
name: verify-chain
description: Read-only verification of a published FORRT nanopublication chain. Fetches each URI from nanopubs/PUBLISHED.md, parses the signed TriG, and checks that the citation graph is internally consistent (each step references the previous step's URI) and externally consistent (Outcome's Repository URL matches this repo; CiTO's cited DOI resolves). Returns a per-row pass/fail report. Run as the final pre-comms check after Phase 5.
---

# /verify-chain

You're verifying that the FORRT chain published from this repository is **internally consistent** (each step cross-references the previous step's URI as it should) and **externally consistent** (the URIs the chain claims about external artefacts — the GitHub repo, the cited DOI — actually resolve and match what's locally present).

This is read-only work. **Do not** edit any nanopub, do not retract, do not supersede. The output is a verification report; any fixes are downstream actions the user takes if the report finds problems.

## When to run

- **After Phase 5 is fully published.** All 6 chain steps must have URIs in `nanopubs/PUBLISHED.md` (URIs replace the `_not yet published_` placeholders).
- **Before announcing the chain publicly.** A LinkedIn post, blog announcement, or paper citation should follow a green `/verify-chain` run, not precede it.
- **After any supersede or retract operation.** Re-verify because the citation graph may have shifted.

## Procedure

### Step 1 — Read the registry

Read `nanopubs/PUBLISHED.md`. Extract the published URIs for each step:

| Step | Template | URI source |
|---|---|---|
| 1 | Quote-with-comment, PICO, or PCC | row labelled "01" in the chain table |
| 2 | AIDA Sentence | row labelled "02" |
| 3 | FORRT Claim | row labelled "03" |
| 4 | FORRT Replication Study | row labelled "04" |
| 5 | FORRT Replication Outcome | row labelled "05" |
| 6 | CiTO Citation | row labelled "06" |
| 7 | Research Software (optional) | row labelled "07" |
| 8 | Research Synthesis (optional) | row labelled "08" |

If any step's row still reads `_not yet published_`, stop and tell the user: *"Step N has no URI in PUBLISHED.md — the chain isn't complete. Run `/verify-chain` again once all six steps are published."*

Skip optional steps (07, 08) if they say `_not applicable / not yet published_`.

### Step 2 — Fetch each nanopub's TriG

For each URI, fetch its signed TriG via the HTTP resolver:

```bash
curl -s -L -H "Accept: application/trig" "<URI>"
```

URIs in either namespace (`https://w3id.org/sciencelive/np/RA…` or `https://w3id.org/np/RA…`) resolve through this single GET. Save each response to a temporary file (in-memory string is also fine) so it can be inspected for cross-references.

If a fetch fails (network error, 404), record it in the report as `step N: URI unreachable` and continue with the remaining steps. Don't stop.

### Step 3 — Internal consistency check (citation graph)

A FORRT chain is a linear citation graph: each step references the previous step's URI somewhere in its assertion (and sometimes provenance) graph. The cleanest test is to fetch step N's TriG and grep / string-search for step N−1's URI.

For each adjacency:

| Test | Pass criterion |
|---|---|
| Step 2 (AIDA) references step 1 (Quote/PICO/PCC) | Step 1's URI appears as a string in step 2's TriG |
| Step 3 (Claim) references step 2 (AIDA) | Step 2's URI appears as a string in step 3's TriG |
| Step 4 (Study) references step 3 (Claim) | Step 3's URI appears as a string in step 4's TriG |
| Step 5 (Outcome) references step 4 (Study) | Step 4's URI appears as a string in step 5's TriG |
| Step 6 (CiTO) references step 5 (Outcome) | Step 5's URI appears as a string in step 6's TriG, as the citing creative work |

Implementation: `grep -F "<step-N-1-URI>" step-N.trig` returns at least one match. Record a tick (✓) or cross (✗) per row.

This grep-based check is intentionally robust to predicate variation across Science Live's template versions — it doesn't matter exactly which predicate names connect the steps, only that the upstream URI is referenced *somewhere* in the downstream nanopub's TriG.

### Step 4 — External consistency check

These cross-reference checks span the chain to artefacts outside the nanopub network.

**Outcome's Repository URL matches this repo's GitHub remote.**

```bash
expected_repo=$(git remote get-url origin | sed 's|.*github.com[:/]||;s|\.git$||')
# Example: "annefou/weatherxbiodiversity-projection"

# Then check that the Outcome's TriG contains the substring:
#   github.com/<expected_repo>
grep -F "github.com/${expected_repo}" step-5.trig
```

If absent: record `Outcome's Repository URL doesn't match local git remote`. Fix is to retract + supersede the Outcome with the correct URL.

**CiTO's cited DOI resolves.**

The CiTO step's TriG includes a `cito:confirms` (or similar) predicate pointing to a DOI URL. Extract that URL (use a simple regex like `https://doi\.org/10\.[0-9.]+/[^>]+` over the step-6 TriG; take the first DOI-shaped match that's NOT the citing work). Then:

```bash
curl -s -o /dev/null -w "%{http_code}" -L "<cited-DOI-URL>"
```

Pass criterion: HTTP status `200`, `302`, or `303` (DOI resolvers redirect through 30x). Fail: `404` or `5xx`.

**Outcome's source DOI matches CITATION.cff (if present).**

If the repo has a `CITATION.cff` with a `doi:` field (Zenodo concept DOI), check that the Outcome's TriG references that same DOI (as a `dct:source` or similar). This catches the "released v1.0.0 but Outcome still references v0.9.0's pre-release DOI" mistake.

```bash
cff_doi=$(grep '^doi:' CITATION.cff | head -1 | sed 's/.*"\(.*\)".*/\1/')
# Example: "10.5281/zenodo.19756173"
grep -F "${cff_doi}" step-5.trig
```

If absent: warn (not fail) — the Zenodo DOI in CITATION.cff might be a later release than the one referenced in the published Outcome, which is a normal version-drift case, not a chain-integrity bug.

### Step 5 — Report

Output a single Markdown table the user can paste into a release-readiness checklist or a Jupyter Book section. One row per check, with pass / fail / warn status.

Template:

```markdown
## /verify-chain report

| Check | Status | Notes |
|---|---|---|
| All 6 step URIs present in PUBLISHED.md | ✓ / ✗ | |
| Each step's TriG is reachable | ✓ / ✗ | |
| AIDA references Quote/PICO/PCC | ✓ / ✗ | |
| FORRT Claim references AIDA | ✓ / ✗ | |
| Replication Study references Claim | ✓ / ✗ | |
| Replication Outcome references Study | ✓ / ✗ | |
| CiTO Citation references Outcome | ✓ / ✗ | |
| Outcome Repository URL matches git remote | ✓ / ✗ | annefou/<repo> |
| CiTO cited DOI resolves | ✓ / ✗ | https://doi.org/... |
| Outcome source DOI matches CITATION.cff | ✓ / ⚠ | warn = version drift |

**Verdict:** GREEN (all passes) / RED (one or more fails) / YELLOW (warns only, no fails).
```

If the verdict is GREEN, conclude with:
> *"The chain is internally consistent and externally resolves correctly. Safe to announce."*

If RED, conclude with the list of specific failures and a suggested next step (typically: retract + supersede via `nanopub-agent-utilities` — see `docs/programmatic-nanopubs.md`).

If YELLOW, conclude with the warnings and a one-line judgement of whether they're real (e.g. CITATION.cff DOI vs Outcome DOI drift is normal during active releases; flag but don't block).

## Anti-patterns

- **Don't edit any nanopub.** This skill is read-only. Verification surfaces problems; the user takes the fix action.
- **Don't try to publish anything.** No `publish`, no `retract`, no `supersede` from this skill.
- **Don't conflate failure with absence.** If step 7 (Research Software) is genuinely optional and the user didn't publish one, that's not a failure — it's an N/A. The report should reflect that.
- **Don't rely on a specific predicate vocabulary.** The grep-based reference check works across template versions. Don't bet on `npx:relatedTo` or similar; the predicate names may change.

## Tools

This skill uses `Read` (for PUBLISHED.md, CITATION.cff, and local files) and `Bash` (for `curl`, `grep`, `git remote`). No `Edit`, `Write`, or any state-changing tool.

## Cross-references

- The chain shapes and which step references which: `docs/chain-decision-tree.md` and `nanopubs/README.md` § Order matters
- For retract / supersede (the typical fix when this skill returns RED): `docs/programmatic-nanopubs.md`
- The published-URI registry: `nanopubs/PUBLISHED.md`
