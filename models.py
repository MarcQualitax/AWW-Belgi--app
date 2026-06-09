from datetime import datetime, timezone
from enum import Enum
from pydantic import BaseModel, Field, field_validator
import re


class RiskLevel(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"
    manual_review = "manual_review"


class ReportRequest(BaseModel):
    enterprise_number: str = Field(..., examples=["0123.456.789"])
    purpose: str = "KYC/AWW onboarding"
    language: str = "nl"

    @field_validator("enterprise_number")
    @classmethod
    def validate_belgian_enterprise_number(cls, value: str) -> str:
        digits = re.sub(r"\D", "", value)
        if len(digits) != 10:
            raise ValueError("Een Belgisch ondernemingsnummer moet 10 cijfers bevatten.")
        base = int(digits[:8])
        check = int(digits[8:])
        expected = 97 - (base % 97)
        if expected == 0:
            expected = 97
        if check != expected:
            raise ValueError("Ongeldig controlegetal voor Belgisch ondernemingsnummer.")
        return digits


class SourceRecord(BaseModel):
    source: str
    status: str
    url: str | None = None
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    data: dict = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class Finding(BaseModel):
    category: str
    severity: RiskLevel
    title: str
    evidence: str
    source: str


class KycReport(BaseModel):
    enterprise_number: str
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    risk_level: RiskLevel
    risk_score: int = Field(ge=0, le=100)
    sources: list[SourceRecord]
    findings: list[Finding]
    missing_information: list[str]
    report_markdown: str
    human_review_required: bool = True
