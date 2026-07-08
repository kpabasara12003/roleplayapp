from typing import Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel


class MessageCreate(BaseModel):
    conversation_id: int
    sender: str  # 'user' or 'ai'
    content: str
    metadata: Optional[Dict[str, Any]] = None


class MessageOut(BaseModel):
    id: int
    conversation_id: int
    sender: str
    content: str
    metadata: Optional[Dict[str, Any]] = None
    created_at: datetime

    class Config:
        from_attributes = True
