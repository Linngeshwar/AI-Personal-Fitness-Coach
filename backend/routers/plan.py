import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException

from db import get_conn
from deps import current_user
from gemini.calls import interpret_constraints, refine_plan
from planner.core import generate_plan
from planner.queries import get_candidate_exercises
from queries.plans import fetch_current_plan, insert_plan
from queries.users import fetch_user, insert_user
from rules.constants import FOCUS_MUSCLES, LEVELS_FOR_EXPERIENCE, SPLITS, resolve_equipment
from rules.screening import apply_screening
from schemas.adjust import AdjustIn, ConstraintDelta
from schemas.exercise import Exercise
from schemas.plan import Plan, PlanState
from schemas.profile import UserProfile
from validator.repair import validate_and_repair

router = APIRouter(prefix="/api")

# A light-touch signal Call A's "energy" field feeds into the deterministic
# planner it already understands -- not a Gemini-authored number.
ENERGY_VOLUME_MULTIPLIER = {"low": 0.85, "normal": 1.0, "high": 1.1}

# Gemini's refine call is only ever allowed to choose from this many ids.
MAX_ALLOWED_IDS = 40


async def _build_candidate_pool(conn, profile: UserProfile) -> dict[str, list[Exercise]]:
    equipment = resolve_equipment([e.value for e in profile.equipment])
    levels = LEVELS_FOR_EXPERIENCE[profile.experience.value]
    injuries = [i.value for i in profile.injuries]

    muscles: set[str] = set()
    for focus_group in SPLITS[profile.days_per_week]:
        for focus in focus_group:
            muscles.update(FOCUS_MUSCLES[focus])

    pool: dict[str, list[Exercise]] = {}
    for muscle in muscles:
        pool[muscle] = await get_candidate_exercises(conn, muscle, equipment, levels, injuries)
    return pool


@router.post("/onboarding")
async def onboarding(profile: UserProfile) -> Plan:
    screening = apply_screening(profile)

    async with get_conn() as conn:
        user_id = await insert_user(conn, profile, screening)
        candidate_pool = await _build_candidate_pool(conn, profile)
        plan = generate_plan(
            profile,
            PlanState(),
            candidate_pool,
            user_id=user_id,
            week_start=date.today(),
            plan_id=str(uuid.uuid4()),
        )
        await insert_plan(conn, plan)

    return plan


@router.get("/plan/current")
async def current_plan(user_id: str = Depends(current_user)) -> Plan:
    async with get_conn() as conn:
        plan = await fetch_current_plan(conn, user_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="no plan yet")
    return plan


def _apply_delta(profile: UserProfile, delta: ConstraintDelta) -> UserProfile:
    updates: dict = {}
    if delta.session_minutes_override is not None:
        updates["session_minutes"] = delta.session_minutes_override
    if delta.equipment_override:
        updates["equipment"] = delta.equipment_override
    if delta.new_injuries:
        updates["injuries"] = list(dict.fromkeys([*profile.injuries, *delta.new_injuries]))
    return profile.model_copy(update=updates) if updates else profile


@router.post("/plan/adjust")
async def adjust(payload: AdjustIn, user_id: str = Depends(current_user)) -> Plan:
    # text -> Call A -> Layer 2 -> Call B -> Layer 4 -> Plan
    async with get_conn() as conn:
        profile = await fetch_user(conn, user_id)
        if profile is None:
            raise HTTPException(status_code=404, detail="no profile on file")

        delta = await interpret_constraints(payload.text, profile)
        merged_profile = _apply_delta(profile, delta) if delta else profile
        volume_multiplier = ENERGY_VOLUME_MULTIPLIER.get(delta.energy, 1.0) if delta else 1.0

        candidate_pool = await _build_candidate_pool(conn, merged_profile)
        draft = generate_plan(
            merged_profile,
            PlanState(volume_multiplier=volume_multiplier),
            candidate_pool,
            user_id=user_id,
            week_start=date.today(),
            plan_id=str(uuid.uuid4()),
        )

        # Draft's own exercises are always in-bounds for Gemini to keep;
        # fill the rest of the whitelist from the same candidate pool.
        draft_ids = sorted({b.exercise_id for d in draft.days for b in d.blocks})
        pool_ids = {e.id for pool in candidate_pool.values() for e in pool}
        extra_ids = sorted(pool_ids - set(draft_ids))
        allowed_ids = draft_ids + extra_ids[: max(0, MAX_ALLOWED_IDS - len(draft_ids))]

        refined = await refine_plan(draft, merged_profile, allowed_ids)
        candidate = draft if refined is None else refined.model_copy(update={"generated_by": "gemini_refined"})

        final_plan, _violations = await validate_and_repair(conn, candidate, merged_profile, fallback=draft)
        await insert_plan(conn, final_plan)

    return final_plan
