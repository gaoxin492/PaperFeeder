<h1 align="left">
  <img src=".github/assets/icon.png" alt="PaperFeeder icon" width="44" style="vertical-align: middle; margin-right: 10px;" />
  <span style="vertical-align: middle;">PaperFeeder</span>
</h1>

> A research intelligence agent pipeline for daily paper and blog triage to your email inbox.

PaperFeeder is designed around an inbox workflow: the digest is delivered by email, while the web viewer, manifests, and feedback pipeline support review, iteration, and feedback collection around that core experience.

**中文说明：** [README.zh-CN.md](README.zh-CN.md)

## Preview

<table>
  <tr>
    <td align="center"><img src=".github/assets/preview-overview.png" alt="Digest overview" width="240" /></td>
    <td align="center"><img src=".github/assets/preview-paper-detail.png" alt="Paper detail" width="240" /></td>
    <td align="center"><img src=".github/assets/preview-summary.png" alt="Executive summary and feedback" width="240" /></td>
  </tr>
  <tr>
    <td align="center"><strong>1.</strong> Overview</td>
    <td align="center"><strong>2.</strong> Paper deep dive</td>
    <td align="center"><strong>3.</strong> Summary + quick feedback</td>
  </tr>
</table>

## Why PaperFeeder

PaperFeeder is a lightweight research intelligence system for people who do not want to manually skim hundreds of links every day, and who want the final output delivered as a high-signal email digest rather than another dashboard to check.

It is built for a simple outcome:

1. ingest high-volume paper and blog streams
2. reduce them into a small, high-signal candidate set
3. generate an opinionated digest instead of a raw feed dump
4. remember what has already been shown recently
5. improve future recommendations from explicit feedback
6. run either locally or as a remote scheduled service

The product is intentionally centered on inbox delivery: email is the main delivery surface for the research brief, while the other components support that workflow.

What makes it more than a paper-summary script is the layering:

| Layer | What it adds |
|------|--------------|
| Multi-source collection | arXiv, Hugging Face daily papers, Semantic Scholar recommendations, curated blogs, optional manual sources |
| Multi-stage selection | keyword gating, coarse LLM filtering, external signal enrichment, fine reranking |
| PDF-aware synthesis | summaries can use PDFs when available, not only titles and abstracts |
| Stateful personalization | short-term anti-repetition memory is separated from long-term preference steering |
| Explicit feedback loop | per-item feedback updates future recommendation inputs |
| Deployable operations | local dry-runs, debug fixtures, GitHub Actions scheduling, Cloudflare Worker + D1 feedback path |

Core capabilities:

| Capability | Details |
|-----------|---------|
| Personalized candidate generation | user-editable interests, keywords, excluded terms, arXiv categories, and curated blogs under `user/` |
| Semantic Scholar steering | positive and negative seed papers influence recommendation fetches |
| Anti-repetition memory | `state/semantic/memory.json` suppresses recently shown items |
| Two-stage LLM filtering | stage 1 trims the pool; stage 2 reranks after external research |
| External signal enrichment | Tavily adds implementation, community, and reproducibility signals |
| Better digest writing | prompt language packs, PDF-aware inputs, HTML output for email and web |
| One-click feedback | email and web viewer links go through Cloudflare Worker + D1 |
| Reproducible artifacts | each run exports manifests and feedback templates under `artifacts/` |

## How It Works

PaperFeeder deliberately separates candidate generation, ranking, reporting, freshness, and preference learning.

### End-to-End Pipeline

1. Collect candidates from papers and blogs.
2. Apply keyword and exclusion rules.
3. Run coarse LLM filtering on title and abstract.
4. Enrich shortlisted papers with external signals.
5. Run fine LLM reranking using both content and signals.
6. Read PDFs when available and generate a polished digest.
7. Send the digest by email and optionally publish a web-view copy.
8. Persist short-term memory for anti-repetition.
9. Convert explicit feedback into future recommendation steering.

### State Model

| State | File / store | Purpose |
|------|---------------|---------|
| Short-term memory | `state/semantic/memory.json` | suppress recently seen items so the digest stays fresh |
| Long-term preferences | `state/semantic/seeds.json` | store positive / negative Semantic Scholar seed IDs |
| Per-run artifacts | `artifacts/run_feedback_manifest_*.json`, `artifacts/semantic_feedback_template_*.json` | map run items to feedback actions and offline review |
| Remote feedback queue | Cloudflare D1 | store pending 👍 / 👎 events before they are applied to seeds |

The distinction is important:

1. `memory.json` means “show this less because it was seen recently”
2. `seeds.json` means “recommend more or less of this kind of paper in the future”

Neither file changes model weights. They only change the candidate pool and recommendation inputs.

### Repository Map

```text
PaperFeeder/
├── paperfeeder/          # Main Python package
├── scripts/              # Bootstrap and feedback helpers
├── cloudflare/           # Worker source and D1 schema
├── state/semantic/       # Persistent memory and seeds
├── artifacts/            # Per-run generated manifests/templates
├── user/                 # User-editable profiles, keywords, prompt text, blogs
├── tests/                # Test suite
├── config.yaml           # Main project configuration
├── icon.png              # README / project icon
└── main.py               # Main digest entrypoint
```

Key files:

1. `paperfeeder/pipeline/runner.py`: orchestrates the full pipeline
2. `paperfeeder/pipeline/filters.py`: keyword filter plus coarse/fine LLM filtering
3. `paperfeeder/pipeline/summarizer.py`: report synthesis and HTML wrapping
4. `paperfeeder/pipeline/researcher.py`: Tavily-based external signal enrichment
5. `paperfeeder/semantic/memory.py`: anti-repetition memory store
6. `paperfeeder/cli/apply_feedback.py`: apply offline, queued, or D1 feedback into seeds
7. `cloudflare/feedback_worker.js`: one-click feedback collection and run viewer endpoint

## Local Setup And Configuration

### What You Need

| Component | Required | Why |
|----------|----------|-----|
| LLM API | Yes | digest synthesis and, if enabled, LLM filtering |
| Email provider | Optional for local preview, required for real use | deliver the digest in its intended email-first format |
| Tavily API | Optional but recommended | external signal enrichment |
| Semantic Scholar API | Strongly recommended | better ID resolution for personalization and feedback links |
| Cloudflare Worker + D1 | Optional | one-click remote feedback loop |

### Local Setup

```bash
bash scripts/bootstrap.sh
source .venv/bin/activate
```

Then:

1. copy `.env.example` to `.env`
2. fill in local credentials for LLM, email, and optional feedback services
3. edit `config.yaml` for toggles, limits, and paths
4. edit `user/blogs.yaml` for blog sources
5. edit files under `user/` for interests, keywords, exclusions, categories, and prompt additions

Local `.env` is for local development and local testing. GitHub Actions deployments should use GitHub Secrets and Variables instead.

If you only remember one setup principle, make it this: the primary user experience is the email digest. Local preview is for iteration; production setup should be optimized around reliable inbox delivery.

### User-Editable Files

| File | What it controls |
|------|------------------|
| `config.yaml` | runtime toggles, fetch windows, path settings, prompt language, state behavior |
| `user/blogs.yaml` | blog source selection and custom feeds |
| `user/research_interests.txt` | research persona / long-form interests |
| `user/keywords.txt` | positive keyword hints |
| `user/exclude_keywords.txt` | noisy topics to suppress |
| `user/arxiv_categories.txt` | arXiv category scope |
| `user/prompt_addon.txt` | extra instruction block injected into prompts |

Config precedence:

1. `config.yaml`
2. `user/blogs.yaml`
3. environment variables
4. `user/research_interests.txt`, `user/prompt_addon.txt`, `user/keywords.txt`, `user/exclude_keywords.txt`, and `user/arxiv_categories.txt`

Preset profiles are available under `user/examples/profiles/`.

### Common Commands

Main digest:

```bash
python main.py --dry-run
python main.py --days 3
```

Debug mode with a fixed JSON fixture:

```bash
python main.py --debug-sample --dry-run
python main.py --debug-sample
python main.py --debug-sample --debug-llm-report --dry-run
python main.py --debug-minimal-report --dry-run
python main.py --debug-sample --debug-sample-path path/to/papers.json --dry-run
```

Optional: `--debug-write-memory` updates `state/semantic/memory.json` during debug sample mode.

Apply reviewed feedback from a manifest:

```bash
python -m paperfeeder.cli.apply_feedback --manifest-file artifacts/run_feedback_manifest_<run_id>.json --dry-run
python -m paperfeeder.cli.apply_feedback --manifest-file artifacts/run_feedback_manifest_<run_id>.json
```

Apply pending feedback from Cloudflare D1:

```bash
python -m paperfeeder.cli.apply_feedback --from-d1 --manifest-file artifacts/run_feedback_manifest_<run_id>.json --manifests-dir artifacts --dry-run
python -m paperfeeder.cli.apply_feedback --from-d1 --manifest-file artifacts/run_feedback_manifest_<run_id>.json --manifests-dir artifacts
```

There is also a wrapper script:

```bash
python scripts/semantic_feedback_apply.py --manifest-file artifacts/run_feedback_manifest_<run_id>.json --dry-run
```

## Remote Deployment With GitHub Actions

If you want PaperFeeder to behave like a remote service, GitHub Actions is the main deployment path. In practice, this is how you turn it into an automated email brief that lands in your inbox every morning.

### Workflow Roles

| Workflow | Purpose |
|----------|---------|
| `.github/workflows/daily-digest.yml` | run the digest on schedule, send email, persist `memory.json` |
| `.github/workflows/apply-feedback-queue.yml` | periodically merge D1 feedback into `seeds.json` |

### Required Secrets And Variables

Required GitHub Secrets for minimal remote email delivery:

1. `LLM_API_KEY`
2. `LLM_MODEL`
3. `RESEND_API_KEY`
4. `EMAIL_TO`

Common additional Secrets:

1. `LLM_BASE_URL`
2. `LLM_FILTER_API_KEY`
3. `LLM_FILTER_BASE_URL`
4. `LLM_FILTER_MODEL`
5. `TAVILY_API_KEY`
6. `SEMANTIC_SCHOLAR_API_KEY`
7. `CLOUDFLARE_ACCOUNT_ID`
8. `CLOUDFLARE_API_TOKEN`
9. `D1_DATABASE_ID`
10. `FEEDBACK_ENDPOINT_BASE_URL`
11. `FEEDBACK_LINK_SIGNING_SECRET`

Recommended GitHub Variables:

1. `SEED_STATE_BRANCH`
2. `SEMANTIC_MEMORY_ENABLED`
3. `SEMANTIC_SEEN_TTL_DAYS`
4. `SEMANTIC_MEMORY_MAX_IDS`
5. `FEEDBACK_TOKEN_TTL_DAYS`
6. `FEEDBACK_REVIEWER`

### Current Default Schedule

| Workflow | UTC | China Standard Time |
|----------|-----|---------------------|
| `daily-digest.yml` | `1 0 * * *` | every day at 08:01 |
| `apply-feedback-queue.yml` | `30 16 */3 * *` | every 3 days at 00:30 on the next day |

GitHub Actions cron is based on UTC calendar time, not a strict every-72-hours timer. A pattern like `*/3` resets at month boundaries.

### First Remote Deployment

1. push the repo to GitHub and enable Actions
2. add Secrets and Variables in the repository settings
3. manually run `Daily Paper Digest` with `dry_run=true`
4. inspect logs and artifacts
5. run it once with `dry_run=false`
6. confirm the state branch is created and updated

State handling:

1. workflows do not write runtime state back to `main`
2. they use a dedicated state branch, defaulting to `memory-state`
3. that branch stores `state/semantic/memory.json` and `state/semantic/seeds.json`

### Remote Operating Modes

Minimum useful remote setup for daily email only:

1. `LLM_*` secrets
2. `RESEND_API_KEY`
3. `EMAIL_TO`
4. `daily-digest.yml`

Full closed-loop setup:

1. everything above
2. Cloudflare Worker deployment
3. D1 database and credentials
4. `apply-feedback-queue.yml`

In the full mode, the loop is:

1. `daily-digest.yml` sends the digest
2. readers submit feedback through email or web links
3. events are stored in D1
4. `apply-feedback-queue.yml` writes them back into `seeds.json`
5. future Semantic Scholar recommendations change accordingly

## Tests

```bash
python -m unittest discover -s tests -p "test_*.py" -v
```

## Notes

1. `artifacts/` and `llm_filter_debug/` are disposable runtime outputs.
2. GitHub Actions persist `state/semantic/seeds.json` and `state/semantic/memory.json` on the state branch.