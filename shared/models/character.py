from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel,Field,ConfigDict
from shared.models.authoring import Name,Text4K,Text8K,Trait


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
    model_config = ConfigDict(extra='forbid')
    name: Name
    gender: str | None = Field(default=None,max_length=20)
    age: int | None = Field(default=None,ge=0,le=10000)
    personality: Text4K | None = None
    likes: list[Trait] | None = Field(default=None,max_length=30)
    dislikes: list[Trait] | None = Field(default=None,max_length=30)
    backstory: Text8K | None = None
    example_dialogue: Text4K | None = None
    appearance: str | None = Field(default=None,max_length=2000)
    greeting: Text4K | None = None
    scenario: Text4K | None = None
    role_description: str | None = Field(default=None,max_length=2000)
    scenario_id: int
    is_ai: bool = True


class CharacterUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: Name | None = None
    gender: str | None = Field(default=None,max_length=20)
    age: int | None = Field(default=None,ge=0,le=10000)
    personality: Text4K | None = None
    likes: list[Trait] | None = Field(default=None,max_length=30)
    dislikes: list[Trait] | None = Field(default=None,max_length=30)
    backstory: Text8K | None = None
    example_dialogue: Text4K | None = None
    appearance: str | None = Field(default=None,max_length=2000)
    greeting: Text4K | None = None
    scenario: Text4K | None = None
    role_description: str | None = Field(default=None,max_length=2000)


class CharacterOut(CharacterBase):
    id: int
    scenario_id: int
    is_ai: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
