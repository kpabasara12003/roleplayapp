from typing import Optional
from datetime import datetime
from pydantic import BaseModel


class ScenarioBase(BaseModel):
    title: str
    greeting: Optional[str] = None
    place: Optional[str] = None
    time: Optional[str] = None
    introduction: Optional[str] = None
    is_public: bool = False


class ScenarioCreate(ScenarioBase):
    pass


class ScenarioUpdate(BaseModel):
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
