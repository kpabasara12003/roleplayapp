from typing import Optional
from datetime import datetime
from pydantic import BaseModel
from pydantic import Field
from shared.schemas.rules import ScenarioRules
from shared.schemas.playthrough import InitialState
from shared.models.authoring import Title,ShortText,Text4K,Text12K
from pydantic import ConfigDict
from shared.models.discovery import Discovery


class ScenarioBase(BaseModel):
    discovery: Discovery = Field(default_factory=Discovery)
    initial_state: InitialState = Field(default_factory=InitialState)
    title: str
    greeting: Optional[str] = None
    place: Optional[str] = None
    time: Optional[str] = None
    introduction: Optional[str] = None
    is_public: bool = False
    rules: ScenarioRules = Field(default_factory=ScenarioRules)


class ScenarioCreate(ScenarioBase):
    model_config = ConfigDict(extra='forbid')
    title: Title
    greeting: Text4K | None = None
    place: ShortText | None = None
    time: ShortText | None = None
    introduction: Text12K | None = None


class ScenarioUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    discovery: Discovery | None = None
    initial_state: Optional[InitialState] = None
    rules: Optional[ScenarioRules] = None
    title: Title | None = None
    greeting: Text4K | None = None
    place: ShortText | None = None
    time: ShortText | None = None
    introduction: Text12K | None = None
    is_public: Optional[bool] = None


class ScenarioOut(ScenarioBase):
    id: int
    user_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
