from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Role = Literal["user", "assistant", "system", "unknown"]


class Message(BaseModel):
    role: Role = "unknown"
    content: str
    index: int


class Conversation(BaseModel):
    title: str | None = None
    source_url: str
    messages: list[Message] = Field(default_factory=list)


class CapsuleRequest(BaseModel):
    url: str
