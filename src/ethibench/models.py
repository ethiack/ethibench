"""Data models for ethibench evaluation pipeline."""

from typing import Literal

from pydantic import BaseModel, Field


class Finding(BaseModel):
    """A vulnerability finding from a security testing tool."""

    title: str
    url: str = ""
    description: str = ""
    cwe: str | int | None = None
    severity: str | None = None
    score: float | None = None
    cvss_vector: str | None = None
    confidence_level: str | None = None
    cve: str | None = None
    module: str | None = None
    mitigation: str | None = None
    impact: str | None = None
    evidence: str | None = None
    steps: str | list[str] | None = None
    metadata: dict | None = None

    # Added during parsing
    uuid: str | None = None
    target_id: str | None = None
    subset_name: str | None = None


class GroundTruth(BaseModel):
    """A ground truth vulnerability entry."""

    id: str
    name: str
    subset_name: str
    target_id: str
    category: str = ""
    description: str = ""
    additional_info: str = ""
    difficulty: str = ""
    cvss: float | None = None


class EvaluationResult(BaseModel):
    """Metrics for a single subset evaluation."""

    true_positives: int = 0
    false_positives: int = 0
    false_negatives: int = 0
    duplicates: int = 0
    precision: float = 0.0
    recall: float = 0.0
    f1_score: float = 0.0
    f05_score: float = 0.0
    severity_score: int = 0
    subset_name: str = ""


class VulnerabilityMatch(BaseModel):
    """LLM structured output for vulnerability comparison."""

    is_match: Literal["YES", "NO"] = Field(
        description="Whether the finding and ground truth describe the same vulnerability"
    )
