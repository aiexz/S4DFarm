CREATE TABLE IF NOT EXISTS flags (
    flag TEXT PRIMARY KEY,
    sploit TEXT,
    team TEXT,
    time INTEGER,
    status TEXT,
    checksystem_response TEXT
);

CREATE INDEX IF NOT EXISTS idx_flags_sploit ON flags(sploit);
CREATE INDEX IF NOT EXISTS idx_flags_team ON flags(team);
CREATE INDEX IF NOT EXISTS idx_flags_status_time ON flags(status, time);
CREATE INDEX IF NOT EXISTS idx_flags_time ON flags(time);

CREATE TABLE IF NOT EXISTS executions (
    id SERIAL PRIMARY KEY,
    client_id TEXT,
    sploit_id TEXT,
    sploit_hash TEXT,
    service TEXT,
    team TEXT,
    round INTEGER,
    start_time DOUBLE PRECISION,
    end_time DOUBLE PRECISION,
    duration REAL,
    exit_code INTEGER,
    timeout BOOLEAN,
    flags_found INTEGER,
    output_preview TEXT
);

CREATE INDEX IF NOT EXISTS idx_executions_sploit ON executions(sploit_id);
CREATE INDEX IF NOT EXISTS idx_executions_team ON executions(team);
CREATE INDEX IF NOT EXISTS idx_executions_service ON executions(service);
CREATE INDEX IF NOT EXISTS idx_executions_round ON executions(round);
CREATE INDEX IF NOT EXISTS idx_executions_start_time ON executions(start_time);
