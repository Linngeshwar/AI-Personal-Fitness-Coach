-- Foundation-pass schema. Run once: psql $DATABASE_URL -f schema.sql
-- No migration tooling -- per spec, three CREATE TABLE blocks is enough for now.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ---------------------------------------------------------------------------
-- users
--
-- Non-sensitive profile fields are plain columns (needed for planner queries
-- and screening re-checks). weight_kg, injuries, and the SafetyFlags block
-- are sensitive -- they're AES-GCM encrypted app-side (backend/privacy/crypto.py)
-- before this INSERT, stored as opaque bytes, decrypted after SELECT.
-- ---------------------------------------------------------------------------
CREATE TABLE users (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  goal              TEXT NOT NULL,
  experience        TEXT NOT NULL,
  days_per_week     INT NOT NULL,
  session_minutes   INT NOT NULL,
  equipment         TEXT[] NOT NULL,
  height_cm         NUMERIC NOT NULL,
  age               INT NOT NULL,
  sex               TEXT NOT NULL,
  activity_level    NUMERIC NOT NULL,
  nutrition_enabled BOOLEAN NOT NULL DEFAULT TRUE,
  requires_clearance BOOLEAN NOT NULL DEFAULT FALSE,
  health_encrypted  BYTEA NOT NULL  -- encrypted JSON: {weight_kg, injuries, safety}
);

-- ---------------------------------------------------------------------------
-- exercises -- single source of truth, seeded once, read-only at runtime.
-- ---------------------------------------------------------------------------
CREATE TABLE exercises (
  id                  TEXT PRIMARY KEY,
  name                TEXT NOT NULL,
  primary_muscle      TEXT NOT NULL,
  secondary_muscles    TEXT[] DEFAULT '{}',
  equipment           TEXT NOT NULL,
  level               TEXT NOT NULL,
  mechanic            TEXT,
  force               TEXT,
  category            TEXT,
  image_paths         TEXT[],
  contraindications   TEXT[] DEFAULT '{}',
  is_compound         BOOLEAN,
  est_seconds_per_set INT DEFAULT 45,
  unilateral          BOOLEAN DEFAULT FALSE
);
CREATE INDEX ON exercises (primary_muscle, equipment, level);

-- ---------------------------------------------------------------------------
-- consents -- one row per purpose per grant/revoke event.
-- ---------------------------------------------------------------------------
CREATE TABLE consents (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  purpose     TEXT NOT NULL,   -- plan_generation | llm_processing | nutrition
  granted_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  revoked_at  TIMESTAMPTZ
);

-- ---------------------------------------------------------------------------
-- plans -- the serialized Plan (schemas/plan.py) stored whole as JSONB.
-- No separate day/block tables: the Plan model is the contract everywhere
-- else, so it's also the storage shape. "Current plan" = most recent row.
-- ---------------------------------------------------------------------------
CREATE TABLE plans (
  id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id            UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  week_start         DATE NOT NULL,
  generated_by       TEXT NOT NULL,
  volume_multiplier  NUMERIC NOT NULL,
  plan_json          JSONB NOT NULL,
  created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ON plans (user_id, created_at DESC);
