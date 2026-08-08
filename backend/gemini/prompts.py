from schemas.plan import Plan
from schemas.profile import UserProfile

CONSTRAINT_SYSTEM = """You translate a user's free-text note about today's training into a
structured delta. Only set fields the note actually implies; leave everything
else at its default. intent must be exactly one of: train, skip, shorten, substitute."""


def build_constraint_prompt(text: str, profile: UserProfile) -> str:
    return (
        f"{CONSTRAINT_SYSTEM}\n\n"
        f"USER PROFILE (context only, do not restate it):\n{profile.model_dump_json()}\n\n"
        f"USER NOTE: {text}\n"
    )


REFINE_SYSTEM = """You are refining a workout plan. You may ONLY use exercise IDs from
ALLOWED_IDS. You may reorder blocks, swap an exercise for another ALLOWED_ID,
and adjust sets by +/-1. You may NOT invent exercises, change the number of
training days, or exceed the stated time budget. For every swap, give a
one-sentence swap_reason. Keep plan_id, user_id, week_start, and
volume_multiplier exactly as given in PLAN."""


def build_refine_prompt(plan: Plan, profile: UserProfile, allowed_ids: list[str]) -> str:
    return (
        f"{REFINE_SYSTEM}\n\n"
        f"ALLOWED_IDS: {allowed_ids}\n\n"
        f"PLAN: {plan.model_dump_json()}\n\n"
        f"PROFILE: {profile.model_dump_json()}\n"
    )
