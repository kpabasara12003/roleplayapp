from pydantic import BaseModel, Field
from typing import Optional, Any, Literal
from datetime import datetime

class WSBaseEvent(BaseModel):
    """Base schema for all WebSocket communications."""
    event: str
    conversation_id: int
    timestamp: datetime = Field(default_factory=datetime.utcnow)

class InboundUserMessage(BaseModel):
    """Payload sent by the frontend user via the WebSocket."""
    content: str

class OutboundStatePayload(BaseModel):
    """Payload representing system states (typing, searching memory, errors)."""
    state: Literal["processing_memory", "typing", "completed", "error"]
    message: Optional[str] = None
    error_detail: Optional[str] = None

class OutboundChunkPayload(BaseModel):
    """Payload representing an atomic text token streaming back from the LLM agent."""
    chunk: str
    index: int

class OutboundMessageCompletePayload(BaseModel):
    """Payload confirming generation ended and content has been safely indexed."""
    message_id: int
    sender: Literal["ai", "user"]
    full_content: str

class OutboundWSEvent(WSBaseEvent):
    """Wrapper sent to the client browser containing wrapped states or text data."""
    payload: dict[str, Any]