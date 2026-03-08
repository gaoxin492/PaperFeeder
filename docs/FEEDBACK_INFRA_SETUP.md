# Feedback Infra Setup (Cloudflare + D1)

Use this only if you want to set up or maintain the web feedback infrastructure.
For normal daily operation, follow README and run GitHub Actions.

## 1. Required secrets

Set in GitHub Actions Secrets:

- `FEEDBACK_ENDPOINT_BASE_URL`
- `FEEDBACK_LINK_SIGNING_SECRET`
- `CLOUDFLARE_ACCOUNT_ID`
- `CLOUDFLARE_API_TOKEN`
- `D1_DATABASE_ID`

Optional:
- `FEEDBACK_TOKEN_TTL_DAYS` (default `7`)
- `FEEDBACK_REVIEWER`

## 2. Worker and D1

Worker code template:
- `cloudflare/feedback_worker.js`

Schema file:
- `cloudflare/d1_feedback_events.sql`

Minimum required tables:
- `feedback_events` (queue events)
- `feedback_runs` (stored web-viewer report HTML)

Core schema:

```sql
CREATE TABLE IF NOT EXISTS feedback_events (
  event_id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL,
  item_id TEXT NOT NULL,
  label TEXT NOT NULL,
  reviewer TEXT,
  created_at TEXT NOT NULL,
  source TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',
  resolved_semantic_paper_id TEXT,
  applied_at TEXT,
  error TEXT
);

CREATE INDEX IF NOT EXISTS idx_feedback_events_status ON feedback_events(status);
CREATE INDEX IF NOT EXISTS idx_feedback_events_run_item ON feedback_events(run_id, item_id);

CREATE TABLE IF NOT EXISTS feedback_runs (
  run_id TEXT PRIMARY KEY,
  created_at TEXT NOT NULL,
  report_html TEXT NOT NULL
);
```

## 2.1 Cloudflare setup by hand (Dashboard)

1. Create D1 database
- Cloudflare Dashboard -> Workers & Pages -> D1 -> Create database.
- Copy the database ID for `D1_DATABASE_ID`.

2. Create/choose Worker
- Workers & Pages -> Create Worker (or open existing worker).
- Paste/update worker code from `cloudflare/feedback_worker.js`.

3. Bind D1 to Worker
- Worker -> Settings -> Bindings -> Add binding -> D1 database.
- Binding name must be `DB` (matches code).

4. Add Worker secret
- Worker -> Settings -> Variables and Secrets -> Add secret:
  - `FEEDBACK_LINK_SIGNING_SECRET` (must match GitHub secret).

5. Deploy Worker
- Click Deploy.
- Verify endpoint:
  - `https://<worker-subdomain>.workers.dev/run?run_id=<known-run-id>`

6. Run D1 schema SQL
- D1 -> your database -> Console/Query.
- Run SQL from `cloudflare/d1_feedback_events.sql`.
- Verify tables exist: `feedback_events`, `feedback_runs`.

## 3. Runtime flow

1. Digest run writes run report HTML to `feedback_runs`.
2. Email includes one run-level URL: `/run?run_id=<id>`.
3. User clicks `positive` / `negative` / `undecided` in viewer.
4. Worker inserts `pending` row to `feedback_events`.
5. `Apply Feedback Queue` action resolves pending events into `semantic_scholar_seeds.json`.

## 4. Validation SQL

Check recent feedback events:

```sql
SELECT event_id, run_id, item_id, label, status, resolved_semantic_paper_id, created_at
FROM feedback_events
ORDER BY created_at DESC
LIMIT 20;
```

Check status distribution:

```sql
SELECT status, COUNT(*) AS cnt
FROM feedback_events
GROUP BY status;
```

Check run report exists:

```sql
SELECT run_id, created_at
FROM feedback_runs
ORDER BY created_at DESC
LIMIT 10;
```

## 5. Notes

- Local script `scripts/apply_semantic_feedback_queue.sh` is optional and mainly for local/debug usage.
- Recommended production path is GitHub Actions:
  - `Daily Paper Digest`
  - `Apply Feedback Queue`
