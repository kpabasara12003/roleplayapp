"""Creator metadata; available terms are managed in PostgreSQL catalog_terms."""
from typing import Annotated
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

Slug=Annotated[str,StringConstraints(pattern=r'^[a-z][a-z0-9_]{0,49}$')]

class Discovery(BaseModel):
    model_config=ConfigDict(extra='forbid')
    genres:list[Slug]=Field(default_factory=list,max_length=4)
    tones:list[Slug]=Field(default_factory=list,max_length=3)
    life_stage:Slug='any'

    @field_validator('genres','tones')
    @classmethod
    def unique(cls,value):
        return list(dict.fromkeys(value))

async def validate_discovery(discovery,cast=None):
    from shared.db.postgres import fetch_all
    from fastapi import HTTPException
    metadata=Discovery.model_validate(discovery)
    terms=await fetch_all('SELECT kind,slug,requires_adult_cast FROM catalog_terms WHERE active')
    selected=[('genre',v) for v in metadata.genres]+[('tone',v) for v in metadata.tones]+[('life_stage',metadata.life_stage)]
    available={(row['kind'],row['slug']):row for row in terms}
    if any(key not in available for key in selected):
        raise HTTPException(422,'Choose available discovery categories. Refresh the category list and try again.')
    if cast is not None and any(available[key]['requires_adult_cast'] for key in selected):
        if any(c.get('age') is None or c['age']<18 for c in cast):
            raise HTTPException(422,'These categories require an age of 18 or older for every cast character.')
