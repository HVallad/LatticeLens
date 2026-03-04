import json
from pathlib import Path

import anthropic
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from latticelens.settings import settings
from latticelens.models import Fact
from latticelens.schemas import ExtractionCandidate, ExtractionRequest, ExtractionResponse

LAYER_PREFIXES = {
    "WHY": ["ADR", "PRD", "ETH", "DES"],
    "GUARDRAILS": ["MC", "AUP", "RISK", "DG", "COMP"],
    "HOW": ["SP", "API", "RUN", "ML", "MON"],
}

# Default prefix per layer for code suggestion
DEFAULT_LAYER_PREFIX = {
    "WHY": "ADR",
    "GUARDRAILS": "RISK",
    "HOW": "SP",
}


def _load_system_prompt() -> str:
    prompt_path = Path(__file__).parent.parent / "prompts" / "extract.txt"
    with open(prompt_path) as f:
        return f.read()


async def _get_next_code(db: AsyncSession, prefix: str) -> str:
    """Find the next available sequence number for a given prefix."""
    result = await db.execute(
        select(Fact.code).where(Fact.code.like(f"{prefix}-%")).order_by(Fact.code.desc())
    )
    existing = result.scalars().all()

    if not existing:
        return f"{prefix}-01"

    max_seq = 0
    for code in existing:
        try:
            seq = int(code.split("-")[1])
            max_seq = max(max_seq, seq)
        except (IndexError, ValueError):
            continue

    return f"{prefix}-{max_seq + 1:02d}"


def _infer_prefix(layer: str, fact_type: str) -> str:
    """Infer the best code prefix from layer and type."""
    type_lower = fact_type.lower()

    prefix_map = {
        "architecture decision": "ADR",
        "product requirement": "PRD",
        "ethical review": "ETH",
        "design proposal": "DES",
        "model card": "MC",
        "acceptable use": "AUP",
        "risk assessment": "RISK",
        "data governance": "DG",
        "compliance": "COMP",
        "system prompt": "SP",
        "api specification": "API",
        "runbook": "RUN",
        "mlops": "ML",
        "monitoring": "MON",
    }

    for keyword, prefix in prefix_map.items():
        if keyword in type_lower:
            if prefix in LAYER_PREFIXES.get(layer, []):
                return prefix

    return DEFAULT_LAYER_PREFIX.get(layer, "ADR")


async def extract_facts(db: AsyncSession, request: ExtractionRequest) -> ExtractionResponse:
    if not settings.anthropic_api_key:
        raise ValueError("ANTHROPIC_API_KEY not configured. Set LATTICELENS_ANTHROPIC_API_KEY environment variable.")

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    system_prompt = _load_system_prompt()

    response = client.messages.create(
        model=settings.extraction_model,
        max_tokens=4096,
        system=system_prompt,
        messages=[
            {
                "role": "user",
                "content": f"Source document: {request.source_name}\nDefault layer: {request.default_layer}\n\n---\n\n{request.content}",
            }
        ],
    )

    response_text = response.content[0].text

    try:
        raw_candidates = json.loads(response_text)
    except json.JSONDecodeError:
        # Try to extract JSON from markdown code blocks
        if "```json" in response_text:
            json_str = response_text.split("```json")[1].split("```")[0].strip()
            raw_candidates = json.loads(json_str)
        elif "```" in response_text:
            json_str = response_text.split("```")[1].split("```")[0].strip()
            raw_candidates = json.loads(json_str)
        else:
            raise ValueError(f"Failed to parse LLM response as JSON: {response_text[:200]}")

    candidates = []
    for raw in raw_candidates:
        layer = raw.get("layer", request.default_layer)
        fact_type = raw.get("type", "Unknown")
        prefix = _infer_prefix(layer, fact_type)
        suggested_code = await _get_next_code(db, prefix)

        tags = raw.get("tags", [])
        if len(tags) < 2:
            tags = tags + ["extracted", "needs-review"][: 2 - len(tags)]
        tags = sorted([t.lower().replace(" ", "-") for t in tags])

        candidates.append(
            ExtractionCandidate(
                suggested_code=suggested_code,
                layer=layer,
                type=fact_type,
                fact_text=raw.get("fact_text", ""),
                tags=tags,
                confidence="Provisional",
                refs=raw.get("refs", []),
            )
        )

    return ExtractionResponse(
        candidates=candidates,
        source_name=request.source_name,
        model_used=settings.extraction_model,
    )
