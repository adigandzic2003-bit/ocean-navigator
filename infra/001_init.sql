-- infr/001_init.sql
CREATE TABLE IF NOT EXISTS sources (
  id SERIAL PRIMARY KEY,
  url TEXT UNIQUE,
  source_type TEXT,             -- html|pdf
  company TEXT,
  first_seen TIMESTAMP DEFAULT NOW(),
  last_seen TIMESTAMP DEFAULT NOW(),
  hash TEXT
);

CREATE TABLE IF NOT EXISTS documents (
  id SERIAL PRIMARY KEY,
  source_id INTEGER REFERENCES sources(id),
  fetched_at TIMESTAMP DEFAULT NOW(),
  mime TEXT,
  lang TEXT,
  text TEXT,
  meta_json JSONB
);

CREATE TABLE IF NOT EXISTS extractions (
  id SERIAL PRIMARY KEY,
  document_id INTEGER REFERENCES documents(id),
  kpi_id TEXT,
  value NUMERIC,
  unit TEXT,
  method TEXT,
  confidence NUMERIC,
  snippet TEXT,
  page_no INTEGER,
  converted BOOLEAN DEFAULT FALSE,
  taxonomy_path TEXT,
  created_at TIMESTAMP DEFAULT NOW()
);
