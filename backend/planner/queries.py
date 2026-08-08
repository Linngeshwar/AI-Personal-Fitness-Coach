from schemas.exercise import Exercise


async def get_candidate_exercises(
    conn, muscle: str, equipment: list[str], levels: list[str], injuries: list[str]
) -> list[Exercise]:
    rows = await conn.fetch(
        """
        SELECT * FROM exercises
        WHERE primary_muscle = $1
          AND equipment = ANY($2)
          AND level = ANY($3)
          AND NOT (contraindications && $4)
        """,
        muscle, equipment, levels, injuries,
    )
    return [Exercise(**dict(r)) for r in rows]
