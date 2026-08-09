from pydantic import BaseModel


class ChatMessage(BaseModel):
    session_id: str
    role: str
    content: str
