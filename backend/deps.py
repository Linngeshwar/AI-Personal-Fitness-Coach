from fastapi import HTTPException

from db import get_conn

# No auth right now -- per spec's cut list this was already going to be
# "a signed cookie with a UUID," and for a single-developer/demo app even
# that's more ceremony than the app needs today. Every route just operates
# on whoever most recently completed onboarding. Real auth is a distinct,
# later concern, not a blocker for using the app.


async def current_user() -> str:
    async with get_conn() as conn:
        row = await conn.fetchrow("SELECT id FROM users ORDER BY created_at DESC LIMIT 1")
    if row is None:
        raise HTTPException(status_code=404, detail="no profile yet -- complete onboarding first")
    return str(row["id"])
