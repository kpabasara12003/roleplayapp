"""Bounded author/player contracts. Persistent mechanics retain the original JSON shape."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator
from shared.schemas.engine import InventoryItem, CharacterAffinity

class Preferences(BaseModel):
    model_config = ConfigDict(extra='forbid')
    language: str = Field(default='English', min_length=1,max_length=60)
    response_length: Literal['short','medium','long'] = 'short'
    perspective: Literal['first','third'] = 'third'
    pacing: Literal['slow','balanced','fast'] = 'balanced'
    formatting: Literal['asterisks','plain'] = 'asterisks'
    intensity: Literal['gentle','balanced','dramatic'] = 'balanced'

class Persona(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(min_length=1,max_length=50)
    background: str = Field(default='',max_length=4000)
    personality: str = Field(default='',max_length=2000)
    appearance: str = Field(default='',max_length=1000)

class InitialState(BaseModel):
    model_config = ConfigDict(extra='forbid')
    inventory: list[InventoryItem] = Field(default_factory=list,max_length=200)
    relationships: dict[str,CharacterAffinity] = Field(default_factory=dict,max_length=100)
    quest_flags: list[str] = Field(default_factory=list,max_length=500)

    @model_validator(mode='after')
    def identities(self):
        if any(f.startswith(('rule:','world:')) for f in self.quest_flags):
            raise ValueError('Internal execution markers cannot be player quest flags')
        if len({i.id for i in self.inventory}) != len(self.inventory):
            raise ValueError('Inventory IDs must be unique')
        if any(k != v.character_name for k,v in self.relationships.items()):
            raise ValueError('Relationship keys must match character names')
        if len(set(self.quest_flags)) != len(self.quest_flags) or any(not f or len(f)>200 for f in self.quest_flags):
            raise ValueError('Flags must be unique strings of 1-200 characters')
        return self

class CharacterRuntime(BaseModel):
    model_config = ConfigDict(extra='forbid')
    motive:str=Field(default='',max_length=1000)
    activity:str=Field(default='',max_length=500)
    location:str=Field(default='',max_length=200)
    known_facts:list[str]=Field(default_factory=list,max_length=100)
    promises:list[str]=Field(default_factory=list,max_length=100)
