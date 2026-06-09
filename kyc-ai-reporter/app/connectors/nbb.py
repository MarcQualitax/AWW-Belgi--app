import httpx
from app.config import settings
from app.connectors.base import Connector
from app.models import SourceRecord


class NbbConnector(Connector):
    name = "NBB Balanscentrale"

    async def fetch(self, enterprise_number: str) -> SourceRecord:
        if not settings.nbb_api_base_url or "example" in settings.nbb_api_base_url:
            return SourceRecord(
                source=self.name,
                status="not_configured",
                url="https://www.nbb.be/nl/balanscentrale",
                warnings=["Configureer een geldige NBB-datatoegang of gebruik de officiële raadpleegtoepassing."],
                data={"enterprise_number": enterprise_number},
            )
        headers = {"Authorization": f"Bearer {settings.nbb_api_key}"} if settings.nbb_api_key else {}
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(f"{settings.nbb_api_base_url}/annual-accounts/{enterprise_number}", headers=headers)
            r.raise_for_status()
            return SourceRecord(source=self.name, status="ok", url=str(r.url), data=r.json())
