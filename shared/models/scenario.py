from typing import Optional
from datetime import datetime
from pydantic import BaseModel
from pydantic import Field
from shared.schemas.rules import ScenarioRules
from shared.schemas.playthrough import InitialState


class ScenarioBase(BaseModel):
    initial_state: InitialState = Field(default_factory=InitialState)
    title: str
    greeting: Optional[str] = None
    place: Optional[str] = None
    time: Optional[str] = None
    introduction: Optional[str] = None
    is_public: bool = False
    rules: ScenarioRules = Field(default_factory=ScenarioRules)


class ScenarioCreate(ScenarioBase):
    pass


class ScenarioUpdate(BaseModel):
    initial_state: Optional[InitialState] = None
    rules: Optional[ScenarioRules] = None
    title: Optional[str] = None
    greeting: Optional[str] = None
    place: Optional[str] = None
    time: Optional[str] = None
    introduction: Optional[str] = None
    is_public: Optional[bool] = None


class ScenarioOut(ScenarioBase):
    id: int
    user_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
