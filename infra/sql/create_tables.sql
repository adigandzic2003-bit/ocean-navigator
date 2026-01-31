-- 1) Basis: Schema optional
CREATE SCHEMA IF NOT EXISTS oin;

-- 2) Haupttabelle
CREATE TABLE IF NOT EXISTS oin.oin_master (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),

  -- Typisierung & Kontext
  record_type         TEXT NOT NULL CHECK (record_type IN ('doc','kpi')),
  tenant              TEXT DEFAULT 'default',
  company             TEXT,

  -- Provenienz
  source_type         TEXT NOT NULL CHECK (source_type IN ('web','pdf','api','gdelt','crossref','analysis','other')),
  source_id           TEXT NOT NULL,
  crawler_name        TEXT,
  language            TEXT,
  published_at        TIMESTAMP WITH TIME ZONE,
  collected_at        TIMESTAMP WITH TIME ZONE DEFAULT now(),

  -- Pipeline & Qualität
  status              TEXT NOT NULL DEFAULT 'new' CHECK (status IN ('new','parsed','analyzed','enriched','ready','error')),
  processing_stage    TEXT,
  error_msg           TEXT,
  priority            INT,
  version             INT NOT NULL DEFAULT 1,
  last_seen_at        TIMESTAMP WITH TIME ZONE,
  created_at          TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
  updated_at          TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
  review_required     BOOLEAN DEFAULT false,
  review_notes        TEXT,
  topic_tags          TEXT,
  geo_scope           TEXT,
  embedding           TEXT,
  keywords            TEXT,
  relevance_score     DOUBLE PRECISION,
  meta                JSONB DEFAULT '{}'::jsonb,
  doc_key             TEXT,

  -- DOC-Felder
  title               TEXT,
  raw_text            TEXT,
  content_type        TEXT CHECK (content_type IS NULL OR content_type IN ('article','report','press_release','study','law','blog','other')),
  content_hash        TEXT,
  lang_confidence     DOUBLE PRECISION,

  -- KPI-Felder
  kpi_key             TEXT,
  kpi_value           DOUBLE PRECISION,
  kpi_unit            TEXT,
  kpi_method          TEXT,
  confidence          DOUBLE PRECISION,
  kpi_context         TEXT,
  kpi_scope           TEXT CHECK (kpi_scope IS NULL OR kpi_scope IN ('site','company','product','region','global')),
  kpi_period_start    DATE,
  kpi_period_end      DATE,
  extracted_from_url  TEXT,
  doc_ref_id          UUID
);

-- 3) Partielle Eindeutigkeiten (Idempotenz)
-- DOC: (record_type, source_type, source_id) eindeutig
CREATE UNIQUE INDEX IF NOT EXISTS oin_uniq_doc_source
  ON oin.oin_master(source_type, source_id)
  WHERE record_type = 'doc';

-- Optional alternativ: (record_type, doc_key), falls source_id instabil
CREATE UNIQUE INDEX IF NOT EXISTS oin_uniq_doc_key
  ON oin.oin_master(record_type, doc_key)
  WHERE record_type = 'doc' AND doc_key IS NOT NULL;

-- KPI: (record_type, company, kpi_key, source_id[, periode]) eindeutig
CREATE UNIQUE INDEX IF NOT EXISTS oin_uniq_kpi_main
  ON oin.oin_master(company, kpi_key, source_id, kpi_period_start, kpi_period_end)
  WHERE record_type = 'kpi';

-- 4) Nützliche Sekundärindizes
CREATE INDEX IF NOT EXISTS oin_idx_company ON oin.oin_master(company);
CREATE INDEX IF NOT EXISTS oin_idx_record_type ON oin.oin_master(record_type);
CREATE INDEX IF NOT EXISTS oin_idx_published_at ON oin.oin_master(published_at);
CREATE INDEX IF NOT EXISTS oin_idx_content_hash ON oin.oin_master(content_hash);
CREATE INDEX IF NOT EXISTS oin_idx_kpi_key ON oin.oin_master(kpi_key);

-- 5) updated_at automatisch pflegen (ohne App-Logik)
CREATE OR REPLACE FUNCTION oin.t_set_updated_at() RETURNS trigger AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_set_updated_at ON oin.oin_master;
CREATE TRIGGER trg_set_updated_at
BEFORE UPDATE ON oin.oin_master
FOR EACH ROW EXECUTE FUNCTION oin.t_set_updated_at();
