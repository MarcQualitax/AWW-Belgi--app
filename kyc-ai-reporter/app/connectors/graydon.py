import httpx
from app.config import settings
from app.connectors.base import Connector
from app.models import SourceRecord


class GraydonConnector(Connector):
    name = "Graydon/Craydon commerciële kredietdata"

    async def fetch(self, enterprise_number: str) -> SourceRecord:
        if not settings.graydon_api_base_url or not settings.graydon_api_key:
            return SourceRecord(
                source=self.name,
                status="not_configured",
                warnings=["Alleen activeren met geldige licentie en API-contract."],
                data={"enterprise_number": enterprise_number},
            )
        headers = {"Authorization": f"Bearer {settings.graydon_api_key}"}
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(f"{settings.graydon_api_base_url}/companies/{enterprise_number}", headers=headers)
            r.raise_for_status()
            return SourceRecord(source=self.name, status="ok", url=str(r.url), data=r.json())
