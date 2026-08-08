from fastapi import APIRouter, Depends, HTTPException

from db import get_conn
from deps import current_user
from queries.users import delete_user, fetch_user
from rules.bmi import compute_bmi_summary
from schemas.profile import BmiSummary

router = APIRouter(prefix="/api")


@router.get("/me/bmi")
async def me_bmi(user_id: str = Depends(current_user)) -> BmiSummary:
    async with get_conn() as conn:
        profile = await fetch_user(conn, user_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="no profile on file")
    return compute_bmi_summary(profile)


@router.delete("/me")
async def delete_me(user_id: str = Depends(current_user)) -> dict:
    async with get_conn() as conn:
        await delete_user(conn, user_id)
    return {"deleted": True}
