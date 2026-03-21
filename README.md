# PaperFeeder

PaperFeeder is a daily paper-and-blog digest pipeline with Semantic Scholar based personalization and a feedback loop.

**中文说明：** [README.zh-CN.md](README.zh-CN.md)

## Final Layout

```text
PaperFeeder/
├── paperfeeder/          # Main Python package
├── scripts/              # Bootstrap and feedback helper scripts
├── cloudflare/           # Feedback worker and D1 schema
├── state/semantic/       # Persistent personalization state
├── artifacts/            # Per-run generated manifests/templates
├── user/                 # User-editable text profiles and prompt snippets
├── tests/                # Test suite
├── config.yaml           # Project defaults
└── main.py               # Main digest entrypoint
```

## What Each Directory Means

`paperfeeder/`

- All real application code lives here now.
- Flat, obvious modules at the top: `models.py` (papers/authors), `email.py` (senders), `chat.py` (OpenAI-style chat client).
- The main pipeline is under `paperfeeder/pipeline/runner.py`.
- Feedback apply CLI lives in `paperfeeder/cli/apply_feedback.py`.

`state/semantic/`

- `state/semantic/seeds.json` stores long-lived positive and negative Semantic Scholar seed IDs.
- `state/semantic/memory.json` stores recently seen paper keys so repeated papers can be suppressed.
- This is runtime state, not source code.

`artifacts/`

- This contains generated run outputs such as `run_feedback_manifest_*.json` and `semantic_feedback_template_*.json`.
- It is disposable runtime output and is ignored by git.

`cloudflare/`

- `cloudflare/feedback_worker.js` is the only feedback worker source.
- `cloudflare/d1_feedback_events.sql` is the D1 schema.

## Setup

```bash
bash scripts/bootstrap.sh
source .venv/bin/activate
```

Then fill in `.env`, edit `config.yaml` for toggles and paths, edit `user/blogs.yaml` for blog sources, and edit files under `user/` for research preferences. The common user files are `user/blogs.yaml`, `user/research_interests.txt`, `user/keywords.txt`, `user/exclude_keywords.txt`, `user/arxiv_categories.txt`, and `user/prompt_addon.txt`.

That local `.env` is mainly for local development and local testing. For GitHub Actions deployments, use GitHub Secrets and Variables instead; the workflows should not depend on a repository `.env` file.

If you want the generated report prompt to be English-first instead of Chinese-first, set `prompt_language` in `config.yaml` to `en-US`.

If you want a different starting point, look at the preset profiles under `user/examples/profiles/` and either copy the files you want into `user/`, or point `config.yaml` at a preset path.

## How To Run

Main digest:

```bash
python main.py --dry-run
python main.py --days 3
```

`--dry-run` writes `report_preview.html` locally and may generate feedback files under `artifacts/`.

**Lightweight debug (one paper, no crawl):** use a JSON fixture instead of fetching arXiv/HF/S2. Skips keyword+LLM filters and Tavily enrichment. **By default, `--debug-sample` does not call the main digest LLM** — it sends a small fixed HTML body (good for testing email, feedback, D1). Copy `tests/debug_sample.example.json` to `tests/debug_sample.json` and edit (or rely on the bundled example when no override exists).

```bash
# Stub HTML only, no main digest LLM; local preview (omit --dry-run to send email)
python main.py --debug-sample --dry-run

# Same stub, real email via Resend
python main.py --debug-sample

# Debug sample but use the real summarizer LLM for the report body
python main.py --debug-sample --debug-llm-report --dry-run

# Full fetch, but stub report body (no main digest LLM)
python main.py --debug-minimal-report --dry-run

# Custom fixture path
python main.py --debug-sample --debug-sample-path path/to/papers.json --dry-run
```

Optional: `--debug-write-memory` updates `state/semantic/memory.json` (default in debug sample mode is to skip it).

Apply reviewed feedback from a manifest:

```bash
python -m paperfeeder.cli.apply_feedback --manifest-file artifacts/run_feedback_manifest_<run_id>.json --dry-run
python -m paperfeeder.cli.apply_feedback --manifest-file artifacts/run_feedback_manifest_<run_id>.json
```

Apply pending feedback from Cloudflare D1:

```bash
python -m paperfeeder.cli.apply_feedback --from-d1 --manifest-file artifacts/run_feedback_manifest_<run_id>.json --manifests-dir artifacts --dry-run
```

There is also a wrapper if you prefer scripts:

```bash
python scripts/semantic_feedback_apply.py --manifest-file artifacts/run_feedback_manifest_<run_id>.json --dry-run
```

## Configuration

The main configuration lives in `config.yaml`. Use it for toggles, fetch windows, and paths. Use `user/blogs.yaml` for blog selection and custom RSS feeds. Use other files under `user/` for research profile text, keywords, categories, and prompt additions. The semantic state paths are:

```yaml
semantic_scholar_seeds_path: "state/semantic/seeds.json"
semantic_memory_path: "state/semantic/memory.json"
```

Config precedence is:

1. `config.yaml`
2. `user/blogs.yaml`
3. environment variables
4. `user/research_interests.txt`, `user/prompt_addon.txt`, `user/keywords.txt`, `user/exclude_keywords.txt`, and `user/arxiv_categories.txt`

Each list file in `user/` uses one item per line. Blank lines and lines starting with `#` are ignored.

## Preset Profiles

Preset starting points live under `user/examples/profiles/`:

- `frontier-ai-lab`
- `interpretability-alignment`
- `coding-agents-reasoning`
- `multimodal-generative`

Each profile contains a `research_interests.txt`, `keywords.txt`, `exclude_keywords.txt`, and `arxiv_categories.txt`.

## Memory

`memory` and `feedback` solve different problems.

### What `memory.json` does

`state/semantic/memory.json` exists to remember what the system has already shown you recently.

It is used to:

1. suppress repeated recommendations
2. reduce near-duplicate daily digests
3. keep the candidate set fresh across runs

It is not a preference model and it does not fine-tune the LLM.

### What `seeds.json` does

`state/semantic/seeds.json` stores explicit positive and negative Semantic Scholar paper IDs.

It is used to:

1. steer Semantic Scholar recommendations toward papers like the ones you liked
2. steer them away from papers you disliked

So the distinction is:

1. `memory.json` means “I have already seen this recently”
2. `seeds.json` means “I explicitly like or dislike this kind of paper”

### How they affect the daily digest

On each run:

1. the pipeline fetches candidates from arXiv, blogs, and optional Semantic Scholar recommendations
2. `memory.json` suppresses recently seen items
3. `seeds.json` influences which Semantic Scholar recommendations get fetched in the first place

Neither file changes model weights. They only change the candidate pool.

## Feedback

Feedback is a separate loop from memory.

### What feedback does

Feedback turns explicit 👍 / 👎 events into updates to `seeds.json`.

The flow is:

1. `python main.py` generates a digest
2. the run exports manifest/template files into `artifacts/`
3. feedback links point to the worker in `cloudflare/`
4. the worker writes events into D1
5. `apply_feedback` converts those events into updates to `state/semantic/seeds.json`

So feedback does not immediately rewrite today's report. It changes future recommendation inputs.

### Core feedback configuration

Copy `.env.example` → `.env` and focus on these first:

| What | Where to set | Why it matters |
|------|--------------|----------------|
| **Worker URL** | `.env` → `FEEDBACK_ENDPOINT_BASE_URL` | Where email feedback links point |
| **Signing secret** | `.env` + Worker → `FEEDBACK_LINK_SIGNING_SECRET` | Prevents forged feedback tokens |
| **D1 access** | `.env` → `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_API_TOKEN`, `D1_DATABASE_ID` | Lets Python upload reports and read feedback |
| **Semantic Scholar API** | `.env` → `SEMANTIC_SCHOLAR_API_KEY` | Improves `semantic_paper_id` resolution so feedback buttons appear |
| **Feedback attachments** | `.env` → `FEEDBACK_EMAIL_ATTACHMENTS` | Controls whether manifest/template JSON files are attached to email |

### Minimal Worker deployment

```bash
cd cloudflare
cp wrangler.toml.example wrangler.toml
# Edit wrangler.toml: set database_id from `wrangler d1 create paperfeeder-feedback`
npx wrangler d1 execute paperfeeder-feedback --remote --file=d1_feedback_events.sql
npx wrangler secret put FEEDBACK_LINK_SIGNING_SECRET
npx wrangler deploy
```

Then set `FEEDBACK_ENDPOINT_BASE_URL` in `.env` to the deployed URL.

The “Open Feedback Web Viewer” banner is optional. It is just a browser entry point to `/run?run_id=...`. The actual feedback loop is driven by per-item 👍 / 👎 links.

## GitHub Actions

This is the most important section if you want PaperFeeder to run remotely and send a daily digest automatically.

There are two key workflows:

| Workflow | Purpose |
|----------|---------|
| `.github/workflows/daily-digest.yml` | Runs the digest on a schedule, sends email, and persists `memory.json` |
| `.github/workflows/apply-feedback-queue.yml` | Periodically merges D1 feedback into `seeds.json` |

### What each workflow does

#### `daily-digest.yml`

By default it:

1. runs every day at `00:01 UTC`, which is `08:01` China Standard Time
2. loads `state/semantic/memory.json` and `state/semantic/seeds.json` from the state branch
3. runs `python main.py`
4. pushes updated `memory.json` back to the state branch

This workflow is what makes remote daily email delivery work.

#### `apply-feedback-queue.yml`

By default it:

1. runs every 3 days at `16:30 UTC` with `30 16 */3 * *`, which is `00:30` China Standard Time on the next day
2. loads `seeds.json` from the state branch
3. reads pending feedback from D1
4. runs `python -m paperfeeder.cli.apply_feedback --from-d1`
5. pushes updated `seeds.json` back to the state branch

This workflow is what closes the feedback loop.

### What the state branch is

The workflows do not write runtime state back to `main`.

Instead they use a dedicated branch:

1. default: `memory-state`
2. overrideable with the repo variable `SEED_STATE_BRANCH`

That branch stores:

1. `state/semantic/memory.json`
2. `state/semantic/seeds.json`

This keeps code and runtime state separate.

### Minimal remote deployment for daily sending

If your goal is “run remotely and send every day”, follow this order.

#### 1. Push the repo to GitHub

1. create your repo
2. push the code
3. enable GitHub Actions

#### 2. Add required GitHub Secrets

Use this mental model: local runs read `.env`; GitHub Actions runs read GitHub Secrets and Variables. Keep those two paths separate and do not commit your local `.env`.

At minimum, set these in `Settings -> Secrets and variables -> Actions -> Secrets`:

1. `LLM_API_KEY`
2. `LLM_MODEL`
3. `RESEND_API_KEY`
4. `EMAIL_TO`

Common additional secrets:

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

#### 3. Add GitHub Variables

Recommended variables in `Settings -> Secrets and variables -> Actions -> Variables`:

1. `SEED_STATE_BRANCH`
2. `SEMANTIC_MEMORY_ENABLED`
3. `SEMANTIC_SEEN_TTL_DAYS`
4. `SEMANTIC_MEMORY_MAX_IDS`
5. `FEEDBACK_TOKEN_TTL_DAYS`
6. `FEEDBACK_REVIEWER`

#### 4. Run `Daily Paper Digest` manually once

Use `workflow_dispatch` first:

1. run once with `dry_run=true`
2. inspect artifacts and logs
3. then run with `dry_run=false`

The first non-dry-run execution will also initialize the state branch if needed.

#### 5. Confirm the schedule

Current defaults:

1. `daily-digest.yml`: `1 0 * * *`
2. `apply-feedback-queue.yml`: `30 16 */3 * *`

Both are UTC. Change the cron expressions if you want a different time zone or cadence.

Use this approach when customizing the schedule:

1. pick the local time you actually want
2. convert that time to UTC
3. put the UTC value into the workflow `schedule.cron`

Examples:

1. If you are in China Standard Time (`UTC+8`) and want `daily-digest.yml` at 08:01 local time, use `1 0 * * *`
2. If you want `apply-feedback-queue.yml` every 3 days at 00:30 China time, use `30 16 */3 * *`

One important limitation: GitHub Actions cron is based on UTC calendar time, not a strict “every 72 hours” timer. A pattern like `*/3` means “every 3rd day of the month”, so the cadence resets at month boundaries. That is usually fine here. If you need an exact 72-hour interval, run the workflow daily and gate execution inside the script instead.

### What happens every day in remote mode

Each day:

1. GitHub Actions triggers `daily-digest.yml`
2. the workflow restores yesterday's `memory.json` / `seeds.json`
3. it runs `main.py`
4. it sends the email
5. it writes the updated `memory.json` back to the state branch

If readers submit feedback:

1. events go into D1
2. `apply-feedback-queue.yml` later merges them into `seeds.json`
3. future Semantic Scholar recommendations change accordingly

### Minimum setup if you only want remote daily email

If feedback is not important yet, the minimum useful remote setup is:

1. `LLM_*` secrets
2. `RESEND_API_KEY`
3. `EMAIL_TO`
4. `daily-digest.yml`

That already gives you:

1. remote daily digest generation
2. remote email delivery
3. persistent `memory.json`

Add Cloudflare + D1 + `apply-feedback-queue.yml` later when you want the full feedback loop.

## Tests

```bash
python -m unittest discover -s tests -p "test_*.py" -v
```

## Notes

- `artifacts/` and `llm_filter_debug/` are ignored runtime output directories.
- GitHub Actions also read and persist `state/semantic/seeds.json` and `state/semantic/memory.json` on the state branch; see **GitHub Actions, `seeds.json`, and what “memory” does** above.
