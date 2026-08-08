from gemini.client import call_gemini
from gemini.prompts import build_constraint_prompt, build_refine_prompt
from schemas.adjust import ConstraintDelta
from schemas.plan import Plan
from schemas.profile import UserProfile

# Measured against gemini-flash-lite-latest (see gemini/client.py) with a
# real 7-day/16-block plan and a 40-id whitelist: Call A 1.0-2.4s (37
# output tokens), Call B 3.6-5.6s (~1.3k output tokens -- it re-emits the
# whole plan, so its floor is bounded by plan size, not prompt complexity).
#
# Budgets sit well above those ranges on purpose. The previous 12s Call B
# budget sat *inside* its own latency spread, so a normal-but-slow response
# tripped the timeout and silently dropped the user back to the unrefined
# deterministic plan. Gemini's transient 503s ("high demand") are real, and
# a slow-but-legitimate response beats an unnecessary fallback every time.
CALL_A_TIMEOUT_S = 10.0
CALL_B_TIMEOUT_S = 20.0


async def interpret_constraints(text: str, profile: UserProfile) -> ConstraintDelta | None:
    """Call A -- Gemini never writes the plan here, it translates human mess
    ("knee's been hurting, only got 25 mins") into UserProfile's own schema.
    Layer 2 re-runs on whatever comes back."""
    prompt = build_constraint_prompt(text, profile)
    return await call_gemini(prompt, ConstraintDelta, temperature=0.2, timeout_s=CALL_A_TIMEOUT_S)


async def refine_plan(plan: Plan, profile: UserProfile, allowed_ids: list[str]) -> Plan | None:
    """Call B -- proposes swaps within an explicit whitelist. Never trusted
    directly: the caller still runs this through the Layer 4 validator."""
    prompt = build_refine_prompt(plan, profile, allowed_ids)
    return await call_gemini(prompt, Plan, temperature=0.3, timeout_s=CALL_B_TIMEOUT_S)
