#!/usr/bin/env python3
"""Import a published FORRT nanopublication chain from a single entry URI.

Discovery is driven by the **Science Live platform's pre-built SPARQL
queries** against the KnowledgePixels nanopub-network endpoint, rather
than by hand-coded link-walking + heuristic step-type classification.
The platform already publishes the queries that answer the questions
this importer needs ("what nanopubs reference X?" / "what does X
reference?" / "what is X's template?"), and the network's
``npa:networkGraph`` admin graph indexes those edges natively.

The script copies three queries from
``science-live-platform/frontend/src/lib/queries/`` into the template's
``scripts/queries/`` directory at first commit; updates to those queries
on the SL platform side flow through by re-copying.

Usage::

    python3 scripts/import-nanopub-chain.py <NANOPUB-URI>

For example, to import the canonical Bombus apex CiTO Citation::

    python3 scripts/import-nanopub-chain.py \\
        https://w3id.org/sciencelive/np/RA1q6c0fG2bMbiozF8Az2UpIfzAzqp8hoVEl6QIzfUpH8

Output (under ``nanopubs/imported/``):

* ``trig/<RA-id>.trig``           — cached TriG for every fetched nanopub.
* ``constellation.json``          — structured graph summary:
                                      ``{ entry, nodes, edges, external_citations }``.
* ``cited_papers.txt``            — external (non-nanopub) URIs found in
                                      the assertion graphs (typically DOIs).

The follow-up step is for the orchestrating skill
(``import-from-nanopub``) to read ``constellation.json`` and write
``CHAIN_SUMMARY.md`` for use in Phase 1.

Dependencies: stdlib + ``rdflib``. Network access required (HTTP to
``query.knowledgepixels.com`` for SPARQL + to ``w3id.org`` for TriG).

Termination guards:

* ``--depth N`` (default 5) — BFS depth from the entry URI.
* ``--max-nodes M`` (default 80) — total nanopubs to fetch.
* ``--timeout T`` (default 30 s per request).
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

try:
    from rdflib import ConjunctiveGraph, URIRef
except ImportError:  # pragma: no cover
    sys.stderr.write(
        "ERROR: this script needs `rdflib`. Install with `pip install rdflib` "
        "in the env that runs your other replication scripts.\n"
    )
    raise SystemExit(2)

# --- Platform endpoints (mirror science-live-platform/frontend/src/lib/sparql.ts) ---
NANOPUB_SPARQL_ENDPOINT_FULL = "https://query.knowledgepixels.com/repo/full"

QUERIES_DIR = Path(__file__).parent / "queries"

# --- URI matching --------------------------------------------------------

_NANOPUB_URI_RE = re.compile(
    r"^(https?://w3id\.org/(?:sciencelive/)?np/RA[A-Za-z0-9_-]{20,})"
)
_DOI_RE = re.compile(r"https?://doi\.org/10\.[0-9]+/[^\s\"<>]+", re.IGNORECASE)
_ORCID_RE = re.compile(r"https?://orcid\.org/0000-[0-9X-]+", re.IGNORECASE)
_ZENODO_DOI_RE = re.compile(
    r"https?://(?:doi\.org/)?10\.5281/zenodo\.(\d+)", re.IGNORECASE,
)
_GITHUB_RE = re.compile(
    r"https?://github\.com/[A-Za-z0-9_.\-]+/[A-Za-z0-9_.\-]+", re.IGNORECASE,
)

# Files inherited from a sibling chain's repository. Conservative list:
# only files that are realistically reusable across replications of the same
# mechanism. The user reviews `_template_from_prior/` after import and
# merges what they want into the new repo. Add to this list iteratively
# as patterns emerge.
SIBLING_INHERITED_FILES = [
    "pixi.toml",
    "pixi.lock",
    "Snakefile",
    "notebooks/01_data_download.py",
    "notebooks/02_data_clean.py",
    "Dockerfile",
]

# Default location for sibling-repo clones — matches Anne's per-project
# convention of placing related repos as siblings to the new replication
# (i.e. ~/Documents/ScienceLive/<repo>/). Configurable via CLI.
DEFAULT_SIBLINGS_DIR = "../"


def canonical_nanopub_uri(any_uri: str) -> str | None:
    """Return the canonical nanopub base URI, stripping fragments and
    named-graph sub-paths."""
    m = _NANOPUB_URI_RE.match(any_uri)
    return m.group(1) if m else None


def resolver_url(uri: str) -> str:
    """Map a canonical nanopub URI to the W3ID resolver that returns TriG.

    The Science Live form ``https://w3id.org/sciencelive/np/RA...`` redirects
    to the platform's HTML viewer. The generic form ``https://w3id.org/np/RA...``
    resolves through the nanopub-network HTTP resolver and serves TriG.
    """
    return uri.replace("https://w3id.org/sciencelive/np/",
                        "https://w3id.org/np/")


# --- HTTP helpers --------------------------------------------------------

def fetch_trig(uri: str, timeout: int = 30) -> str:
    """Fetch a nanopub URI as TriG."""
    fetch = resolver_url(uri)
    req = urllib.request.Request(
        fetch,
        headers={
            "Accept": "application/trig, application/n-quads;q=0.9, */*;q=0.5",
            "User-Agent": "forrt-replication-template/import-nanopub-chain",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode("utf-8", errors="replace")
    stripped = body.lstrip().lower()
    if stripped.startswith("<!doctype html") or stripped.startswith("<html"):
        raise ValueError(
            f"Resolver returned HTML for {uri}; expected TriG. The URI form may "
            f"not be supported by the W3ID redirect — file an issue or use "
            f"the bare ``https://w3id.org/np/RA…`` form."
        )
    return body


def load_query(name: str) -> str:
    """Load a SPARQL query file from ``scripts/queries/``."""
    path = QUERIES_DIR / f"{name}.rq"
    if not path.exists():
        raise FileNotFoundError(
            f"SPARQL query file not found: {path}. "
            "These should be copied from "
            "`science-live-platform/frontend/src/lib/queries/`."
        )
    return path.read_text()


def substitute(query: str, **bindings: str) -> str:
    """Substitute placeholders in a SPARQL query.

    Two conventions match the SL platform's `sparql.ts`:

    - ``?_name``       → ``<URI>``   (URI substitution, used for
                                       graph-pattern subjects/objects)
    - ``${name}``      → ``URI``     (bare-string substitution, used inside
                                       ``STR()`` / ``CONTAINS()`` clauses)
    """
    out = query
    for name, value in bindings.items():
        out = out.replace(f"?_{name}", f"<{value}>")
        out = out.replace("${" + name + "}", value)
    return out


def sparql_query(query: str, timeout: int = 60) -> list[dict[str, str]]:
    """POST a SPARQL query, return a list of bindings dicts."""
    data = urllib.parse.urlencode({"query": query}).encode("utf-8")
    req = urllib.request.Request(
        NANOPUB_SPARQL_ENDPOINT_FULL,
        data=data,
        headers={
            "Accept": "application/sparql-results+json",
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "forrt-replication-template/import-nanopub-chain",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        result = json.loads(resp.read().decode("utf-8"))
    return [
        {k: v["value"] for k, v in row.items()}
        for row in result.get("results", {}).get("bindings", [])
    ]


# --- Template-label lookup (the only "type classification" the script needs) ---

_TEMPLATE_LABEL_CACHE: dict[str, str] = {}


def template_label(template_uri: str, *, fetch_timeout: int = 20) -> str:
    """Return a human-readable label for a nanopub template.

    Templates on the SL platform / nanopub network are themselves nanopubs.
    Their ``rdfs:label`` or ``dct:title`` names what the template represents
    (e.g. "AIDA Sentence", "FORRT Replication Outcome", "Citation with CiTO").
    """
    if not template_uri:
        return ""
    if template_uri in _TEMPLATE_LABEL_CACHE:
        return _TEMPLATE_LABEL_CACHE[template_uri]
    try:
        trig = fetch_trig(template_uri, timeout=fetch_timeout)
    except Exception:
        _TEMPLATE_LABEL_CACHE[template_uri] = ""
        return ""
    graph = ConjunctiveGraph()
    try:
        graph.parse(data=trig, format="trig")
    except Exception:
        _TEMPLATE_LABEL_CACHE[template_uri] = ""
        return ""
    # Prefer the template's own subject; fall back to any rdfs:label / dct:title.
    label_predicates = {
        "http://www.w3.org/2000/01/rdf-schema#label",
        "http://purl.org/dc/terms/title",
        "http://purl.org/dc/elements/1.1/title",
    }
    template_ref = URIRef(template_uri)
    label = ""
    for s, p, o in graph.triples((template_ref, None, None)):
        if str(p) in label_predicates:
            cand = str(o).strip()
            if cand:
                label = cand
                break
    if not label:
        for s, p, o in graph.triples((None, None, None)):
            if str(p) in label_predicates and not isinstance(o, URIRef):
                cand = str(o).strip()
                if cand:
                    label = cand
                    break
    # Strip the "Template: " self-descriptive prefix that SL/nanopub-network
    # templates carry — the platform uses it to label the template *itself*,
    # but our consumers want the step-type, not the meta-label.
    if label.startswith("Template: "):
        label = label[len("Template: "):]
    elif label.startswith("Template "):
        label = label[len("Template "):]
    _TEMPLATE_LABEL_CACHE[template_uri] = label
    return label


# --- Per-nanopub summarisation -------------------------------------------

@dataclass
class NodeSummary:
    uri: str
    step_type: str = ""          # human-readable, from template's rdfs:label
    template_uri: str = ""
    authors_orcid: list[str] = field(default_factory=list)
    plain_text_excerpts: list[str] = field(default_factory=list)
    raw_trig_path: str = ""


@dataclass
class EdgeSummary:
    source: str
    target: str
    relation: str


def parse_node(uri: str, trig_path: Path) -> NodeSummary:
    """Build a NodeSummary from a fetched TriG file."""
    node = NodeSummary(uri=uri, raw_trig_path=str(trig_path))
    graph = ConjunctiveGraph()
    try:
        graph.parse(source=str(trig_path), format="trig")
    except Exception:
        return node

    # Template URI → step-type label (uses the platform's own template registry).
    for s, p, o in graph.triples((None, None, None)):
        ps = str(p)
        if ps.endswith("wasCreatedFromTemplate"):
            node.template_uri = str(o)
            node.step_type = template_label(node.template_uri)
            break

    # ORCID authors
    for s, p, o in graph.triples((None, None, None)):
        os_ = str(o)
        if _ORCID_RE.match(os_) and os_ not in node.authors_orcid:
            node.authors_orcid.append(os_)

    # Plain-text excerpts (longest few literals — these are the substantive
    # content like Outcome conclusions, Study scopes, AIDA sentences).
    seen: set[str] = set()
    candidates: list[str] = []
    for s, p, o in graph.triples((None, None, None)):
        if isinstance(o, URIRef):
            continue
        val = str(o).strip()
        if len(val) < 12 or val in seen:
            continue
        if val.startswith("http://") or val.startswith("https://"):
            continue
        seen.add(val)
        candidates.append(val)
    candidates.sort(key=len, reverse=True)
    node.plain_text_excerpts = candidates[:4]

    return node


def cited_dois(trig_path: Path) -> set[str]:
    """Return all DOI URIs found anywhere in a fetched TriG file."""
    out: set[str] = set()
    text = trig_path.read_text(errors="replace")
    for m in _DOI_RE.finditer(text):
        out.add(m.group(0))
    return out


# --- SPARQL-driven discovery + TriG-based content extraction -------------

def find_outgoing_refs(uri: str) -> list[str]:
    """All nanopubs the entry references (downstream chain direction)."""
    q = substitute(load_query("references-from"), nanopubUri=uri)
    rows = sparql_query(q)
    return [r["np"] for r in rows if "np" in r]


def find_incoming_refs(uri: str) -> list[str]:
    """All nanopubs that reference the entry (upstream chain direction).
    Uses the SL platform's existing ``nanopub-references.rq`` verbatim."""
    q = substitute(load_query("nanopub-references"), nanopubUri=uri)
    rows = sparql_query(q)
    return [r["np"] for r in rows if "np" in r]


def discover_neighbours(uri: str) -> set[str]:
    """Bidirectional neighbour set: outgoing references + incoming references."""
    out: set[str] = set()
    for fn in (find_outgoing_refs, find_incoming_refs):
        try:
            for n in fn(uri):
                canon = canonical_nanopub_uri(n)
                if canon and canon != uri:
                    out.add(canon)
        except urllib.error.HTTPError as e:
            print(f"    ! SPARQL HTTP error: {e}", file=sys.stderr)
        except urllib.error.URLError as e:
            print(f"    ! SPARQL URL error: {e}", file=sys.stderr)
        except Exception as e:  # noqa: BLE001
            print(f"    ! SPARQL unexpected error: {e}", file=sys.stderr)
    return out


# --- BFS using SPARQL neighbourhood --------------------------------------

def walk(entry_uri: str, depth_limit: int, max_nodes: int, timeout: int,
         cache_dir: Path) -> tuple[dict[str, NodeSummary], list[EdgeSummary], set[str]]:
    """BFS the citation graph from `entry_uri`, using SPARQL for neighbour
    discovery and HTTP TriG fetching for per-nanopub content extraction.
    """
    cache_dir.mkdir(parents=True, exist_ok=True)

    nodes: dict[str, NodeSummary] = {}
    edges: list[EdgeSummary] = []
    externals: set[str] = set()
    visited: set[str] = set()
    queue: deque[tuple[str, int]] = deque([(entry_uri, 0)])

    while queue and len(nodes) < max_nodes:
        uri, depth = queue.popleft()
        if uri in visited:
            continue
        visited.add(uri)

        # 1. Fetch the TriG (caching)
        ra_id = uri.rsplit("/", 1)[-1]
        trig_path = cache_dir / f"{ra_id}.trig"
        if not trig_path.exists():
            print(f"  [{depth}] fetch TriG  {uri}", file=sys.stderr)
            try:
                trig_path.write_text(fetch_trig(uri, timeout=timeout))
            except Exception as e:  # noqa: BLE001
                print(f"    ! TriG fetch failed: {e}", file=sys.stderr)
                continue
            time.sleep(0.1)

        # 2. Parse into a NodeSummary
        node = parse_node(uri, trig_path)
        nodes[uri] = node
        externals |= cited_dois(trig_path)

        # Templates and template-definition nanopubs are not chain steps;
        # don't crawl outward from them. After we've stripped the
        # "Template: " self-descriptive prefix in `template_label()`, the
        # remaining signature words for template-definition nanopubs are
        # "defining a/an" (assertion / provenance / pubinfo template) and
        # "publishing labels".
        label_lower = (node.step_type or "").lower()
        is_template = (
            label_lower.startswith("defining a") or
            label_lower.startswith("defining an") or
            "publishing labels" in label_lower
        )

        # 3. Discover neighbours via SPARQL (only if we still have depth budget,
        # and only if this node is itself a chain step, not a template).
        if depth < depth_limit and not is_template:
            print(f"  [{depth}] SPARQL nbrs {uri}", file=sys.stderr)
            try:
                neighbours = discover_neighbours(uri)
            except Exception as e:  # noqa: BLE001
                print(f"    ! neighbour discovery failed: {e}", file=sys.stderr)
                neighbours = set()
            # Exclude template URIs the node was created from — those are
            # template definitions, not chain steps. Same for any URI that
            # appears anywhere as the target of `wasCreatedFromTemplate`.
            template_targets = {node.template_uri} if node.template_uri else set()
            for n in neighbours:
                if n in template_targets:
                    continue
                edges.append(EdgeSummary(source=uri, target=n, relation="refersTo"))
                if n not in visited:
                    queue.append((n, depth + 1))

    return nodes, edges, externals


# --- Infrastructure-layer inheritance ------------------------------------

HAS_OUTCOME_REPO_PREDICATES = {
    "https://w3id.org/sciencelive/o/terms/hasOutcomeRepository",
    "https://w3id.org/sciencelive/o/terms/hasRepository",
    "http://schema.org/codeRepository",
}


def extract_outcome_repos(nodes: dict[str, NodeSummary]) -> list[tuple[str, str]]:
    """For each Outcome (or Research Software) nanopub, find the URI of its
    associated code repository. Returns a list of (nanopub_uri, repo_uri)
    pairs. The repo_uri may be either a GitHub URL or a Zenodo DOI.
    """
    out: list[tuple[str, str]] = []
    for n in nodes.values():
        if not n.raw_trig_path:
            continue
        graph = ConjunctiveGraph()
        try:
            graph.parse(source=n.raw_trig_path, format="trig")
        except Exception:
            continue
        for s, p, o in graph.triples((None, None, None)):
            if str(p) in HAS_OUTCOME_REPO_PREDICATES:
                out.append((n.uri, str(o)))
    return out


def zenodo_doi_to_github(zenodo_doi: str, *, timeout: int = 20) -> str | None:
    """Resolve a Zenodo DOI to its associated GitHub repository URL via
    the Zenodo REST API's `related_identifiers` metadata.
    """
    m = _ZENODO_DOI_RE.search(zenodo_doi)
    if not m:
        return None
    record_id = m.group(1)
    api_url = f"https://zenodo.org/api/records/{record_id}"
    try:
        with urllib.request.urlopen(api_url, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:  # noqa: BLE001
        print(f"    ! Zenodo API failed for {zenodo_doi}: {e}", file=sys.stderr)
        return None
    related = data.get("metadata", {}).get("related_identifiers", [])
    # Prefer `isSupplementTo` → `isDerivedFrom` → any github URL.
    for relation_preference in ("isSupplementTo", "isDerivedFrom", None):
        for ri in related:
            ident = ri.get("identifier", "")
            if _GITHUB_RE.search(ident):
                if relation_preference is None or ri.get("relation") == relation_preference:
                    # Strip /tree/..., /blob/..., trailing slashes.
                    cleaned = ident.split("/tree/")[0].split("/blob/")[0].rstrip("/")
                    return cleaned
    return None


def resolve_repo_url(raw: str, *, timeout: int = 20) -> str | None:
    """Normalise a `hasOutcomeRepository` value to a GitHub URL.
    Accepts a GitHub URL directly or a Zenodo DOI (resolves via Zenodo API).
    """
    raw = raw.strip()
    m = _GITHUB_RE.search(raw)
    if m:
        return m.group(0).rstrip("/")
    if _ZENODO_DOI_RE.search(raw):
        return zenodo_doi_to_github(raw, timeout=timeout)
    return None


def clone_sibling(github_url: str, target_dir: Path) -> Path | None:
    """`git clone` if not already present at `target_dir`. Returns the
    local clone path on success (or if already present), else None.
    """
    if target_dir.exists():
        # Already present — assume it's a valid clone of the same repo.
        return target_dir
    target_dir.parent.mkdir(parents=True, exist_ok=True)
    print(f"    cloning {github_url} → {target_dir}", file=sys.stderr)
    try:
        subprocess.run(
            ["git", "clone", "--depth=1", "--quiet", github_url, str(target_dir)],
            check=True, capture_output=True, timeout=120,
        )
    except subprocess.CalledProcessError as e:
        msg = (e.stderr or b"").decode(errors="replace").strip()
        print(f"    ! clone failed: {msg}", file=sys.stderr)
        return None
    except subprocess.TimeoutExpired:
        print(f"    ! clone timed out after 120 s", file=sys.stderr)
        return None
    return target_dir


def copy_inherited_files(sibling_dir: Path, staging_dir: Path,
                          sibling_name: str) -> list[str]:
    """Copy a curated set of files from `sibling_dir` to `staging_dir`,
    prepending a provenance header to each. Returns the list of relative
    paths copied.
    """
    staging_dir.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []
    for rel in SIBLING_INHERITED_FILES:
        src = sibling_dir / rel
        if not src.is_file():
            continue
        dst = staging_dir / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        content = src.read_text(errors="replace")
        # Choose a sensible comment prefix per extension.
        ext = src.suffix.lower()
        if ext in (".py", ".yml", ".yaml", ".dockerfile") or src.name == "Dockerfile":
            comment = "# "
        elif ext == ".md":
            comment = ""
        else:
            comment = "# "  # fallback
        header_lines = [
            f"{comment}Inherited from prior FORRT chain sibling: {sibling_name}",
            f"{comment}Source: <sibling-repo>/{rel}",
            f"{comment}Review and merge into your replication's own file at the corresponding path,",
            f"{comment}then remove this staging copy. _template_from_prior/ is a reference area",
            f"{comment}only — not the source of truth for this replication.",
            "",
        ]
        dst.write_text("\n".join(header_lines) + content)
        copied.append(rel)
    return copied


def write_setup_inherited(out_path: Path,
                            resolved_repos: list[dict],
                            staging_dir_rel: str) -> None:
    """Write `nanopubs/imported/SETUP_INHERITED.md` documenting what's been
    cloned and what's been staged for review.
    """
    lines = [
        "# Setup inherited from the prior FORRT chain(s)",
        "",
        "Companion to `CHAIN_SUMMARY.md`. The summary documents the *claims*",
        "of the prior chain; this file documents the *infrastructure*",
        "(GitHub repositories, local clones, code/environment scaffolding)",
        "that the import skill has discovered or copied so you can start",
        "the new replication where the prior one ended.",
        "",
        "## Prior-chain repositories",
        "",
    ]
    if not resolved_repos:
        lines.append("*(no `hasOutcomeRepository` URIs were discovered in the imported")
        lines.append("nanopubs — either the chains don't expose them or the predicate")
        lines.append("differs from the ones this script recognises)*")
        lines.append("")
    else:
        lines.append("| Outcome / RS nanopub | Repository URL | Local clone |")
        lines.append("|---|---|---|")
        for r in resolved_repos:
            lines.append(
                f"| `{r['source_nanopub']}` | {r['github_url'] or r['raw_repo_uri']} | "
                f"`{r.get('clone_path') or '(not cloned)'}` |"
            )
        lines.append("")

    if any(r.get("copied_files") for r in resolved_repos):
        lines.append(f"## Files copied to `{staging_dir_rel}` for review")
        lines.append("")
        lines.append("These are starter files from the canonical sibling chain. **They are")
        lines.append("not the source of truth for this replication** — review each one,")
        lines.append("merge with (or replace) your own equivalent in the corresponding")
        lines.append("location, then delete `_template_from_prior/`.")
        lines.append("")
        for r in resolved_repos:
            if not r.get("copied_files"):
                continue
            lines.append(f"### From `{r.get('clone_path') or r['github_url']}`")
            lines.append("")
            for rel in r["copied_files"]:
                lines.append(f"- `{rel}`")
            lines.append("")

    lines.extend([
        "## Suggested next steps",
        "",
        "1. Open `_template_from_prior/pixi.toml` and merge its declared",
        "   dependencies into your own `pixi.toml`; the matching",
        "   `_template_from_prior/pixi.lock` carries the prior chain's",
        "   per-platform pinned versions. After merging, run `pixi install`",
        "   to refresh your own `pixi.lock`, then commit both files.",
        "2. Open `_template_from_prior/notebooks/01_data_download.py` to see",
        "   how the prior chain fetched climate / occurrence / paper data.",
        "   The patterns there — GBIF pre-minted-download style, Polytope",
        "   for DestinE Climate DT, Figshare for CRU TS — generalise to most",
        "   biodiversity-x-climate replications. Adapt the constants",
        "   (download keys, DOIs, file paths) for your replication.",
        "3. If the prior chain has cached data on disk that your replication",
        "   can reuse (CRU TS, DestinE GRIB files, etc.), wire a",
        "   `<REPO_NAME>_SHARED_DATA_DIR` env-var fallback into your",
        "   `01_data_download.py` so locally-cached data is preferred over",
        "   re-downloading. The fallback path goes to the freshly-cloned",
        "   sibling under the local clone path listed in the table above.",
        "4. Delete `_template_from_prior/` once you've merged everything you",
        "   want — it's a one-shot staging area, not durable repo state.",
    ])
    out_path.write_text("\n".join(lines))


def run_inheritance(
    nodes: dict[str, NodeSummary],
    siblings_dir: Path,
    staging_dir: Path,
    enable_clone: bool,
) -> list[dict]:
    """Discover prior-chain repos, optionally clone them, and copy curated
    files to the staging area. Returns a list of per-repo result dicts for
    the SETUP_INHERITED.md report.
    """
    results: list[dict] = []
    repos = extract_outcome_repos(nodes)
    if not repos:
        print("  (no Outcome `hasOutcomeRepository` URIs found — nothing to inherit)",
              file=sys.stderr)
        return results

    # Deduplicate raw repo URIs (multiple Outcomes can point at the same one)
    seen_raw: set[str] = set()
    unique_repos = []
    for src, raw in repos:
        if raw in seen_raw:
            continue
        seen_raw.add(raw)
        unique_repos.append((src, raw))

    for source_uri, raw_repo in unique_repos:
        github_url = resolve_repo_url(raw_repo)
        result = {
            "source_nanopub": source_uri,
            "raw_repo_uri": raw_repo,
            "github_url": github_url,
            "clone_path": None,
            "copied_files": [],
        }
        if not github_url:
            print(f"  ! could not resolve {raw_repo} to a GitHub URL", file=sys.stderr)
            results.append(result)
            continue

        repo_name = github_url.rstrip("/").split("/")[-1]
        clone_path = siblings_dir / repo_name
        if enable_clone:
            clone_result = clone_sibling(github_url, clone_path)
            if clone_result is None:
                results.append(result)
                continue
        else:
            if not clone_path.exists():
                print(f"  --no-clone-siblings: {clone_path} not present locally",
                      file=sys.stderr)
                results.append(result)
                continue

        result["clone_path"] = str(clone_path)
        # Only copy files from the FIRST resolvable sibling (canonical) by
        # default, to avoid clobbering staging with duplicates from each
        # sibling. We mark this as the canonical by being the first repo we
        # successfully clone.
        already_copied = any(r.get("copied_files") for r in results)
        if not already_copied:
            copied = copy_inherited_files(clone_path, staging_dir, repo_name)
            result["copied_files"] = copied
            if copied:
                print(f"    copied {len(copied)} files → {staging_dir}",
                      file=sys.stderr)
        results.append(result)
    return results


# --- Output --------------------------------------------------------------

def write_constellation(nodes: dict[str, NodeSummary],
                         edges: list[EdgeSummary],
                         entry_uri: str,
                         externals: set[str],
                         out_path: Path) -> None:
    payload = {
        "entry": entry_uri,
        "node_count": len(nodes),
        "edge_count": len(edges),
        "sparql_endpoint": NANOPUB_SPARQL_ENDPOINT_FULL,
        "nodes": [
            {
                "uri": n.uri,
                "step_type": n.step_type,
                "template_uri": n.template_uri,
                "authors_orcid": n.authors_orcid,
                "plain_text_excerpts": n.plain_text_excerpts,
                "raw_trig_path": n.raw_trig_path,
            }
            for n in nodes.values()
        ],
        "edges": [
            {"source": e.source, "target": e.target, "relation": e.relation}
            for e in edges
        ],
        "external_citations": sorted(externals),
    }
    out_path.write_text(json.dumps(payload, indent=2))


# --- CLI -----------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Walk a published FORRT nanopub chain from a single entry "
                    "URI, using the Science Live platform's pre-built SPARQL "
                    "queries against the KP nanopub-network endpoint.",
    )
    p.add_argument("uri", help="Entry nanopub URI (e.g. CiTO or Research Synthesis).")
    p.add_argument("--depth", type=int, default=5,
                   help="BFS depth limit (default 5).")
    p.add_argument("--max-nodes", type=int, default=80,
                   help="Total nanopubs to fetch (default 80).")
    p.add_argument("--timeout", type=int, default=30,
                   help="HTTP timeout per fetch in seconds (default 30).")
    p.add_argument("--out-dir", default="nanopubs/imported",
                   help="Output directory (default 'nanopubs/imported').")
    p.add_argument("--siblings-dir", default=DEFAULT_SIBLINGS_DIR,
                   help="Where to clone sibling-chain repositories (default '../', "
                        "matching the convention of putting related repos side-by-side).")
    p.add_argument("--staging-dir", default="_template_from_prior",
                   help="Where to stage inherited files for review "
                        "(default '_template_from_prior'). Review + merge then delete.")
    p.add_argument("--no-clone-siblings", action="store_true",
                   help="Skip git-cloning sibling repos. Inheritance only proceeds "
                        "if siblings happen to be cloned already at --siblings-dir.")
    p.add_argument("--no-inherit", action="store_true",
                   help="Skip the whole infrastructure-inheritance step (no sibling "
                        "discovery, no clone, no file copy, no SETUP_INHERITED.md). "
                        "Use this for a pure claim-layer import.")
    args = p.parse_args(argv)

    canon = canonical_nanopub_uri(args.uri)
    if canon is None:
        print(f"ERROR: {args.uri!r} does not look like a nanopub URI.",
              file=sys.stderr)
        return 2
    if canon != args.uri:
        print(f"  normalised entry URI: {canon}", file=sys.stderr)
    args.uri = canon

    out_dir = Path(args.out_dir)
    cache_dir = out_dir / "trig"
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Importing nanopub chain from {args.uri}", file=sys.stderr)
    print(f"  SPARQL endpoint: {NANOPUB_SPARQL_ENDPOINT_FULL}", file=sys.stderr)
    print(f"  depth limit = {args.depth}, max nodes = {args.max_nodes}",
          file=sys.stderr)

    nodes, edges, externals = walk(
        args.uri, depth_limit=args.depth, max_nodes=args.max_nodes,
        timeout=args.timeout, cache_dir=cache_dir,
    )

    write_constellation(nodes, edges, args.uri, externals,
                         out_dir / "constellation.json")

    if externals:
        (out_dir / "cited_papers.txt").write_text(
            "\n".join(sorted(externals)) + "\n"
        )

    print(file=sys.stderr)
    print(f"Imported {len(nodes)} nanopubs, {len(edges)} edges.", file=sys.stderr)
    print(f"  constellation: {out_dir / 'constellation.json'}", file=sys.stderr)
    print(f"  TriG cache:    {cache_dir}/", file=sys.stderr)
    if externals:
        print(f"  external DOIs: {out_dir / 'cited_papers.txt'} "
              f"({len(externals)} unique)", file=sys.stderr)

    by_type: dict[str, int] = {}
    for n in nodes.values():
        key = n.step_type or "<no template label>"
        by_type[key] = by_type.get(key, 0) + 1
    print(file=sys.stderr)
    print("Step-type breakdown:", file=sys.stderr)
    for t, c in sorted(by_type.items(), key=lambda kv: -kv[1]):
        print(f"  {c:3d} × {t}", file=sys.stderr)

    # Infrastructure-layer inheritance — clone sibling repos and stage
    # files into _template_from_prior/ for the user to review.
    if not args.no_inherit:
        print(file=sys.stderr)
        print("=== Infrastructure inheritance ===", file=sys.stderr)
        siblings_dir = Path(args.siblings_dir).resolve()
        staging_dir = Path(args.staging_dir).resolve()
        siblings_dir.mkdir(parents=True, exist_ok=True)
        results = run_inheritance(
            nodes,
            siblings_dir=siblings_dir,
            staging_dir=staging_dir,
            enable_clone=not args.no_clone_siblings,
        )
        write_setup_inherited(
            out_dir / "SETUP_INHERITED.md",
            resolved_repos=results,
            staging_dir_rel=args.staging_dir,
        )
        print(f"\nSETUP_INHERITED.md → {out_dir / 'SETUP_INHERITED.md'}",
              file=sys.stderr)
        if any(r.get("copied_files") for r in results):
            print(f"Inherited files staged in: {staging_dir}",
                  file=sys.stderr)
            print("Review + merge into your own files, then delete the staging dir.",
                  file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
