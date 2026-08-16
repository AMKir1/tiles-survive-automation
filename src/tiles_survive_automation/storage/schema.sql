CREATE TABLE IF NOT EXISTS Rule (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  description TEXT,
  window_title_hint TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS RuleStep (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  rule_id INTEGER NOT NULL REFERENCES Rule(id) ON DELETE CASCADE,
  order_index INTEGER NOT NULL,
  step_type TEXT NOT NULL,
  name TEXT NOT NULL,
  enabled INTEGER NOT NULL DEFAULT 1,
  params_json TEXT NOT NULL,
  template_path TEXT,
  confidence_threshold REAL NOT NULL DEFAULT 0.85,
  strategy TEXT NOT NULL DEFAULT 'VISUAL_THEN_RELATIVE',
  verification_json TEXT,
  screenshot_path TEXT,
  delay_after_ms INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS Execution (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  target_type TEXT NOT NULL,
  target_id INTEGER NOT NULL,
  status TEXT NOT NULL,
  error_message TEXT
);

CREATE TABLE IF NOT EXISTS ExecutionStep (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  execution_id INTEGER NOT NULL REFERENCES Execution(id) ON DELETE CASCADE,
  rule_id INTEGER NOT NULL,
  rule_step_id INTEGER NOT NULL,
  timestamp TEXT NOT NULL,
  description TEXT NOT NULL,
  matched_template TEXT,
  confidence REAL,
  x INTEGER,
  y INTEGER,
  result TEXT NOT NULL,
  error_message TEXT
);
