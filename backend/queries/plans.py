from schemas.plan import Plan

INSERT_SQL = """
INSERT INTO plans (id, user_id, week_start, generated_by, volume_multiplier, plan_json)
VALUES ($1, $2, $3, $4, $5, $6::jsonb);
"""

SELECT_CURRENT_SQL = """
SELECT plan_json FROM plans
WHERE user_id = $1
ORDER BY created_at DESC
LIMIT 1;
"""


async def insert_plan(conn, plan: Plan) -> None:
    await conn.execute(
        INSERT_SQL,
        plan.plan_id, plan.user_id, plan.week_start, plan.generated_by,
        plan.volume_multiplier, plan.model_dump_json(),
    )


async def fetch_current_plan(conn, user_id: str) -> Plan | None:
    row = await conn.fetchrow(SELECT_CURRENT_SQL, user_id)
    if row is None:
        return None
    return Plan.model_validate_json(row["plan_json"])
