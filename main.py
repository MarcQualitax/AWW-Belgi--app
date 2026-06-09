import asyncio
from fastapi import FastAPI
from app.connectors.kbo import KboConnector
from app.connectors.nbb import NbbConnector
from app.connectors.search import GoogleSearchConnector
from app.connectors.graydon import GraydonConnector
from app.models import KycReport, ReportRequest
from app.services.report import ai_enhance_report, deterministic_report

app = FastAPI(title="KYC AI Reporter België", version="0.1.0")

CONNECTORS = [KboConnector(), NbbConnector(), GoogleSearchConnector(), GraydonConnector()]


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.post("/reports", response_model=KycReport)
async def create_report(request: ReportRequest) -> KycReport:
    results = await asyncio.gather(
        *[connector.fetch(request.enterprise_number) for connector in CONNECTORS],
        return_exceptions=True,
    )
    sources = []
    for connector, result in zip(CONNECTORS, results):
        if isinstance(result, Exception):
            from app.models import SourceRecord
            sources.append(SourceRecord(source=connector.name, status="error", warnings=[str(result)]))
        else:
            sources.append(result)

    report = deterministic_report(request.enterprise_number, sources, request.purpose)
    return await ai_enhance_report(report)
