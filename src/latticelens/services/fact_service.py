import math
from datetime import date, datetime, timezone

from sqlalchemy import bindparam, case, cast, delete, func, literal, select, text, type_coerce
from sqlalchemy.dialects.postgresql import ARRAY, TEXT
from sqlalchemy.ext.asyncio import AsyncSession

from latticelens.models import Fact, FactConfidence, FactHistory, FactLayer, FactRef, FactStatus
from latticelens.schemas import (
    FactCreate,
    FactHistoryEntry,
    FactListResponse,
    FactQuery,
    FactResponse,
    FactUpdate,
)

LAYER_PREFIXES = {
    "WHY": ["ADR", "PRD", "ETH", "DES"],
    "GUARDRAILS": ["MC", "AUP", "RISK", "DG", "COMP"],
    "HOW": ["SP", "API", "RUN", "ML", "MON"],
}


def validate_code_layer(code: str, layer: str) -> bool:
    prefix = code.split("-")[0]
    return prefix in LAYER_PREFIXES.get(layer, [])


def _fact_to_response(fact: Fact, refs: list[str]) -> FactResponse:
    is_stale = False
    if fact.review_by and fact.review_by < date.today():
        is_stale = True

    return FactResponse(
        id=fact.id,
        code=fact.code,
        layer=fact.layer.value if isinstance(fact.layer, FactLayer) else fact.layer,
        type=fact.type,
        fact_text=fact.fact_text,
        tags=fact.tags,
        status=fact.status.value if isinstance(fact.status, FactStatus) else fact.status,
        confidence=fact.confidence.value if isinstance(fact.confidence, FactConfidence) else fact.confidence,
        version=fact.version,
        owner=fact.owner,
        refs=refs,
        superseded_by=fact.superseded_by,
        review_by=fact.review_by,
        created_at=fact.created_at,
        updated_at=fact.updated_at,
        is_stale=is_stale,
    )


async def _get_refs_for_fact(db: AsyncSession, code: str) -> list[str]:
    result = await db.execute(select(FactRef.to_code).where(FactRef.from_code == code))
    return [row[0] for row in result.all()]


async def create_fact(db: AsyncSession, data: FactCreate) -> FactResponse:
    if not validate_code_layer(data.code, data.layer):
        raise ValueError(f"Code prefix '{data.code.split('-')[0]}' is not valid for layer '{data.layer}'")

    existing = await db.execute(select(Fact).where(Fact.code == data.code))
    if existing.scalar_one_or_none():
        raise ValueError(f"CONFLICT:Fact with code '{data.code}' already exists")

    if data.refs:
        for ref_code in data.refs:
            ref_exists = await db.execute(select(Fact.code).where(Fact.code == ref_code))
            if not ref_exists.scalar_one_or_none():
                raise ValueError(f"BADREF:Referenced fact '{ref_code}' does not exist")

    tags = sorted([t.lower() for t in data.tags])

    fact = Fact(
        code=data.code,
        layer=FactLayer(data.layer),
        type=data.type,
        fact_text=data.fact_text,
        tags=tags,
        status=FactStatus(data.status),
        confidence=FactConfidence(data.confidence),
        owner=data.owner,
        review_by=data.review_by,
        version=1,
    )
    db.add(fact)
    await db.flush()

    for ref_code in data.refs:
        db.add(FactRef(from_code=data.code, to_code=ref_code))
    await db.flush()

    return _fact_to_response(fact, data.refs)


async def get_fact(db: AsyncSession, code: str) -> FactResponse | None:
    result = await db.execute(select(Fact).where(Fact.code == code))
    fact = result.scalar_one_or_none()
    if not fact:
        return None
    refs = await _get_refs_for_fact(db, code)
    return _fact_to_response(fact, refs)


async def update_fact(db: AsyncSession, code: str, data: FactUpdate) -> FactResponse | None:
    result = await db.execute(select(Fact).where(Fact.code == code))
    fact = result.scalar_one_or_none()
    if not fact:
        return None

    new_status = data.status or (fact.status.value if isinstance(fact.status, FactStatus) else fact.status)
    if new_status == "Superseded":
        superseded_target = data.superseded_by or fact.superseded_by
        if not superseded_target:
            raise ValueError("SUPERSEDED:Setting status to Superseded requires superseded_by to be set")
        target_exists = await db.execute(select(Fact.code).where(Fact.code == superseded_target))
        if not target_exists.scalar_one_or_none():
            raise ValueError(f"BADREF:Superseded target '{superseded_target}' does not exist")

    if data.superseded_by:
        target_exists = await db.execute(select(Fact.code).where(Fact.code == data.superseded_by))
        if not target_exists.scalar_one_or_none():
            raise ValueError(f"BADREF:Superseded target '{data.superseded_by}' does not exist")

    if data.refs is not None:
        for ref_code in data.refs:
            ref_exists = await db.execute(select(Fact.code).where(Fact.code == ref_code))
            if not ref_exists.scalar_one_or_none():
                raise ValueError(f"BADREF:Referenced fact '{ref_code}' does not exist")

    # Snapshot current state into history BEFORE applying changes
    history = FactHistory(
        code=fact.code,
        version=fact.version,
        layer=fact.layer,
        type=fact.type,
        fact_text=fact.fact_text,
        tags=fact.tags,
        status=fact.status,
        confidence=fact.confidence,
        owner=fact.owner,
        superseded_by=fact.superseded_by,
        review_by=fact.review_by,
        changed_by=data.changed_by,
        change_reason=data.change_reason,
    )
    db.add(history)

    # Apply updates
    if data.fact_text is not None:
        fact.fact_text = data.fact_text
    if data.tags is not None:
        fact.tags = sorted([t.lower() for t in data.tags])
    if data.status is not None:
        fact.status = FactStatus(data.status)
    if data.confidence is not None:
        fact.confidence = FactConfidence(data.confidence)
    if data.owner is not None:
        fact.owner = data.owner
    if data.review_by is not None:
        fact.review_by = data.review_by
    if data.superseded_by is not None:
        fact.superseded_by = data.superseded_by

    fact.version += 1
    fact.updated_at = datetime.now(timezone.utc)

    if data.refs is not None:
        await db.execute(delete(FactRef).where(FactRef.from_code == code))
        for ref_code in data.refs:
            db.add(FactRef(from_code=code, to_code=ref_code))

    await db.flush()

    refs = await _get_refs_for_fact(db, code)
    return _fact_to_response(fact, refs)


async def deprecate_fact(db: AsyncSession, code: str, changed_by: str = "system", change_reason: str = "Deprecated") -> FactResponse | None:
    result = await db.execute(select(Fact).where(Fact.code == code))
    fact = result.scalar_one_or_none()
    if not fact:
        return None

    history = FactHistory(
        code=fact.code,
        version=fact.version,
        layer=fact.layer,
        type=fact.type,
        fact_text=fact.fact_text,
        tags=fact.tags,
        status=fact.status,
        confidence=fact.confidence,
        owner=fact.owner,
        superseded_by=fact.superseded_by,
        review_by=fact.review_by,
        changed_by=changed_by,
        change_reason=change_reason,
    )
    db.add(history)

    fact.status = FactStatus.DEPRECATED
    fact.version += 1
    fact.updated_at = datetime.now(timezone.utc)
    await db.flush()

    refs = await _get_refs_for_fact(db, code)
    return _fact_to_response(fact, refs)


async def get_fact_history(db: AsyncSession, code: str) -> list[FactHistoryEntry]:
    result = await db.execute(
        select(FactHistory).where(FactHistory.code == code).order_by(FactHistory.version.desc())
    )
    rows = result.scalars().all()
    return [
        FactHistoryEntry(
            version=h.version,
            fact_text=h.fact_text,
            tags=h.tags,
            status=h.status.value if isinstance(h.status, FactStatus) else h.status,
            confidence=h.confidence.value if isinstance(h.confidence, FactConfidence) else h.confidence,
            changed_by=h.changed_by,
            changed_at=h.changed_at,
            change_reason=h.change_reason,
        )
        for h in rows
    ]


async def query_facts(db: AsyncSession, query: FactQuery) -> FactListResponse:
    stmt = select(Fact)
    count_stmt = select(func.count()).select_from(Fact)

    conditions = []

    if query.layer:
        layer_enums = [FactLayer(l) for l in query.layer]
        conditions.append(Fact.layer.in_(layer_enums))

    if query.type:
        conditions.append(Fact.type.in_(query.type))

    if query.status:
        status_enums = [FactStatus(s) for s in query.status]
        conditions.append(Fact.status.in_(status_enums))

    if query.confidence:
        conf_enums = [FactConfidence(c) for c in query.confidence]
        conditions.append(Fact.confidence.in_(conf_enums))

    if query.tags_any:
        conditions.append(
            Fact.tags.has_any(cast(query.tags_any, ARRAY(TEXT)))
        )

    if query.tags_all:
        conditions.append(
            Fact.tags.has_all(cast(query.tags_all, ARRAY(TEXT)))
        )

    if query.owner:
        conditions.append(Fact.owner == query.owner)

    if query.text_search:
        conditions.append(
            text("to_tsvector('english', fact_text) @@ plainto_tsquery('english', :search)").bindparams(
                search=query.text_search
            )
        )

    if not query.include_stale:
        conditions.append(
            (Fact.review_by.is_(None)) | (Fact.review_by >= date.today())
        )

    for cond in conditions:
        stmt = stmt.where(cond)
        count_stmt = count_stmt.where(cond)

    # Ordering: confidence DESC (Confirmed > Provisional > Assumed), then updated_at DESC
    confidence_order = case(
        (Fact.confidence == FactConfidence.CONFIRMED, literal(1)),
        (Fact.confidence == FactConfidence.PROVISIONAL, literal(2)),
        (Fact.confidence == FactConfidence.ASSUMED, literal(3)),
        else_=literal(4),
    )
    stmt = stmt.order_by(confidence_order, Fact.updated_at.desc())

    # Pagination
    offset = (query.page - 1) * query.page_size
    stmt = stmt.offset(offset).limit(query.page_size)

    total_result = await db.execute(count_stmt)
    total = total_result.scalar()

    result = await db.execute(stmt)
    facts = result.scalars().all()

    fact_responses = []
    for fact in facts:
        refs = await _get_refs_for_fact(db, fact.code)
        fact_responses.append(_fact_to_response(fact, refs))

    total_pages = math.ceil(total / query.page_size) if total > 0 else 1

    return FactListResponse(
        facts=fact_responses,
        total=total,
        page=query.page,
        page_size=query.page_size,
        total_pages=total_pages,
    )


async def bulk_create_facts(db: AsyncSession, facts_data: list[FactCreate]) -> list[FactResponse]:
    # Two-pass approach: create all facts without refs first, then add refs
    # This handles cross-references between facts in the same batch
    results = []
    saved_refs: dict[str, list[str]] = {}

    # Pass 1: Create all facts without refs
    for data in facts_data:
        saved_refs[data.code] = data.refs
        data_without_refs = data.model_copy(update={"refs": []})
        result = await create_fact(db, data_without_refs)
        results.append(result)

    # Pass 2: Add refs now that all facts exist
    for data in facts_data:
        refs = saved_refs.get(data.code, [])
        if refs:
            # Validate refs exist
            for ref_code in refs:
                ref_exists = await db.execute(select(Fact.code).where(Fact.code == ref_code))
                if not ref_exists.scalar_one_or_none():
                    raise ValueError(f"BADREF:Referenced fact '{ref_code}' does not exist")
            for ref_code in refs:
                db.add(FactRef(from_code=data.code, to_code=ref_code))
            await db.flush()

    # Rebuild responses with refs
    final_results = []
    for data in facts_data:
        result = await get_fact(db, data.code)
        final_results.append(result)

    return final_results


async def get_fact_counts(db: AsyncSession) -> dict:
    total = await db.execute(select(func.count()).select_from(Fact))
    active = await db.execute(select(func.count()).select_from(Fact).where(Fact.status == FactStatus.ACTIVE))
    stale = await db.execute(
        select(func.count())
        .select_from(Fact)
        .where(Fact.review_by.isnot(None), Fact.review_by < date.today(), Fact.status == FactStatus.ACTIVE)
    )
    return {
        "total": total.scalar(),
        "active": active.scalar(),
        "stale": stale.scalar(),
    }
