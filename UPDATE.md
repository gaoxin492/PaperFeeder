# Updates Log

## 2026-02-28

### 1) Cross-Source Feedback Actionability (ArXiv/HF -> Semantic ID) Added

- Feedback manifest export now performs best-effort Semantic Scholar ID resolution for report-visible ArXiv and HuggingFace papers that lack `semantic_paper_id`.
- Resolution order is deterministic: existing semantic ID -> arXiv ID mapping -> conservative title-match fallback.
- This increases one-click feedback coverage for cross-source papers without changing apply semantics.

### 2) Manifest Resolution Transparency Added

- Per-paper metadata now records resolution outcome:
  - `arxiv_id`
  - `resolution_status`
  - `resolution_method`
  - `feedback_enabled`
  - optional `resolution_error`
- Manifest also includes run-level resolver stats/warnings for audit/debug.

### 3) Run-Scoped Resolver Budget + Fail-Open Behavior

- Resolver uses run-scoped in-memory cache only (no persisted resolver cache file).
- Best-effort lookup is bounded by configurable attempt/time budgets (including no-key mode safeguards).
- On throttling/errors/budget exhaustion, remaining papers are emitted unresolved/non-actionable; digest generation continues.

### 4) Feedback Apply Flow Unchanged

- Link generation/actionability is now broader, but seed updates still happen only through apply (`Apply Feedback Queue` / apply script).
- Daily operation remains: run digest -> give feedback -> run apply.

## 2026-02-22

### 1) Feedback Flow Moved to Web Report Viewer (Email = Notification Only)

- Digest email now stays content-focused and includes a single run-level web viewer entry link.
- Feedback actions are completed in the web viewer context (not inside email client body).
- Web viewer uses the original report HTML and keeps per-paper feedback controls (`positive` / `negative`).

### 2) Cloudflare D1 Apply Bridge Completed

- Manual apply path now supports reading pending feedback events directly from D1 (`--from-d1`), defaulting to all pending events.
- Apply writes terminal statuses (`applied` / `rejected`) back to D1 with metadata.
- Preserved backward-compatible local queue mode (`--from-queue`) for local debugging.

### 3) Seed + Memory State Persistence on Dedicated State Branch

- Workflows now load/persist mutable state (`semantic_scholar_seeds.json`, `semantic_scholar_memory.json`) from a dedicated state branch (`memory-state` by default).
- This avoids frequent `main` branch conflicts from bot-updated state files.
- Added `SEED_STATE_BRANCH` repo variable support for branch override.

### 4) Feedback Reliability and UX Improvements

- Feedback tokens now include `semantic_paper_id`, and worker writes `resolved_semantic_paper_id` directly to D1 queue rows.
- Removed `undecided` from one-click web feedback actions for V1 operation.
- Added inline click UX in web viewer (small success/fail animation/toast, no page redirect per click).

### 5) Email Attachments Simplified

- Removed manifest/template JSON attachments from digest emails.
- Artifacts are still generated/uploaded for workflow/debug use when needed.

### 6) Documentation Refresh

- README cleaned up to reflect only current production flow (seed + memory + web feedback + manual apply).
- Added dedicated docs:
  - `docs/PERSONALIZATION_AND_MEMORY.md`
  - `docs/FEEDBACK_INFRA_SETUP.md`
- Moved Cloudflare/D1 low-level setup details out of README into focused infra documentation.

## 2026-02-21

### 1) Semantic Memory Persistence Moved to Dedicated Branch

- GitHub Actions now reads/writes `semantic_scholar_memory.json` from/to a dedicated `memory-state` branch.
- This isolates high-frequency memory state churn from `main` and reduces push/rebase friction for code changes.
- If `memory-state` or the memory file does not exist, workflow initializes an empty memory state safely.

### 2) Report-Visible Memory Marking Fix

- Semantic seen-memory updates now mark only Semantic Scholar papers that are actually visible in final rendered report links.
- This avoids false positives where a paper was selected internally but did not appear in final HTML sections.

### 3) Fine Filter Model Wiring + Parse Debugging

- Fine filtering path is explicitly wired to main `llm_*` model settings (while coarse filtering remains on `llm_filter_*`).
- Added detailed debug logging for `LLM filter: Could not parse response` cases:
  - full prompt
  - raw model response
  - model/base URL/stage metadata
  - saved under `llm_filter_debug/`

### 4) Documentation Sync (README Operational Notes)

- Added operational notes covering:
  - fetch/report dedup rules and current limitations
  - semantic memory TTL/cap behavior
  - `days_back` usage in GitHub Actions manual runs
  - daily git workflow with auto-updating memory branch
  - troubleshooting for parse failures and report count mismatches
- Clarified fine filter output target as Top `1-5`.
- Clarified OpenSpec artifacts are local workflow files (gitignored by default in this repo).

## 2026-02-18

### 1) Semantic Scholar Source Integrated

- Added seed-based Semantic Scholar recommendations as a first-class paper source.
- Added config controls:
  - `semantic_scholar_enabled`
  - `semantic_scholar_max_results`
  - `semantic_scholar_seeds_path`
  - optional `SEMANTIC_SCHOLAR_API_KEY`
- Added local seed file:
  - `semantic_scholar_seeds.json`
  - keys: `positive_paper_ids`, `negative_paper_ids`
- Added ID normalization so numeric corpus IDs are automatically converted to `CorpusId:<id>`.
- Semantic Scholar candidates are merged into the existing paper pool before dedup/filtering.

### 2) Local Timeout / China Network Stability Improvements

- Enabled proxy-aware network requests (`aiohttp` with `trust_env=True`) in paper/blog/semantic source fetchers.
- Added stronger blog fetch robustness:
  - browser-like headers
  - retry on timeout/5xx
- Result:
  - fewer random blog timeouts in China environment
  - remaining failures are mostly deterministic endpoint issues (for example, Anthropic 404).

### 3) Coarse vs Fine Filter Model Wiring Fixed

- Coarse filter still uses `llm_filter_*` (cheap model path).
- Fine filter now uses main model settings `llm_*` as intended.
- This aligns final ranking with your preferred higher-quality model.

### 4) Additional Runtime Hardening

- Fixed arXiv recent-paper date filtering to use UTC-consistent comparison.
- Added null-safe handling for papers without `pdf_url` to avoid summarize-stage crash.
- Hardened PDF download error logging for missing URL cases.
