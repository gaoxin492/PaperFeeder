# Semantic Scholar Integration Plan (Minimal Changes)

Assumption: we already have a valid Semantic Scholar API key.

## Goal

Add Semantic Scholar as an additional paper source so daily recommendations feed into the existing pipeline:

`Fetch -> Keyword Filter -> LLM Coarse Filter -> Tavily Enrichment -> LLM Fine Filter -> Report/Email`

No new product/dashboard in V1. No major architecture refactor.

## Scope (V1)

- Add one new source: `SemanticScholarSource`
- Use seed-driven recommendations (positive + negative paper IDs from local JSON)
- Merge and deduplicate with current sources (arXiv + HuggingFace + manual)
- Keep all downstream filtering/summarization logic unchanged

Out of scope:

- UI/dashboard
- DB storage/migrations
- Browser automation from personal Semantic Scholar account

## Design (Concrete)

## 1) New config fields (in `config.py` + `config.yaml`)

- `semantic_scholar_enabled: bool = False`
- `semantic_scholar_api_key: str = ""`
- `semantic_scholar_max_results: int = 50`
- `semantic_scholar_seeds_path: str = "semantic_scholar_seeds.json"`

Environment override:

- `SEMANTIC_SCHOLAR_API_KEY`

## 2) New seed file (repo file)

Create `semantic_scholar_seeds.json`:

```json
{
  "positive_paper_ids": [],
  "negative_paper_ids": []
}
```

Rules:

- IDs are Semantic Scholar `paperId` values
- Keep this file user-maintained (manual update with newly liked/disliked papers)

## 3) Implement source (in `sources/paper_sources.py`)

Implement `SemanticScholarSource.fetch(...)`:

- Read seed IDs from `semantic_scholar_seeds.json`
- If no positive IDs, return empty list with warning log
- Call recommendations endpoint:
  - `POST https://api.semanticscholar.org/recommendations/v1/papers/`
- Request fields needed for pipeline compatibility:
  - `paperId,title,abstract,authors,year,venue,url,externalIds`
- Convert results to `Paper` objects:
  - `source = PaperSource.SEMANTIC_SCHOLAR`
  - set `arxiv_id` from `externalIds.ArXiv` if present
  - set `url` to S2 or arXiv URL
  - set `pdf_url` to arXiv PDF URL when arXiv ID exists

Error handling:

- 401/403: invalid key -> clear warning, return `[]`
- 429: rate limit -> retry with backoff, then return partial/empty
- timeout/network errors -> return `[]` (do not break full pipeline)

## 4) Wire source into pipeline (in `main.py`)

Inside `fetch_papers(...)`:

- If `semantic_scholar_enabled` and key present:
  - instantiate `SemanticScholarSource(...)`
  - fetch recommendations
  - append to `papers`
  - log count

Keep existing dedup logic:

- key = `arxiv_id or url` (already present)

## 5) Export/source plumbing

- Ensure `sources/__init__.py` export remains correct (already includes `SemanticScholarSource`)

## 6) GitHub Actions support (no workflow logic change needed)

Add one repo secret:

- `SEMANTIC_SCHOLAR_API_KEY`

No schedule/job changes required.

## Request Efficiency Plan

- One recommendations call per run (normal mode)
- Optional small retry policy for 429/timeout
- Max results capped (default 50)
- Local dedup prevents unnecessary downstream processing

Expected request volume:

- Typical: 5-30/day
- Peak debug days: <100/day

## Validation Plan

## Local

1. Add `SEMANTIC_SCHOLAR_API_KEY` to `.env`
2. Set `semantic_scholar_enabled: true` in `config.yaml`
3. Add at least 3 positive seed IDs
4. Run `python main.py --dry-run`
5. Verify logs show non-zero S2 count and pipeline completes

## GitHub Actions

1. Add secret `SEMANTIC_SCHOLAR_API_KEY`
2. Manual run with `dry_run=true`
3. Confirm report artifact contains S2-fed papers

## Risks and Mitigations

- Seed quality too narrow -> weak recommendations
  - Mitigation: keep 10-30 diverse positive IDs and prune negatives regularly
- Occasional API throttling/latency
  - Mitigation: retry with backoff; graceful fallback to existing sources
- Missing abstracts/metadata on some papers
  - Mitigation: keep paper with best available fields; let LLM filter handle low-quality candidates

## Checklist

- [ ] Add config fields in `config.py`
- [ ] Add env override for `SEMANTIC_SCHOLAR_API_KEY`
- [ ] Update `config.yaml` defaults/comments
- [ ] Create `semantic_scholar_seeds.json`
- [x] Implement `SemanticScholarSource.fetch()` in `sources/paper_sources.py`
- [x] Wire S2 source into `main.py::fetch_papers`
- [ ] Verify dedup behavior with mixed arXiv/S2 results
- [ ] Add short README section for seed file format + setup
- [x] Local dry-run validation
- [ ] GitHub Actions dry-run validation
- [ ] Real send validation

## Implementation Log

### 2026-02-17 - Step 1-3 Completed

Completed items:

- [x] Add config fields in `config.py`
- [x] Add env override for `SEMANTIC_SCHOLAR_API_KEY`
- [x] Update `config.yaml` defaults/comments
- [x] Create `semantic_scholar_seeds.json`

File-level changes:

- `config.py`
  - Added new config fields:
    - `semantic_scholar_enabled`
    - `semantic_scholar_api_key`
    - `semantic_scholar_max_results`
    - `semantic_scholar_seeds_path`
  - Added env overrides:
    - `SEMANTIC_SCHOLAR_ENABLED`
    - `SEMANTIC_SCHOLAR_API_KEY`
    - `SEMANTIC_SCHOLAR_MAX_RESULTS`
    - `SEMANTIC_SCHOLAR_SEEDS_PATH`
  - Added bool/int parsing for Semantic Scholar env values
  - Added Semantic Scholar fields to `to_yaml()` (excluding API key)

- `config.yaml`
  - Added Semantic Scholar section:
    - `semantic_scholar_enabled: false`
    - `semantic_scholar_max_results: 50`
    - `semantic_scholar_seeds_path: "semantic_scholar_seeds.json"`

- `semantic_scholar_seeds.json`
  - Added initial seed template:
    - `positive_paper_ids`
    - `negative_paper_ids`

### 2026-02-17 - Step 4 Completed

Completed item:

- [x] Implement `SemanticScholarSource.fetch()` in `sources/paper_sources.py`

File-level changes:

- `sources/paper_sources.py`
  - Implemented `SemanticScholarSource` with:
    - optional API key support (authenticated or unauthenticated mode)
    - seed loading from `semantic_scholar_seeds.json`
    - recommendations endpoint call:
      - `POST /recommendations/v1/papers/`
    - request params:
      - `limit`
      - `fields=paperId,title,abstract,authors,year,venue,url,externalIds`
    - retry/backoff handling for timeout/429
    - graceful fallback for auth/server/network failures
    - conversion to `Paper` model with `PaperSource.SEMANTIC_SCHOLAR`
    - arXiv ID extraction from `externalIds.ArXiv` for dedup/PDF reuse

### 2026-02-17 - Step 5 Completed

Completed item:

- [x] Wire S2 source into `main.py::fetch_papers`

File-level changes:

- `main.py`
  - Added `SemanticScholarSource` import
  - Integrated S2 fetch block in `fetch_papers(...)`:
    - gated by `semantic_scholar_enabled`
    - uses config fields (`api_key`, `seeds_path`, `max_results`)
    - appends results into existing `papers` list before dedup

### 2026-02-17 - Validation Run (Local Dry-Run)

Completed item:

- [x] Local dry-run validation

Observed behavior:

- Pipeline completed successfully end-to-end (`python main.py --dry-run`)
- Semantic Scholar source block executed
- S2 returned zero papers due empty seeds:
  - log: `Semantic Scholar: no positive seed IDs found, skipping`
- This confirms wiring is active and gracefully degrades when seeds are not populated

### 2026-02-17 - Seed Normalization and Mixed-Source Validation

Completed item:

- [x] Verify dedup behavior with mixed arXiv/S2 results

File-level changes:

- `sources/paper_sources.py`
  - Added `_normalize_seed_ids(...)`:
    - numeric-like IDs are converted to `CorpusId:<id>`
    - prefixed IDs are passed through
  - `fetch(...)` now normalizes positive/negative seed IDs before API call

Validation evidence:

- Dry-run with `SEMANTIC_SCHOLAR_ENABLED=true` and populated seeds:
  - `🧠 Fetching from Semantic Scholar recommendations...`
  - `Found 50 papers`
  - `✅ Total unique papers: 100`
- Confirms S2 source is active and merged into the same deduplicated pool.

## Recommendation Control Guide (How to steer S2 output)

The recommendation behavior is controlled by five levers:

1. Seed positives (`semantic_scholar_seeds.json` -> `positive_paper_ids`)
   - Strongest signal for "more like this"
2. Seed negatives (`semantic_scholar_seeds.json` -> `negative_paper_ids`)
   - Explicit signal for "less like this"
3. Source volume (`semantic_scholar_max_results`)
   - Number of S2 candidates injected before filtering
4. Hard topical gates (`keywords` / `exclude_keywords` in `config.yaml`)
   - Controls which candidates survive recall stage
5. LLM preference (`research_interests` in `config.yaml`)
   - Controls coarse/fine ranking among surviving candidates

Practical tuning workflow:

- Keep 10-30 positive seeds for core interests
- Keep 3-10 negative seeds for unwanted topics
- Refresh seeds weekly (add strong new papers, remove stale/noisy ones)
- If too broad: lower `semantic_scholar_max_results` and tighten `exclude_keywords`
- If too narrow: add more diverse positives and raise `semantic_scholar_max_results`

### 2026-02-18 - Stability Debug and Runtime Fixes

Observed issues from direct runs:

- arXiv intermittently returned `Found 0` despite fresh entries existing
- Blog fetches timed out reproducibly in China network environment
- Fine filter used filter model instead of main model
- S2-introduced papers without `pdf_url` could crash PDF processing

Fixes applied:

- `main.py`
  - Fine filter now uses main model settings:
    - `llm_api_key`, `llm_base_url`, `llm_model`
  - Coarse filter remains on `llm_filter_*` settings

- `sources/paper_sources.py`
  - Enabled proxy-aware HTTP in aiohttp sessions (`trust_env=True`)
  - Fixed arXiv date filtering with UTC-consistent comparison

- `sources/blog_sources.py`
  - Enabled proxy-aware HTTP in aiohttp sessions (`trust_env=True`)
  - Added browser-like headers for feed fetches
  - Added retry for timeout/5xx responses

- `summarizer.py`
  - Added null-safe handling for missing `pdf_url` (fallback to abstract-only)

- `llm_client.py`
  - Hardened error logging when URL is `None`

Validation outcome:

- Dry-run now completes end-to-end after fixes
- arXiv no longer always drops to zero (fresh counts observed)
- Blog fetch stability improved; remaining failures are deterministic endpoint issues (e.g., Anthropic 404, Meta HTTP 400)
