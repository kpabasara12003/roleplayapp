from typing import List
from fastapi import APIRouter, HTTPException, Depends

from shared.db.postgres import fetch_one, fetch_all, execute, execute_returning
from shared.models.character import CharacterCreate, CharacterUpdate, CharacterOut
from fastapi_server.app.api.users import get_current_user

router = APIRouter(prefix="/characters", tags=["Characters"])


@router.post("", response_model=CharacterOut, status_code=201)
async def create_character(
    payload: CharacterCreate,
    user: dict = Depends(get_current_user),
):
    # Verify scenario ownership
    scenario = await fetch_one(
        "SELECT id FROM scenarios WHERE id = %s AND user_id = %s AND deleted_at IS NULL",
        (payload.scenario_id, user["id"]),
    )
    if not scenario:
        raise HTTPException(status_code=404, detail="Scenario not found")

    row = await execute_returning(
        """
        INSERT INTO characters (
            scenario_id, is_ai, name, gender, age, personality, likes, dislikes,
            backstory, example_dialogue, appearance, greeting, scenario, role_description
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id, scenario_id, is_ai, name, gender, age, personality, likes, dislikes,
                  backstory, example_dialogue, appearance, greeting, scenario, role_description,
                  created_at, updated_at
        """,
        (
            payload.scenario_id,
            payload.is_ai,
            payload.name,
            payload.gender,
            payload.age,
            payload.personality,
            payload.likes,
            payload.dislikes,
            payload.backstory,
            payload.example_dialogue,
            payload.appearance,
            payload.greeting,
            payload.scenario,
            payload.role_description,
        ),
    )
    if not row:
        raise HTTPException(status_code=500, detail="Failed to create character")
    return row


@router.get("", response_model=List[CharacterOut])
async def list_characters(
    scenario_id: int,
    is_ai: bool = None,
    user: dict = Depends(get_current_user),
):
    base_sql = """
        SELECT c.id, c.scenario_id, c.is_ai, c.name, c.gender, c.age, c.personality,
               c.likes, c.dislikes, c.backstory, c.example_dialogue, c.appearance,
               c.greeting, c.scenario, c.role_description, c.created_at, c.updated_at
        FROM characters c
        JOIN scenarios s ON c.scenario_id = s.id
        WHERE s.deleted_at IS NULL AND s.user_id = %s AND c.scenario_id = %s
    """
    params: list = [user["id"], scenario_id]
    if is_ai is not None:
        base_sql += " AND c.is_ai = %s"
        params.append(is_ai)
    base_sql += " ORDER BY c.created_at ASC"
    rows = await fetch_all(base_sql, tuple(params))
    return rows


@router.get("/{character_id}", response_model=CharacterOut)
async def get_character(
    character_id: int,
    user: dict = Depends(get_current_user),
):
    row = await fetch_one(
        """
        SELECT c.id, c.scenario_id, c.is_ai, c.name, c.gender, c.age, c.personality,
               c.likes, c.dislikes, c.backstory, c.example_dialogue, c.appearance,
               c.greeting, c.scenario, c.role_description, c.created_at, c.updated_at
        FROM characters c
        JOIN scenarios s ON c.scenario_id = s.id
        WHERE s.deleted_at IS NULL AND c.id = %s AND s.user_id = %s
        """,
        (character_id, user["id"]),
    )
    if not row:
        raise HTTPException(status_code=404, detail="Character not found")
    return row


@router.patch("/{character_id}", response_model=CharacterOut)
async def update_character(
    character_id: int,
    payload: CharacterUpdate,
    user: dict = Depends(get_current_user),
):
    # Verify ownership via scenario
    owner = await fetch_one(
        """
        SELECT c.id FROM characters c
        JOIN scenarios s ON c.scenario_id = s.id
        WHERE s.deleted_at IS NULL AND c.id = %s AND s.user_id = %s
        """,
        (character_id, user["id"]),
    )
    if not owner:
        raise HTTPException(status_code=404, detail="Character not found")

    fields = []
    values = []
    for field_name in [
        "name", "gender", "age", "personality", "likes", "dislikes",
        "backstory", "example_dialogue", "appearance", "greeting", "scenario", "role_description",
    ]:
        val = getattr(payload, field_name)
        if field_name in payload.model_fields_set and (val is not None or field_name != 'name'):
            fields.append(f"{field_name} = %s")
            values.append(val)

    if not fields:
        raise HTTPException(status_code=400, detail="No fields to update")

    values.extend([character_id])
    sql = f"""
        UPDATE characters SET {', '.join(fields)}
        WHERE id = %s
        RETURNING id, scenario_id, is_ai, name, gender, age, personality, likes, dislikes,
                  backstory, example_dialogue, appearance, greeting, scenario, role_description,
                  created_at, updated_at
    """
    row = await execute_returning(sql, tuple(values))
    if not row:
        raise HTTPException(status_code=500, detail="Failed to update character")
    return row


@router.delete("/{character_id}", status_code=204)
async def delete_character(
    character_id: int,
    user: dict = Depends(get_current_user),
):
    count = await execute(
        """
        DELETE FROM characters c USING scenarios s
        WHERE c.id = %s AND c.scenario_id = s.id AND s.user_id = %s AND s.deleted_at IS NULL
        """,
        (character_id, user["id"]),
    )
    if count == 0:
        raise HTTPException(status_code=404, detail="Character not found")
    return None
