"""Convert a free-form security report (Markdown) to structured findings JSONL."""

import json
from pathlib import Path
from typing import List

from loguru import logger
from pydantic import BaseModel, Field

from ethibench.config import get_api_url, get_llm_model, get_llm_provider, get_temperature
from ethibench.llm import get_model


class ExtractedFinding(BaseModel):
    """A single vulnerability extracted from a report."""

    title: str = Field(description="Short vulnerability name")
    url: str = Field(default="", description="Affected URL or endpoint")
    description: str = Field(default="", description="Vulnerability description")
    cwe: str = Field(default="", description="CWE identifier if mentioned")
    severity: str = Field(default="", description="Severity level if mentioned")
    steps: list[str] = Field(default_factory=list, description="Steps to reproduce")


class ExtractedFindings(BaseModel):
    """List of findings extracted from a report."""

    findings: List[ExtractedFinding]


EXTRACT_PROMPT = """You are a security report parser. Extract all individual vulnerability findings from the following security report.

For each vulnerability, extract:
- title: a short, descriptive name for the vulnerability
- url: the affected URL or endpoint (if mentioned)
- description: a detailed description of the vulnerability
- cwe: the CWE identifier (if mentioned)
- severity: the severity level (if mentioned)
- steps: steps to reproduce (if described)

Be thorough — extract every distinct vulnerability mentioned in the report. Do not merge different vulnerabilities into one finding, even if they are related.

REPORT:
{report_content}
"""


def convert_report_to_findings(
    report_path: str | Path, output_path: str | Path | None = None
) -> Path:
    """Convert a Markdown report to a findings JSONL file.

    Args:
        report_path: Path to the report file (Markdown or plain text).
        output_path: Where to write findings.jsonl. Defaults to findings.jsonl
                     in the same directory as the report.

    Returns:
        Path to the generated findings.jsonl file.
    """
    report_path = Path(report_path)
    if output_path is None:
        output_path = report_path.parent / "findings.jsonl"
    else:
        output_path = Path(output_path)

    report_content = report_path.read_text()

    llm = get_model(
        model_name=get_llm_model(),
        provider=get_llm_provider(),
        api_url=get_api_url(),
        temperature=get_temperature(),
    )
    structured_llm = llm.with_structured_output(ExtractedFindings)

    logger.info(f"Extracting findings from {report_path}…")
    prompt = EXTRACT_PROMPT.format(report_content=report_content)
    result = structured_llm.invoke(prompt)

    with open(output_path, "w") as f:
        for finding in result.findings:
            f.write(finding.model_dump_json() + "\n")

    logger.info(f"Extracted {len(result.findings)} findings → {output_path}")
    return output_path
