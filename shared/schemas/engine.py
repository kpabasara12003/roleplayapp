#roleplay_backend/app/schemas/engine.py
from enum import Enum
from typing import Annotated
from pydantic import BaseModel, Field, model_validator
from typing import List, Optional
class InventoryItem(BaseModel):
    id: str = Field(min_length=1,max_length=100,pattern=r'^[a-z0-9_-]+$')
    name: str = Field(min_length=1,max_length=200)
    description: str = Field(max_length=2000)
    quantity: int = Field(default=1, ge=1,le=10000,strict=True)

class CharacterAffinity(BaseModel):
    character_name: str
    affinity_score: Annotated[int, Field(ge=-100, le=100)] = 0
    relationship_status: str = "Stranger"       # Friendly, Suspicious, Rival, Ally

class MutationType(str, Enum):
    QUEST_STARTED = 'QUEST_STARTED'
    QUEST_RESTARTED = 'QUEST_RESTARTED'
    QUEST_FAILED = 'QUEST_FAILED'
    QUEST_PROGRESS = 'QUEST_PROGRESS'
    CHARACTER_UPDATED = 'CHARACTER_UPDATED'
    FLAG_CLEARED = 'FLAG_CLEARED'
    QUEST_ADVANCED = 'QUEST_ADVANCED'
    CLOCK_ADVANCED = 'CLOCK_ADVANCED'
    ITEM_ADDED = "ITEM_ADDED"
    ITEM_REMOVED = "ITEM_REMOVED"
    AFFINITY_CHANGED = "AFFINITY_CHANGED"
    FLAG_TRIGGERED = "FLAG_TRIGGERED"
    LOCATION_CHANGED = "LOCATION_CHANGED"
    TIME_CHANGED = "TIME_CHANGED"

class EngineMutation(BaseModel):
    """A mechanical shift determined by the Director Agent"""
    type: MutationType
    target: str      # Name of item, character, flag, or new location/time string
    description: str # UI notice message: e.g., "Evelyn liked that (+5 Affinity)"
    value_change: Optional[int] = None # Used for incrementing/decrementing scores or quantities
    character_state: Optional[dict] = None

    @model_validator(mode='after')
    def validate_change(self):
        if not self.target.strip() or len(self.target) > 200:
            raise ValueError('Mutation target must contain 1-200 characters')
        if self.type in (MutationType.ITEM_ADDED, MutationType.ITEM_REMOVED):
            if self.value_change is not None and not 1 <= self.value_change <= 10000:
                raise ValueError('Item quantity must be between 1 and 10000')
        if self.type == MutationType.AFFINITY_CHANGED and self.value_change is not None:
            if not -100 <= self.value_change <= 100:
                raise ValueError('Affinity change must be between -100 and 100')
        return self

class DirectorEvaluation(BaseModel):
    """The structured schema output required from the Director Agent LLM call"""
    reasoning: str = Field(max_length=1000,description="Brief action decision explanation")
    is_action_allowed: bool = Field(description="Set to false if player is cheating, godmoding, or lacks a required item")
    failure_explanation: Optional[str] = Field(description="Why it failed, passed to the Chronicler to narrate if disallowed")
    
    # Structural updates to apply
    mutations: List[EngineMutation] = Field(default_factory=list)
    command_ids: list[str] = Field(default_factory=list,max_length=5)
