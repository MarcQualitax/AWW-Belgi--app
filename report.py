from openai import AsyncOpenAI
from app.config import settings
from app.models import KycReport, SourceRecord
from app.services.risk import score_sources


def deterministic_report(enterprise_number: str, sources: list[SourceRecord], purpose: str) -> KycReport:
    score, level, findings, missing = score_sources(sources)
    source_lines = "\n".join([f"- {s.source}: {s.status}; url={s.url or 'n.v.t.'}; waarschuwingen={'; '.join(s.warnings)}" for s in sources])
    finding_lines = "\n".join([f"- [{f.severity}] {f.title}: {f.evidence} ({f.source})" for f in findings]) or "- Geen automatische rode vlaggen vastgesteld in de beschikbare data."
    missing_lines = "\n".join([f"- {m}" for m in missing]) or "- Geen ontbrekende kerninformatie vastgesteld door de automatische controle."

    md = f"""# AWW/KYC/MKS-rapport

## Scope
Doel: {purpose}
Ondernemingsnummer: {enterprise_number}

## Samenvatting
Automatische risicoscore: {score}/100
Risiconiveau: {level}
Menselijke review vereist: ja

## Geraadpleegde bronnen
{source_lines}

## Bevindingen
{finding_lines}

## Ontbrekende informatie en manuele acties
{missing_lines}

## Aanbevolen AWW/KYC-controles
1. Identificeer en verifieer de onderneming via KBO.
2. Verifieer bestuurders, wettelijke vertegenwoordigers en UBO's via toegestane bronnen.
3. Controleer jaarrekeningen, continuïteit, faillissement/liquidatie en publicaties in het Belgisch Staatsblad.
4. Voer sanctie-, PEP- en adverse-media-screening uit via een daarvoor gelicentieerde bron.
5. Leg doel en aard van de relatie vast.
6. Documenteer herkomst van middelen waar relevant.
7. Bewaar bronbewijzen, tijdstippen, beslissingsregels en reviewer.

## Beslissing
Dit rapport is een AI-ondersteunde risicoanalyse. Neem geen finale onboarding- of weigeringbeslissing zonder compliance-review.
"""
    return KycReport(
        enterprise_number=enterprise_number,
        risk_level=level,
        risk_score=score,
        sources=sources,
        findings=findings,
        missing_information=missing,
        report_markdown=md,
        human_review_required=True,
    )


async def ai_enhance_report(report: KycReport) -> KycReport:
    if not settings.openai_api_key:
        return report

    client = AsyncOpenAI(api_key=settings.openai_api_key)
    prompt = {
        "enterprise_number": report.enterprise_number,
        "risk_score": report.risk_score,
        "risk_level": report.risk_level,
        "sources": [s.model_dump(mode="json") for s in report.sources],
        "findings": [f.model_dump(mode="json") for f in report.findings],
        "missing_information": report.missing_information,
    }
    system = (
        "Je bent een Belgische AML/KYC compliance-assistent. Schrijf in het Nederlands. "
        "Maak een uitgebreid maar voorzichtig rapport met bronverwijzingen per bevinding. "
        "Verzin geen feiten. Markeer ontbrekende data en vereis menselijke review. "
        "Geef geen juridisch bindend advies."
    )
    response = await client.chat.completions.create(
        model=settings.openai_model,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": str(prompt)}],
        temperature=0.1,
    )
    report.report_markdown = response.choices[0].message.content or report.report_markdown
    return report
