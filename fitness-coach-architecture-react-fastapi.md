# AI Personal Fitness Coach — Architecture Spec (React + FastAPI)

**Stack:** Vite + React (SPA) · FastAPI (Python) · PostgreSQL via raw `asyncpg` · Gemini API
**Positioning:** the coach that survives you missing a day
**Build window:** ~48 hours

---

## The governing principle

Gemini is a **transformer of valid plans, not an originator of plans**.

Every plan is born deterministic, gets personalised by Gemini within a constrained vocabulary, and must then pass a validator before a human ever sees it. If Gemini is slow, rate-limited, returns malformed JSON, or the venue wifi dies, the deterministic plan ships instead and the app still works.

Three consequences follow, and they're the reason this beats "prompt Gemini for a plan":

1. **You can never fully lose the demo.** Layer 2 alone is a working product.
2. **Every exercise ID is guaranteed to exist** in your catalog, so images always render.
3. **You have something to say to judges** that isn't "we called an LLM."

### Why raw asyncpg changes the plan, not the architecture

No ORM means no models auto-generating queries for you — every query is SQL you write and every row you map to a Pydantic model by hand. That's more typing on Day 1 but it removes an entire class of hackathon failure (ORM session/async footguns, lazy-load surprises, migration drift). Given the timebox: **hand-roll a tiny query layer once, reuse it everywhere.**

```python
# db.py
import asyncpg
from contextlib import asynccontextmanager

pool: asyncpg.Pool | None = None

async def init_pool():
    global pool
    pool = await asyncpg.create_pool(dsn=DATABASE_URL, min_size=2, max_size=10)

@asynccontextmanager
async def get_conn():
    async with pool.acquire() as conn:
        yield conn
```

Every route below assumes `async with get_conn() as conn: ...`. No separate repository classes — at this scale it's ceremony you don't have time for. One `queries.py` per domain (exercises, foods, plans, sessions) with plain `async def` functions returning Pydantic models is enough structure.

---

# Layer 0 — Intake

**Job:** turn a person into a `UserProfile` and a `SafetyFlags` object. Nothing else.

### Pydantic models (FastAPI's real strength here — reuse these everywhere: request validation, DB row mapping, Gemini schema)

```python
# schemas/profile.py
from pydantic import BaseModel, Field
from typing import Literal
from enum import Enum

class Goal(str, Enum):
    fat_loss = "fat_loss"
    muscle_gain = "muscle_gain"
    strength = "strength"
    endurance = "endurance"
    general = "general"

class Experience(str, Enum):
    beginner = "beginner"
    intermediate = "intermediate"
    advanced = "advanced"

class Equipment(str, Enum):
    none = "none"
    dumbbells = "dumbbells"
    barbell = "barbell"
    machines = "machines"
    bands = "bands"
    pullup_bar = "pullup_bar"
    full_gym = "full_gym"

class Injury(str, Enum):
    knee = "knee"
    lower_back = "lower_back"
    shoulder = "shoulder"
    wrist = "wrist"
    ankle = "ankle"

class SafetyFlags(BaseModel):
    under_18: bool = False
    pregnant_or_postpartum: bool = False
    cardiac_or_bp_condition: bool = False
    diabetes: bool = False
    eating_disorder_history: bool = False
    chest_pain_on_exertion: bool = False

class UserProfile(BaseModel):
    goal: Goal
    experience: Experience
    days_per_week: int = Field(ge=2, le=6)
    session_minutes: Literal[20, 30, 45, 60]
    equipment: list[Equipment]
    injuries: list[Injury] = []
    height_cm: float
    weight_kg: float
    age: int
    sex: Literal["male", "female", "other"]
    activity_level: float = Field(ge=1.2, le=1.9)
    safety: SafetyFlags
```

FastAPI validates the request body against this automatically — malformed onboarding data 422s before it ever reaches your logic. That's the ORM-less stack's main gift: Pydantic does the job an ORM's model layer would have done anyway.

### Screening gate (blocking, before anything generates)

```python
def apply_screening(profile: UserProfile) -> ScreeningResult:
    s = profile.safety
    if s.under_18 or s.pregnant_or_postpartum or s.eating_disorder_history:
        return ScreeningResult(nutrition_enabled=False,
            message="We won't set calorie targets for you. Talk to a doctor or dietitian.",
            volume_cap=0.7)
    if s.chest_pain_on_exertion or s.cardiac_or_bp_condition:
        return ScreeningResult(requires_clearance=True)
    return ScreeningResult()
```

Not a modal. A visible card on the plan screen, every time. A judge *will* ask "what if a 15-year-old with an eating disorder uses this" — the honest, implemented refusal is worth more than any feature that hour could otherwise buy.

### Privacy layer (your differentiator as a security student)

- **Data minimisation:** the Gemini prompt receives an anonymised attribute bundle — `age_band: "18-24"`, never `dob`; no name, no email.
- **Encryption at rest:** health fields (`weight_kg`, `injuries`, `SafetyFlags`) encrypted app-side with `cryptography`'s `AESGCM` before the raw SQL `INSERT`, decrypted after `SELECT`. Small helper module, not a library dependency.
- **Consent record:** `consents(user_id, purpose, granted_at, revoked_at)` — separate rows for `plan_generation`, `llm_processing`, `nutrition`.
- **Hard delete:** `DELETE /api/me` — cascades via FK `ON DELETE CASCADE`, one query. 20 minutes of work, no other team will have it.
- **One slide:** a data-flow diagram marking what leaves the device, what's encrypted, what's never sent to Google.

---

# Layer 1 — Knowledge base

**Job:** be the single source of truth for every noun and every number. Loaded once at seed time via a plain `asyncpg` script, read-only at runtime.

### 1.1 Exercise catalog

Vendor [`free-exercise-db`](https://github.com/yuhonas/free-exercise-db) into `/data/exercises.json` — ~870 exercises, MIT licensed, includes images. **Never call it over the network at runtime.**

```sql
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
```

```python
# scripts/seed_exercises.py
import json, asyncio, asyncpg, re

CONTRA_PATTERNS = [
    (r"squat|lunge|leg press|step.?up", "knee"),
    (r"deadlift|good morning|row.*bent", "lower_back"),
    (r"overhead|press.*shoulder|upright row", "shoulder"),
]

async def seed():
    conn = await asyncpg.connect(DATABASE_URL)
    data = json.load(open("data/exercises.json"))
    for ex in data:
        contra = [tag for pat, tag in CONTRA_PATTERNS if re.search(pat, ex["name"], re.I)]
        await conn.execute("""
            INSERT INTO exercises (id, name, primary_muscle, secondary_muscles,
              equipment, level, mechanic, force, category, image_paths,
              contraindications, is_compound)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)
            ON CONFLICT (id) DO NOTHING
        """, ex["id"], ex["name"], ex["primaryMuscles"][0], ex["secondaryMuscles"],
             ex["equipment"], ex["level"], ex.get("mechanic"), ex.get("force"),
             ex["category"], ex["images"], contra, ex.get("mechanic") == "compound")
    await conn.close()

asyncio.run(seed())
```

Pattern-tag everything, then hand-review the top 150 most-used exercises. Two hours; powers your most impressive validator rule.

### 1.2 Food table

**Do not train anything.** A table:

```sql
CREATE TABLE foods (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  name_local TEXT,
  serving_desc TEXT,
  serving_g NUMERIC NOT NULL,
  kcal_100g NUMERIC NOT NULL,
  protein_100g NUMERIC NOT NULL,
  carbs_100g NUMERIC NOT NULL,
  fat_100g NUMERIC NOT NULL,
  fiber_100g NUMERIC,
  tags TEXT[],
  source TEXT
);
```

Seed ~200 rows via `COPY foods FROM 'data/foods.csv' CSV HEADER` — one line, no ORM import machinery needed. **100 Indian staples** (idli, dosa, sambar, rasam, curd rice, upma, pongal, chapati, dal, paneer, filter coffee with sugar, biryani, vada, poori, avial, thayir sadam) from IFCT 2017, plus 100 generic (chicken breast, eggs, oats, rice, whey, banana, peanut butter). Two people, two hours in a spreadsheet, export CSV.

Highest value-per-hour asset in the project. Every nutrition API in the room is Western.

### 1.3 Rule tables (Python constants, not DB — no reason to round-trip SQL for numbers that never change)

```python
# rules/constants.py
VOLUME_LANDMARKS = {
    "beginner":     {"min": 6,  "target": 10, "max": 14},
    "intermediate": {"min": 8,  "target": 14, "max": 20},
    "advanced":     {"min": 10, "target": 18, "max": 24},
}

REP_SCHEME = {
    "strength":    {"reps": (3, 6),   "rest": 180, "rir": 2},
    "muscle_gain": {"reps": (8, 12),  "rest": 90,  "rir": 1},
    "fat_loss":    {"reps": (10, 15), "rest": 60,  "rir": 2},
    "endurance":   {"reps": (15, 25), "rest": 45,  "rir": 3},
    "general":     {"reps": (8, 15),  "rest": 75,  "rir": 2},
}

SPLITS = {
    2: [["full_body"], ["full_body"]],
    3: [["push"], ["pull"], ["legs"]],
    4: [["upper"], ["lower"], ["upper"], ["lower"]],
    5: [["push"], ["pull"], ["legs"], ["upper"], ["lower"]],
    6: [["push"], ["pull"], ["legs"], ["push"], ["pull"], ["legs"]],
}
```

---

# Layer 2 — Planner core (deterministic)

**Job:** `(UserProfile, PlanState) -> Plan`. Pure function. No network, no LLM, no DB writes — only reads. Same input, same output.

### The `Plan` contract — write this before any other code

```python
# schemas/plan.py
from pydantic import BaseModel
from typing import Literal
from datetime import date

class PlanBlock(BaseModel):
    exercise_id: str          # MUST exist in exercises table
    order: int
    sets: int
    rep_low: int
    rep_high: int
    rest_seconds: int
    rir: int
    note: str | None = None          # Gemini may write this
    swap_reason: str | None = None   # Gemini may write this

class PlanDay(BaseModel):
    date: date
    type: Literal["workout", "rest", "active_recovery"]
    focus: str | None
    est_minutes: int
    blocks: list[PlanBlock]

class Plan(BaseModel):
    plan_id: str
    user_id: str
    week_start: date
    generated_by: Literal["deterministic", "gemini_refined"]
    volume_multiplier: float
    days: list[PlanDay]
```

This model is shared verbatim between the planner, the validator, the Gemini response schema, and the API response — write it once in `schemas/plan.py`, import everywhere. It's the artifact that ends every "RAG vs Gemini" argument on your team, because both sides become implementation details behind this interface.

### The algorithm, step by step

**Step 1 — Select split.** `SPLITS[days_per_week]`, distributed with rest days maximally spaced (3 days → Mon/Wed/Fri, not Mon/Tue/Wed).

**Step 2 — Allocate volume.** Per muscle group: weekly target sets = `VOLUME_LANDMARKS[experience]["target"] × PlanState.volume_multiplier`, distributed across sessions training that group.

**Step 3 — Filter the pool.** One `asyncpg` query, array-overlap operator does your injury safety check in one line:

```python
async def get_candidate_exercises(conn, muscle: str, equipment: list[str],
                                   levels: list[str], injuries: list[str]):
    return await conn.fetch("""
        SELECT * FROM exercises
        WHERE primary_muscle = $1
          AND equipment = ANY($2)
          AND level = ANY($3)
          AND NOT (contraindications && $4)
    """, muscle, equipment, levels, injuries)
```

**Step 4 — Select exercises.** Compounds first (`is_compound`), then isolation. Deterministic seeded shuffle (`random.Random(hash(user_id + week_number))`) — reproducible, not identical every week. Cap 4–6 per session.

**Step 5 — Assign sets/reps/rest.** From `REP_SCHEME[goal]`. Load expressed as **RIR**, never kg — you don't know their 1RM and guessing is how you injure someone. `"3 × 8–12 @ RIR 1–2"`.

**Step 6 — Fit to the time budget.** The step teams forget, the one users feel:

```python
def estimate_minutes(blocks: list[PlanBlock], exercises: dict) -> int:
    total = 300  # warmup
    for b in blocks:
        per_set = exercises[b.exercise_id].est_seconds_per_set
        total += b.sets * per_set + (b.sets - 1) * b.rest_seconds
    return total // 60

def fit_to_budget(blocks, exercises, budget_minutes):
    while estimate_minutes(blocks, exercises) > budget_minutes * 1.0:
        isolation = [b for b in blocks if not exercises[b.exercise_id].is_compound]
        if isolation:
            blocks.remove(min(isolation, key=lambda b: b.order))
        elif any(b.rest_seconds > 45 for b in blocks):
            for b in blocks: b.rest_seconds = max(45, b.rest_seconds - 15)
        else:
            for b in blocks: b.sets = max(2, b.sets - 1)
    return blocks
```
Never drop the compound. Sets floor at 2, rest floors at scheme minimum.

**Step 7 — Emit a `Plan`.** Pure Python, returns the Pydantic model directly — FastAPI serialises it for you.

```python
# planner/core.py
def generate_plan(profile: UserProfile, state: PlanState,
                   candidate_pool: dict[str, list[Exercise]]) -> Plan:
    ...  # steps 1-6, pure function, fully unit-testable without a DB or event loop
```

Keep this function DB-free (candidates passed in already-fetched) — makes it trivially unit-testable and reusable inside the validator's repair step.

---

# Layer 3 — Gemini

**Job:** the three narrow things LLMs are actually better at than code. Three separate calls, never one big one.

Model: `gemini-2.5-flash`. Use `response_mime_type="application/json"` + `response_schema` (the Python SDK accepts a Pydantic model directly as the schema — no hand-written JSON schema needed).

```python
# gemini/client.py
import google.generativeai as genai

async def call_gemini(prompt: str, response_model: type[BaseModel],
                       temperature: float, timeout_s: float) -> BaseModel | None:
    try:
        model = genai.GenerativeModel("gemini-2.5-flash")
        resp = await asyncio.wait_for(
            model.generate_content_async(
                prompt,
                generation_config={
                    "temperature": temperature,
                    "response_mime_type": "application/json",
                    "response_schema": response_model,
                },
            ), timeout=timeout_s)
        return response_model.model_validate_json(resp.text)
    except (asyncio.TimeoutError, Exception) as e:
        log.warning(f"gemini call failed: {e}")
        return None   # caller falls back — never raises into the request path
```

`response_model=None` return is the load-bearing line in this file. Every call site checks for `None` and falls back to the deterministic result. Gemini failure is not an exception path, it's an expected branch.

### Call A — Constraint interpreter

Input: free text. *"knee's been hurting, only got 25 mins, I'm in a hotel with just dumbbells"*

```python
class ConstraintDelta(BaseModel):
    session_minutes_override: int | None = None
    equipment_override: list[Equipment] = []
    new_injuries: list[Injury] = []
    energy: Literal["low", "normal", "high"] = "normal"
    intent: Literal["train", "skip", "shorten", "substitute"]
```

Highest-value call in the system, ~30 lines to wire. The delta merges into `UserProfile`, and **Layer 2 re-runs.** Gemini never writes the plan here — it translates human mess into your schema.

### Call B — Plan refiner

Input: the deterministic plan + profile + an explicit whitelist of candidate exercise IDs (≤40, from Step 3's pool).

```
System: You are refining a workout plan. You may ONLY use exercise IDs from
ALLOWED_IDS. You may reorder blocks, swap an exercise for another ALLOWED_ID,
and adjust sets by ±1. You may NOT invent exercises, change the number of
training days, or exceed the stated time budget. For every swap, give a
one-sentence swap_reason.

ALLOWED_IDS: [...]
PLAN: {...}
PROFILE: {...}
```

`temperature=0.3`, `response_model=Plan`. Set `generated_by="gemini_refined"` on success. On `None` → ship the deterministic plan unchanged. This branch is what makes the demo survive dead wifi.

### Call C — Coach voice

```python
class CoachCopy(BaseModel):
    session_brief: str     # "Push day. 32 min. Two compounds, then accessories."
    motivation: str        # references actual behaviour, not generic
    change_note: str       # "You skipped Wednesday twice, so legs moved to Saturday."
```

`temperature=0.9`. Zero safety risk, high perceived polish. `change_note` is the sentence that proves the app noticed — cache 12h, key on `(user_id, plan_id)`.

### Call D — Nutrition advisor (gated)

Input: targets computed in code (never by Gemini) + logged foods + candidate food IDs.

```
Suggest up to 3 swaps from ALLOWED_FOOD_IDS that move the user closer to
their protein target without exceeding their calorie target. Return food IDs
and a one-line reason. Do not state calorie or macro numbers — the app
computes those from the database.
```

**Gemini never emits a number.** Every kcal and gram on screen comes from a `SELECT` or from the code below — non-negotiable, it's the fix for the original trained-macro-model idea.

```python
def compute_targets(profile: UserProfile) -> NutritionTargets:
    bmr = mifflin_st_jeor(profile)
    tdee = bmr * profile.activity_level
    delta = {"fat_loss": -400, "muscle_gain": 300}.get(profile.goal.value, 0)
    target_kcal = max(tdee + delta, bmr)          # hard floor, never below BMR
    protein_g = clamp(1.6 * profile.weight_kg, 0, 2.2 * profile.weight_kg)
    return NutritionTargets(kcal=target_kcal, protein_g=protein_g)
```

---

# Layer 4 — Validator

**Job:** reject anything Gemini returns that breaks the rules, and fall back. Build this properly — it's your most impressive artifact.

```python
# validator/rules.py
class Violation(BaseModel):
    rule: str
    severity: Literal["hard", "soft"]
    detail: str

async def validate(conn, plan: Plan, profile: UserProfile) -> list[Violation]:
    violations = []
    ex_ids = {b.exercise_id for d in plan.days for b in d.blocks}
    rows = await conn.fetch("SELECT id, equipment, contraindications, est_seconds_per_set "
                             "FROM exercises WHERE id = ANY($1)", list(ex_ids))
    ex_map = {r["id"]: r for r in rows}

    for day in plan.days:
        for block in day.blocks:
            ex = ex_map.get(block.exercise_id)
            if ex is None:
                violations.append(Violation(rule="EXERCISE_EXISTS", severity="hard",
                    detail=f"{block.exercise_id} not found")); continue
            if set(ex["contraindications"]) & set(profile.injuries):
                violations.append(Violation(rule="NO_CONTRAINDICATION", severity="hard",
                    detail=f"{block.exercise_id} contraindicated for {profile.injuries}"))
            if ex["equipment"] not in profile.equipment:
                violations.append(Violation(rule="EQUIPMENT_AVAILABLE", severity="hard",
                    detail=f"{block.exercise_id} needs {ex['equipment']}"))
        if day.est_minutes > profile.session_minutes * 1.15:
            violations.append(Violation(rule="TIME_BUDGET", severity="hard",
                detail=f"{day.date} est {day.est_minutes}min > budget"))

    rest_days = sum(1 for d in plan.days if d.type == "rest")
    if rest_days < 1:
        violations.append(Violation(rule="REST_DAY_PRESENT", severity="hard", detail="0 rest days"))

    # ... VOLUME_IN_RANGE, PROGRESSION_SANE, nutrition rules (KCAL_FLOOR,
    # PROTEIN_CEILING, SCREENING_GATE, FOOD_ID_EXISTS) follow the same shape

    return violations
```

### Repair ladder

```python
async def validate_and_repair(conn, plan: Plan, profile: UserProfile,
                               fallback: Plan) -> tuple[Plan, list[Violation]]:
    violations = await validate(conn, plan, profile)
    hard = [v for v in violations if v.severity == "hard"]
    if not hard:
        return plan, violations

    repaired = await attempt_repair(conn, plan, hard, profile)
    re_violations = await validate(conn, repaired, profile)
    if not [v for v in re_violations if v.severity == "hard"]:
        return repaired, re_violations

    await log_rejected_plan(conn, plan, hard)   # feeds /debug/validations
    return fallback, hard
```

Targeted repairs: contraindicated exercise → swap for highest-ranked legal alternative from the same pool; over time budget → drop lowest-priority isolation block; volume out of range → scale sets toward target. Anything that still fails → discard, ship deterministic, log why.

**The demo moment:** `/debug/validations` lists rejected plans and the rule that caught them. *"Gemini proposed a plan with an overhead press for a user with a shoulder injury. Our validator rejected it and fell back. The model never gets the last word."* Nobody else in the room will have this.

---

# Layer 5 — State and adaptation

**Job:** the actual product. Everything above serves this loop.

```sql
CREATE TABLE session_logs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  plan_id UUID NOT NULL,
  scheduled_date DATE NOT NULL,
  status TEXT NOT NULL,            -- completed | partial | skipped
  actual_minutes INT,
  rpe INT,                         -- 1..10
  pain_flag TEXT,
  skip_reason TEXT,                -- no_time | tired | travel | sick | unmotivated
  completed_blocks JSONB,
  logged_at TIMESTAMPTZ DEFAULT now()
);
```

### Adherence engine (deterministic, runs on every log write)

```python
async def compute_adherence(conn, user_id: str) -> AdherenceState:
    rows = await conn.fetch("""
        SELECT status, rpe, skip_reason, scheduled_date
        FROM session_logs
        WHERE user_id = $1 AND scheduled_date >= now() - interval '14 days'
        ORDER BY scheduled_date DESC
    """, user_id)
    return AdherenceState(
        adherence_14d=sum(r["status"] == "completed" for r in rows) / max(len(rows), 1),
        consecutive_misses=count_consecutive(rows, "skipped"),
        avg_rpe_7d=mean([r["rpe"] for r in rows[:7] if r["rpe"]]) or None,
        skip_reason_mode=mode([r["skip_reason"] for r in rows if r["skip_reason"]]),
    )
```

### Trigger table

| Condition | Action |
|---|---|
| 1 miss, `adherence_14d ≥ 0.7` | Reshuffle remaining week. No volume change. **No guilt copy.** |
| `consecutive_misses ≥ 2` | `volume_multiplier ×= 0.8`, shorten sessions 25%, surface 10-minute version |
| `consecutive_misses ≥ 4` | Full reset week: 2 sessions, 20 min, "restart" framing |
| `avg_rpe_7d ≤ 5` and adherence ≥ 0.8 | `volume_multiplier ×= 1.1`, tighten RIR by 1 |
| `avg_rpe_7d ≥ 9` | `volume_multiplier ×= 0.85`, add rest day |
| `pain_flag` set | Add to `injuries`, immediately re-filter and regenerate |
| `skip_reason_mode = "no_time"` | Drop `session_minutes` one tier permanently, notify why |

Then: regenerate the **next 7 days only.** Never a 12-week plan. Cheap, fast, always current.

```python
@router.post("/api/sessions/log")
async def log_session(payload: SessionLogIn, user=Depends(current_user)):
    async with get_conn() as conn:
        await insert_session_log(conn, user.id, payload)
        adherence = await compute_adherence(conn, user.id)
        state = apply_triggers(adherence)          # pure function, no I/O
        if state.needs_regen:
            new_plan = await regenerate_week(conn, user, state)
            return {"adherence": adherence, "plan": new_plan}
    return {"adherence": adherence}
```

### Structural motivation (not just copy)

- **The 10-minute version.** Every session ships a pre-computed minimum-viable variant (first compound, 2 sets). One tap. Logs as `partial`, preserves the streak.
- **Streaks survive rest days.** Streak counts *scheduled* sessions honoured — a planned rest day never breaks it.
- **The change note.** Every adaptation says why, in one sentence.
- **No guilt copy, ever.** Never "you missed 3 workouts." Say what happens next.

---

# Layer 6 — Delivery (Vite + React SPA)

### Project shape

```
/frontend
  src/
    api/client.ts        // thin fetch wrapper, typed from OpenAPI
    pages/Onboarding.tsx
    pages/Today.tsx
    pages/Logger.tsx
    pages/Adjust.tsx
    pages/Week.tsx
    pages/Nutrition.tsx
    pages/DebugValidations.tsx
  vite.config.ts          // proxy /api -> http://localhost:8000
/backend
  main.py
  db.py
  schemas/
  routers/
  planner/
  validator/
  gemini/
  rules/
  scripts/seed_exercises.py
```

### FastAPI ↔ React contract

FastAPI's auto-generated OpenAPI schema (`/openapi.json`) is the free win of this stack pairing — run `openapi-typescript` once against it to generate TS types for the React client, so the `Plan` shape can't drift between backend and frontend without a type error.

```bash
npx openapi-typescript http://localhost:8000/openapi.json -o frontend/src/api/schema.d.ts
```

```ts
// frontend/vite.config.ts
export default defineConfig({
  server: { proxy: { "/api": "http://localhost:8000" } }
});
```

### Screens (build exactly these, nothing else)

1. **Onboarding** — 6 steps, one question per screen, screening at step 5, consent at step 6.
2. **Today** — the whole product. Date, focus, est. minutes, `session_brief`, exercise cards from the catalog, "Start", "I've only got 10 minutes".
3. **Logger** — check off blocks, one RPE slider, optional pain toggle. Under 15 seconds to complete.
4. **Adjust** — free-text box wired to Call A. Your demo showpiece.
5. **Week** — seven pills, compact, secondary.
6. **Nutrition** — targets, food search, three swap suggestions. Hidden entirely if screening-gated.

### FastAPI routes

```python
# routers/plan.py
router = APIRouter(prefix="/api")

@router.post("/onboarding")
async def onboarding(profile: UserProfile) -> Plan: ...

@router.get("/plan/current")
async def current_plan(user=Depends(current_user)) -> Plan: ...

@router.post("/plan/adjust")
async def adjust(payload: AdjustIn, user=Depends(current_user)) -> Plan: ...
    # text -> Call A -> Layer 2 -> Call B -> Layer 4 -> Plan

@router.post("/sessions/log")
async def log_session(payload: SessionLogIn, user=Depends(current_user)): ...

@router.get("/today")
async def today(user=Depends(current_user)) -> TodayResponse: ...
    # Call C, cached 12h

@router.get("/nutrition/targets")
async def targets(user=Depends(current_user)) -> NutritionTargets: ...

@router.post("/nutrition/swaps")
async def swaps(user=Depends(current_user)) -> list[FoodSwap]: ...

@router.get("/debug/validations")
async def debug_validations() -> list[RejectedPlan]: ...   # judge-facing

@router.delete("/me")
async def delete_me(user=Depends(current_user)): ...        # hard delete, cascade
```

### Performance and demo safety

- **Cache Gemini responses** keyed on `sha256(profile_json + plan_state_json + call_type)` in a plain `gemini_cache` table (`key TEXT PRIMARY KEY, response JSONB, created_at`). Same input never costs a second call.
- **Never block first paint on Gemini.** `/api/plan/current` returns the deterministic plan immediately; the frontend hydrates `generated_by === "gemini_refined"` fields in when a second, faster response lands (or just accept `deterministic` for the visible demo path).
- **Stream Call C** with FastAPI's `StreamingResponse` — token-by-token coach text is the one thing that should visibly arrive live.
- **Timeouts:** 6s on Call B, 4s on Calls A and C, enforced via `asyncio.wait_for` in `call_gemini`. No retries during the demo.
- **Pre-seed a demo user** with 3 weeks of realistic session history so the adherence engine has something to react to on stage.

---

# Build order

| Window | Deliverable | Definition of done |
|---|---|---|
| **D1 09:00–11:00** | `Plan`/`UserProfile` Pydantic models, validator rule list, DB schema, exercise seed script | `python scripts/seed_exercises.py` populates 870 exercises with contraindication tags |
| **D1 11:00–15:00** | Layer 2 planner core + `/api/onboarding` | React onboarding form posts, gets back a valid 7-day plan JSON. **Working demo by lunch.** |
| **D1 15:00–18:00** | Gemini client + Calls A/B, Layer 4 validator | `/api/plan/adjust` with free text produces a different, still-valid plan |
| **D1 18:00–21:00** | `session_logs`, adherence engine, triggers | Log two skips via API → next week's plan is measurably lighter |
| **D1 21:00–23:00** | Food table seed (`COPY` from CSV), targets, swaps | 200 foods in, targets computed in code, screening gate enforced |
| **D2 09:00–13:00** | Today, Logger, Adjust screens (React) | Looks finished on one screen. Nothing else polished. |
| **D2 13:00–15:00** | Call C streaming, privacy layer, `/debug/validations` page | Delete endpoint works, validator page shows real rejections |
| **D2 15:00–17:00** | **Code freeze.** Seed demo user, warm the Gemini cache | Demo runs twice in a row with wifi off for Gemini calls |
| **D2 17:00–19:00** | Rehearse 3 minutes, five times, out loud | Everyone knows their 40 seconds |

**Cut list, non-negotiable:** RAG. Training any model. Auth beyond a name field (skip real OAuth — a signed cookie with a UUID is enough). Mobile app. Wearables. Social features. Progress photos. Grocery costing. Video demos. An ORM migration tool — three `CREATE TABLE` statements in a `schema.sql` run once at setup is enough for a hackathon; Alembic-style migrations are solving a problem you don't have this weekend.

---

# The three minutes

1. **(20s) The problem, sharply.** Not "people struggle to be fit." — *"People don't need a plan. They have plans. They quit on the second Tuesday, when they miss one day and the plan is suddenly wrong."*
2. **(40s) Meet the persona.** 20, hostel room, 30 minutes, no equipment, exams next week. Onboard live in the React app. Today screen appears in under two seconds.
3. **(50s) The moment.** Type *"skipped yesterday, shoulder's sore, only 25 minutes today"* into Adjust. Plan rewrites live. Shoulder exercises gone. Fits 25 minutes. Change note explains why.
4. **(40s) The engineering.** Show `/debug/validations`. *"Gemini proposed a plan with an overhead press for a user with a shoulder injury. Our validator rejected it and fell back. The model never gets the last word."*
5. **(30s) Privacy + the food table.** One diagram, one line: no identifiers leave the device; 200 Indian foods no Western nutrition API has.

Land on: **the coach that survives you missing a day.**
