# Personalization Guide: Memory + Preference Feedback

This guide explains how to run PaperFeeder with:
- Semantic Scholar anti-repetition memory
- Human preference feedback (positive/negative/undecided reset)
- Queue-first apply flow

## 1. What each file does

- `semantic_scholar_seeds.json`
  - Your preference profile (what to prefer/avoid)
  - Keys:
    - `positive_paper_ids`
    - `negative_paper_ids`

- `semantic_scholar_memory.json`
  - Short-term anti-repetition memory
  - Stores unified cross-source seen keys with timestamps
  - Key namespaces:
    - `arxiv:<id>` (canonical when arXiv id exists)
    - `semantic:<CorpusId...>` (semantic compatibility)
    - legacy raw semantic ids (for migration compatibility)
    - `hf:<normalized-url>` (HF fallback without arXiv id)

- `artifacts/run_feedback_manifest_<run_id>.json`
  - Mapping between final report items and semantic paper IDs for that run

- `feedback_events` (D1 table)
  - Queue of web feedback clicks (`pending` -> `applied`/`rejected`)

## 2. How the recommendation loop works

1. Fetch Semantic Scholar candidates from your seed profile.
2. Suppress recently seen keys (memory TTL window) across Semantic Scholar/arXiv/HF.
3. Run filtering + synthesis and generate digest.
4. If you click feedback in web viewer, events are queued to D1 (`pending`).
5. Manual apply action updates `semantic_scholar_seeds.json`.
6. Next run uses updated seeds + memory.

No automatic seed mutation happens on click. Apply remains manual by design.

## 3. Minimum configuration

In `config.yaml`:

```yaml
semantic_scholar_enabled: true
semantic_scholar_max_results: 30
semantic_scholar_seeds_path: "semantic_scholar_seeds.json"
semantic_memory_enabled: true
semantic_memory_path: "semantic_scholar_memory.json"
semantic_seen_ttl_days: 30
semantic_memory_max_ids: 5000
```

For web feedback:

```bash
FEEDBACK_ENDPOINT_BASE_URL=https://paperfeeder-feedback.<subdomain>.workers.dev
FEEDBACK_LINK_SIGNING_SECRET=<shared-secret>
FEEDBACK_TOKEN_TTL_DAYS=7
```

For D1 apply:

```bash
CLOUDFLARE_ACCOUNT_ID=<account-id>
CLOUDFLARE_API_TOKEN=<api-token>
D1_DATABASE_ID=<database-id>
```

## 4. Daily operator workflow

1. Run digest (local or GitHub Action).
2. Open email digest.
3. Click one run-level link to open web viewer.
4. Click `positive` / `negative` / `undecided` on papers you care about.
5. Run manual apply action:
   - `Apply Feedback Queue` (`dry_run=false`)
6. Next digest reflects updated preference seeds.

Label semantics:
- `positive` -> add to positive and remove from negative
- `negative` -> add to negative and remove from positive
- `undecided` -> remove from both (reset)

## 5. State branch model (recommended)

Use a separate branch for mutable state (default `memory-state`):
- digest workflow loads seeds + memory from state branch
- apply workflow writes updated seeds to state branch
- digest workflow writes updated memory to state branch

This keeps `main` focused on code and avoids frequent bot-commit conflicts.

Repo variable:

```bash
SEED_STATE_BRANCH=memory-state
```

Default:
- If `SEED_STATE_BRANCH` is not set, workflows automatically fall back to `memory-state`.

## 6. Dedup behavior (important)

Current default dedup rules:
- Papers: `arxiv_id` first, else `url`
- Blogs: exact `url`

Memory suppression rules (separate from fetch dedup):
- canonical preference is `arxiv:<id>` when available
- Semantic Scholar keeps dual-read/dual-write compatibility (`semantic:*` + legacy raw id)
- only report-visible final papers are written into memory

Title-based dedup is not the default pipeline key right now.

If you need strict title dedup, add a post-fetch normalization step:
- normalize title (lowercase, trim spaces, remove punctuation noise)
- dedup on normalized title before coarse filter

## 7. Troubleshooting

- Repeated recommendations from Semantic Scholar:
  - Check `semantic_memory_enabled`, TTL, and memory file updates.

- Feedback clicks recorded but seeds unchanged:
  - You likely skipped manual apply.
  - Run `Apply Feedback Queue` with `dry_run=false`.

- Many `rejected` events:
  - Check `error` in D1 table.
  - Most common causes are invalid token/label or superseded older click.

- Email client odd behavior on links:
  - Keep email as notification-only and use web viewer for interactions.
  - Prefer custom domain if deliverability policies are strict.
