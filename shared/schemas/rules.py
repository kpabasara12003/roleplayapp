from pydantic import BaseModel, Field, model_validator
from shared.schemas.engine import EngineMutation

class Transition(BaseModel):
    id: str = Field(min_length=1,max_length=80,pattern=r'^[a-zA-Z0-9_-]+$')
    triggers: list[str] = Field(min_length=1,max_length=20)
    requires_items: dict[str,int] = Field(default_factory=dict)
    requires_flags: list[str] = Field(default_factory=list)
    once: bool = True
    mutations: list[EngineMutation] = Field(default_factory=list,max_length=20)

    @model_validator(mode='after')
    def prerequisites(self):
        if any(not trigger.strip() for trigger in self.triggers):
            raise ValueError('Triggers cannot be blank')
        if any(quantity<1 for quantity in self.requires_items.values()):
            raise ValueError('Required item quantities must be positive')
        return self

class WorldEvent(BaseModel):
    id: str = Field(min_length=1,max_length=80,pattern=r'^[a-zA-Z0-9_-]+$')
    description: str = Field(min_length=1,max_length=1000)
    narration: str = Field(min_length=1,max_length=2500)
    requires_flags: list[str] = Field(default_factory=list)
    min_turns: int = Field(default=0,ge=0)
    once: bool = True
    mutations: list[EngineMutation] = Field(default_factory=list,max_length=20)

class ScenarioRules(BaseModel):
    transitions: list[Transition] = Field(default_factory=list,max_length=100)
    world_events: list[WorldEvent] = Field(default_factory=list,max_length=100)

    @model_validator(mode='after')
    def unique_ids(self):
        for group in (self.transitions,self.world_events):
            if len({item.id for item in group}) != len(group):
                raise ValueError('Rule IDs must be unique')
        return self
