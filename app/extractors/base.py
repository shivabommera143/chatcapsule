from abc import ABC, abstractmethod

from app.models import Conversation


class ConversationExtractor(ABC):
    @abstractmethod
    async def extract(self, url: str) -> Conversation:
        """Fetch and normalize one shared conversation."""
