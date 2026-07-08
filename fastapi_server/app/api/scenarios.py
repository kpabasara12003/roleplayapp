from typing import List
from fastapi import APIRouter, HTTPException, Depends

from shared.db.postgres import fetch_one, fetch_all, execute, execute_returning
from shared.models.scenario import ScenarioCreate, ScenarioUpdate, ScenarioOut
from fastapi_server.app.api.users import get_current_user

router = APIRouter(prefix="/scenarios", tags=["Scenarios"])


@router.post("", response_model=ScenarioOut, status_code=201)
async def create_scenario(
    payload: ScenarioCreate,
    user: dict = Depends(get_current_user),
):
    row = await execute_returning(
        """
        INSERT INTO scenarios (user_id, title, greeting, place, time, introduction, is_public)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        RETURNING id, user_id, title, greeting, place, time, introduction, is_public, created_at, updated_at
        """,
        (
            user["id"],
            payload.title,
            payload.greeting,
            payload.place,
            payload.time,
            payload.introduction,
            payload.is_public,
        ),
    )
    if not row:
        raise HTTPException(status_code=500, detail="Failed to create scenario")
    return row


@router.get("", response_model=List[ScenarioOut])
async def list_scenarios(user: dict = Depends(get_current_user)):
    rows = await fetch_all(
        """
        SELECT id, user_id, title, greeting, place, time, introduction, is_public, created_at, updated_at
        FROM scenarios WHERE user_id = %s ORDER BY created_at DESC
        """,
        (user["id"],),
    )
    return rows


@router.get("/{scenario_id}", response_model=ScenarioOut)
async def get_scenario(scenario_id: int, user: dict = Depends(get_current_user)):
    row = await fetch_one(
        """
        SELECT id, user_id, title, greeting, place, time, introduction, is_public, created_at, updated_at
        FROM scenarios WHERE id = %s AND user_id = %s
        """,
        (scenario_id, user["id"]),
    )
    if not row:
        raise HTTPException(status_code=404, detail="Scenario not found")
    return row


@router.patch("/{scenario_id}", response_model=ScenarioOut)
async def update_scenario(
    scenario_id: int,
    payload: ScenarioUpdate,
    user: dict = Depends(get_current_user),
):
    # Build dynamic SET clause safely
    fields = []
    values = []
    if payload.title is not None:
        fields.append("title = %s")
        values.append(payload.title)
    if payload.greeting is not None:
        fields.append("greeting = %s")
        values.append(payload.greeting)
    if payload.place is not None:
        fields.append("place = %s")
        values.append(payload.place)
    if payload.time is not None:
        fields.append("time = %s")
        values.append(payload.time)
    if payload.introduction is not None:
        fields.append("introduction = %s")
        values.append(payload.introduction)
    if payload.is_public is not None:
        fields.append("is_public = %s")
        values.append(payload.is_public)

    if not fields:
        raise HTTPException(status_code=400, detail="No fields to update")

    values.extend([scenario_id, user["id"]])
    sql = f"""
        UPDATE scenarios SET {', '.join(fields)}
        WHERE id = %s AND user_id = %s
        RETURNING id, user_id, title, greeting, place, time, introduction, is_public, created_at, updated_at
    """
    row = await execute_returning(sql, tuple(values))
    if not row:
        raise HTTPException(status_code=404, detail="Scenario not found")
    return row


@router.delete("/{scenario_id}", status_code=204)
async def delete_scenario(scenario_id: int, user: dict = Depends(get_current_user)):
    count = await execute(
        "DELETE FROM scenarios WHERE id = %s AND user_id = %s",
        (scenario_id, user["id"]),
    )
    if count == 0:
        raise HTTPException(status_code=404, detail="Scenario not found")
    return None
