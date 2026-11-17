from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel


class CharacterBase(BaseModel):
    name: str
    gender: Optional[str] = None
    age: Optional[int] = None
    personality: Optional[str] = None
    likes: Optional[List[str]] = None
    dislikes: Optional[List[str]] = None
    backstory: Optional[str] = None
    example_dialogue: Optional[str] = None
    appearance: Optional[str] = None
    greeting: Optional[str] = None
    scenario: Optional[str] = None
    role_description: Optional[str] = None


class CharacterCreate(CharacterBase):
    scenario_id: int
    is_ai: bool = True


class CharacterUpdate(BaseModel):
    name: Optional[str] = None
    gender: Optional[str] = None
    age: Optional[int] = None
    personality: Optional[str] = None
    likes: Optional[List[str]] = None
    dislikes: Optional[List[str]] = None
    backstory: Optional[str] = None
    example_dialogue: Optional[str] = None
    appearance: Optional[str] = None
    greeting: Optional[str] = None
    scenario: Optional[str] = None
    role_description: Optional[str] = None


class CharacterOut(CharacterBase):
    id: int
    scenario_id: int
    is_ai: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
