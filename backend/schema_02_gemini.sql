-- Additive to schema.sql (already applied, catalog already seeded -- this
-- file only adds what Layer 4 needs). Run once:
--   psql $DATABASE_URL -f schema_02_gemini.sql

-- ---------------------------------------------------------------------------
-- rejected_plans -- every plan the validator couldn't repair, and why.
-- Feeds GET /api/debug/validations, the judge-facing "the model never gets
-- the last word" screen.
-- ---------------------------------------------------------------------------
CREATE TABLE rejected_plans (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  plan_json   JSONB NOT NULL,
  violations  JSONB NOT NULL,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ON rejected_plans (created_at DESC);
