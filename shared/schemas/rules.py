from pydantic import BaseModel, Field, model_validator
from shared.schemas.engine import EngineMutation,InventoryItem

class Transition(BaseModel):
    id: str = Field(min_length=1,max_length=80,pattern=r'^[a-zA-Z0-9_-]+$')
    triggers: list[str] = Field(default_factory=list,max_length=20)
    description: str = Field(default='',max_length=1000)
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
    items:dict[str,InventoryItem]=Field(default_factory=dict,max_length=200)
    writing_defaults: dict = Field(default_factory=dict)
    track_relationships: bool = True
    mode: str = Field(default='freeform',pattern=r'^(freeform|structured)$')
    relationship_thresholds: dict[str,int] = Field(default_factory=lambda:{'Rival':-50,'Stranger':-10,'Acquaintance':10,'Friend':40,'Ally':75})
    quests: dict[str,list[str]] = Field(default_factory=dict,max_length=100)
    quest_objectives: dict[str,dict[str,int]] = Field(default_factory=dict,max_length=100)
    transitions: list[Transition] = Field(default_factory=list,max_length=100)
    world_events: list[WorldEvent] = Field(default_factory=list,max_length=100)

    @model_validator(mode='after')
    def unique_ids(self):
        if any(key!=item.id for key,item in self.items.items()):
            raise ValueError('Item catalog keys must match stable item IDs')
        from shared.schemas.playthrough import Preferences
        Preferences.model_validate(self.writing_defaults)
        if any(not -100<=value<=100 for value in self.relationship_thresholds.values()):
            raise ValueError('Relationship thresholds must be -100 through 100')
        if any(not stages or len(stages)>100 for stages in self.quests.values()):
            raise ValueError('Quests require 1-100 stages')
        if any(not objectives or any(value<1 or value>10000 for value in objectives.values()) for objectives in self.quest_objectives.values()):
            raise ValueError('Quest objectives require positive bounded targets')
        for group in (self.transitions,self.world_events):
            if len({item.id for item in group}) != len(group):
                raise ValueError('Rule IDs must be unique')
        return self
