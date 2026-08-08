from privacy.crypto import decrypt_health, encrypt_health
from schemas.profile import Injury, SafetyFlags, ScreeningResult, UserProfile

INSERT_SQL = """
INSERT INTO users (
    goal, experience, days_per_week, session_minutes, equipment,
    height_cm, age, sex, activity_level, nutrition_enabled,
    requires_clearance, health_encrypted
) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
RETURNING id;
"""

SELECT_SQL = """
SELECT id, goal, experience, days_per_week, session_minutes, equipment,
       height_cm, age, sex, activity_level, nutrition_enabled,
       requires_clearance, health_encrypted
FROM users WHERE id = $1;
"""

DELETE_SQL = "DELETE FROM users WHERE id = $1;"


async def insert_user(conn, profile: UserProfile, screening: ScreeningResult) -> str:
    health_blob = encrypt_health({
        "weight_kg": profile.weight_kg,
        "injuries": [i.value for i in profile.injuries],
        "safety": profile.safety.model_dump(),
    })
    row = await conn.fetchrow(
        INSERT_SQL,
        profile.goal.value, profile.experience.value, profile.days_per_week,
        profile.session_minutes, [e.value for e in profile.equipment],
        profile.height_cm, profile.age, profile.sex, profile.activity_level,
        screening.nutrition_enabled, screening.requires_clearance, health_blob,
    )
    return str(row["id"])


async def fetch_user(conn, user_id: str) -> UserProfile | None:
    row = await conn.fetchrow(SELECT_SQL, user_id)
    if row is None:
        return None
    health = decrypt_health(row["health_encrypted"])
    return UserProfile(
        goal=row["goal"],
        experience=row["experience"],
        days_per_week=row["days_per_week"],
        session_minutes=row["session_minutes"],
        equipment=list(row["equipment"]),
        injuries=[Injury(i) for i in health["injuries"]],
        height_cm=float(row["height_cm"]),
        weight_kg=float(health["weight_kg"]),
        age=row["age"],
        sex=row["sex"],
        activity_level=float(row["activity_level"]),
        safety=SafetyFlags(**health["safety"]),
    )


async def delete_user(conn, user_id: str) -> None:
    await conn.execute(DELETE_SQL, user_id)
