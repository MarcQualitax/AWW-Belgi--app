import httpx
from app.config import settings
from app.connectors.base import Connector
from app.models import SourceRecord


class GoogleSearchConnector(Connector):
    name = "Google Custom Search / open internet"

    async def fetch(self, enterprise_number: str) -> SourceRecord:
        if not settings.google_custom_search_key or not settings.google_custom_search_cx:
            return SourceRecord(
                source=self.name,
                status="not_configured",
                warnings=["Gebruik Google Custom Search API of een andere toegestane zoek-API; scrape geen zoekresultaten."],
                data={"queries": [enterprise_number, f'"{enterprise_number}" fraude faillissement sancties witwassen']},
            )
        params = {
            "key": settings.google_custom_search_key,
            "cx": settings.google_custom_search_cx,
            "q": f'"{enterprise_number}" OR "BE{enterprise_number}"',
            "num": 10,
        }
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get("https://www.googleapis.com/customsearch/v1", params=params)
            r.raise_for_status()
            return SourceRecord(source=self.name, status="ok", url=str(r.url), data=r.json())
