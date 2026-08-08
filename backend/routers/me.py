from fastapi import APIRouter, Depends

from db import get_conn
from deps import current_user
from queries.users import delete_user

router = APIRouter(prefix="/api")


@router.delete("/me")
async def delete_me(user_id: str = Depends(current_user)) -> dict:
    async with get_conn() as conn:
        await delete_user(conn, user_id)
    return {"deleted": True}
