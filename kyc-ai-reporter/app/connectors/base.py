from abc import ABC, abstractmethod
from app.models import SourceRecord


class Connector(ABC):
    name: str

    @abstractmethod
    async def fetch(self, enterprise_number: str) -> SourceRecord:
        raise NotImplementedError
