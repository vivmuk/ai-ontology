# ai-ontology

A living ontology of **emerging AI concepts (2024 → now)**, grown weekly by an
agent pipeline. Inspired by [NVIDIA/auto-ontology](https://github.com/NVIDIA/auto-ontology)
("take a repo, keep its ontology current") — this repo *is* the ontology, and it
updates itself.

## What's in here

- `ontology.yaml` — the artifact: concepts (id, label, category, first_seen,
  summary, sources, status) and typed relations (enables / derives_from /
  supersedes / extends / used_with / contrasts_with), everything dated and sourced.
- `ontology.json` — machine copy for the viewer and for pipelines.
- `index.html` — force-directed graph viewer (dark, category-colored, click a
  node for its card; dashed ring = emerging, solid = established). Serve
  statically or via GitHub Pages.
- `update.py` — the weekly updater. Discovers genuinely new AI concepts from the
  last 7 days via the **Venice API** (gemini-3-5-flash, web search on),
  normalizes/validates them, merges into the ontology, appends `CHANGELOG.md`,
  commits (and pushes with `--push`).
- `verify.sh` — invariant checks: unique ids, valid categories/statuses/types,
  no dangling relations, parseable artifact.
- `CHANGELOG.md` — append-only human log of every weekly merge.

## Weekly update

```bash
.venv/bin/python update.py --push        # discover, merge, commit, push
.venv/bin/python update.py --dry-run      # see the proposal first
.venv/bin/python update.py --repo /path/to/other/checkout
```

Venice key resolution: `--key`, `$VENICE_API_KEY`, or
`~/.config/ai-ontology/venice.key` (mode 600).

It's wired to a Hermes cron that runs it weekly and reports the diff.

## Baseline and growth policy

- Baseline seeded 2024→now: test-time compute scaling, reasoning models, RLVR,
  MCP, agentic coding, MoE, SSM hybrids, GraphRAG, agentic RAG, world models,
  KV-cache compression, inference cost collapse, evals for scheming, and ~35 more.
- Weekly discovery adds up to 6 concepts max — genuinely new traction only
  (papers, frontier releases, adopted protocols), never news items or rebrands.
- A concept can graduate `emerging → established`, or be marked `absorbed`
  when folded into a successor.
- Categories: reasoning, agents, architecture, training, retrieval, multimodal,
  infrastructure, interaction-protocols, evaluation, safety.

## Interop

The YAML is deliberately close to Auto Ontology's model-interchange document
(`auto_ontology` dialect) so a concept layer can be imported there later; the
relation set is a strict subset of what a semantic layer can map onto.
