# Published nanopub chain — URI registry

This file is the canonical registry of published nanopub URIs for this replication. Update it as you publish each step.

## Chain

| Step | Template | URI | Published |
|---|---|---|---|
| 01 | Quote-with-comment (or PICO / PCC) | https://w3id.org/sciencelive/np/RAPXXucP5ybWIYK5hFoBLxyZkhCYgSvRqFUtzqe13volk | |
| 02 | AIDA Sentence | https://w3id.org/sciencelive/np/RAP4AuE_48-QhDrhC5loj0Tx5_qlilVx2Pu75_zT2c7Y4 | |
| 03 | FORRT Claim | https://w3id.org/sciencelive/np/RA6rlc6PBloQtaFWbN3rXizMQqT-DOZgJzCPNsWQFjnTo | |
| 04 | FORRT Replication Study | https://w3id.org/sciencelive/np/RA-H2_b7MJxxUg9nJH8McxccG_6Kr3s8xlXQM8vrnamnU | |
| 05 | FORRT Replication Outcome | _not yet published_ | |
| 06 | CiTO Citation | _not yet published_ | |

## Software & data archive (Zenodo)

| Artefact | DOI | Notes |
|---|---|---|
| Source — concept DOI | [10.5281/zenodo.20363555](https://doi.org/10.5281/zenodo.20363555) | Resolves to the latest version. |
| Source — version DOI (v0.1.0) | [10.5281/zenodo.20363556](https://doi.org/10.5281/zenodo.20363556) | This release. |
| Docker image | _pending docker.yml run / Zenodo upload_ | GHCR `ghcr.io/annefou/sdm-scale-replication`; archived if `ZENODO_TOKEN` secret is set. |

## Optional layers

| Step | Template | URI | Published |
|---|---|---|---|
| 07 | Research Software (if applicable) | _not applicable / not yet published_ | |
| 08 | Research Synthesis (if applicable) | _not applicable / not yet published_ | |

## Format

URIs from Science Live are of the form `https://w3id.org/sciencelive/np/RA…`. URIs from Nanodash (used as a fallback when the Science Live UI hits a bug) are of the form `https://w3id.org/np/RA…`. Both are valid and citable.

If a URI is not in the Science Live namespace, view it via the Science Live viewer by wrapping the URI:

```
https://platform.sciencelive4all.org/np/?uri=<full-URI>
```

## Cross-references

- Drafts: `nanopubs/drafts/`
- Form structure: `docs/forrt-form-fields.md`
- Chain shape decision: `docs/chain-decision-tree.md`
