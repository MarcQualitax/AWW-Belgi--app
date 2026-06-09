from app.models import Finding, RiskLevel, SourceRecord


def score_sources(sources: list[SourceRecord]) -> tuple[int, RiskLevel, list[Finding], list[str]]:
    score = 20
    findings: list[Finding] = []
    missing: list[str] = []

    for src in sources:
        if src.status != "ok":
            missing.append(f"{src.source}: {', '.join(src.warnings) or src.status}")
            score += 5
            continue

        text = str(src.data).lower()
        red_flags = ["faillissement", "fraude", "sanctie", "witwassen", "ambtshalve doorhaling", "liquidatie"]
        for flag in red_flags:
            if flag in text:
                score += 15
                findings.append(Finding(
                    category="red_flag",
                    severity=RiskLevel.high,
                    title=f"Mogelijke indicator: {flag}",
                    evidence=f"Term gevonden in gegevens van {src.source}.",
                    source=src.source,
                ))

    if not any(s.source.startswith("KBO") and s.status == "ok" for s in sources):
        findings.append(Finding(
            category="identificatie",
            severity=RiskLevel.manual_review,
            title="Identiteit niet volledig geverifieerd via KBO",
            evidence="KBO-connector is niet geconfigureerd of gaf geen bruikbaar resultaat.",
            source="KBO",
        ))

    score = max(0, min(100, score))
    if score >= 70:
        level = RiskLevel.high
    elif score >= 40:
        level = RiskLevel.medium
    else:
        level = RiskLevel.low
    if missing:
        level = RiskLevel.manual_review
    return score, level, findings, missing
