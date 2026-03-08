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
