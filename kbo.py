import httpx
from app.config import settings
from app.connectors.base import Connector
from app.models import SourceRecord


class KboConnector(Connector):
    name = "KBO Public Search/Webservice"

    async def fetch(self, enterprise_number: str) -> SourceRecord:
        if not settings.kbo_api_base_url or "example" in settings.kbo_api_base_url:
            return SourceRecord(
                source=self.name,
                status="not_configured",
                url="https://economie.fgov.be/nl/themas/ondernemingen/kruispuntbank-van",
                warnings=["Configureer de officiële KBO Webservice Public Search of een toegestane dataleverancier."],
                data={"enterprise_number": enterprise_number},
            )
        headers = {"Authorization": f"Bearer {settings.kbo_api_key}"} if settings.kbo_api_key else {}
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(f"{settings.kbo_api_base_url}/enterprises/{enterprise_number}", headers=headers)
            r.raise_for_status()
            return SourceRecord(source=self.name, status="ok", url=str(r.url), data=r.json())
