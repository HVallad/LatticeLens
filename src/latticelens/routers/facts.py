from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from latticelens.db import get_db
from latticelens.schemas import (
    FactCreate,
    FactHistoryEntry,
    FactListResponse,
    FactQuery,
    FactResponse,
    FactUpdate,
)
from latticelens.services import fact_service

router = APIRouter(prefix="/facts", tags=["facts"])


@router.post("", response_model=FactResponse, status_code=201)
async def create_fact(data: FactCreate, db: AsyncSession = Depends(get_db)):
    try:
        return await fact_service.create_fact(db, data)
    except ValueError as e:
        msg = str(e)
        if msg.startswith("CONFLICT:"):
            raise HTTPException(status_code=409, detail=msg.split(":", 1)[1])
        elif msg.startswith("BADREF:"):
            raise HTTPException(status_code=400, detail=msg.split(":", 1)[1])
        else:
            raise HTTPException(status_code=422, detail=msg)


@router.get("/{code}", response_model=FactResponse)
async def get_fact(code: str, db: AsyncSession = Depends(get_db)):
    result = await fact_service.get_fact(db, code)
    if not result:
        raise HTTPException(status_code=404, detail=f"Fact '{code}' not found")
    return result


@router.patch("/{code}", response_model=FactResponse)
async def update_fact(code: str, data: FactUpdate, db: AsyncSession = Depends(get_db)):
    try:
        result = await fact_service.update_fact(db, code, data)
    except ValueError as e:
        msg = str(e)
        if msg.startswith("SUPERSEDED:"):
            raise HTTPException(status_code=400, detail=msg.split(":", 1)[1])
        elif msg.startswith("BADREF:"):
            raise HTTPException(status_code=400, detail=msg.split(":", 1)[1])
        else:
            raise HTTPException(status_code=422, detail=msg)
    if not result:
        raise HTTPException(status_code=404, detail=f"Fact '{code}' not found")
    return result


@router.delete("/{code}", response_model=FactResponse)
async def deprecate_fact(code: str, db: AsyncSession = Depends(get_db)):
    result = await fact_service.deprecate_fact(db, code)
    if not result:
        raise HTTPException(status_code=404, detail=f"Fact '{code}' not found")
    return result


@router.get("/{code}/history", response_model=list[FactHistoryEntry])
async def get_fact_history(code: str, db: AsyncSession = Depends(get_db)):
    # Verify fact exists
    fact = await fact_service.get_fact(db, code)
    if not fact:
        raise HTTPException(status_code=404, detail=f"Fact '{code}' not found")
    return await fact_service.get_fact_history(db, code)


@router.post("/query", response_model=FactListResponse)
async def query_facts(query: FactQuery, db: AsyncSession = Depends(get_db)):
    return await fact_service.query_facts(db, query)


@router.post("/bulk", response_model=list[FactResponse], status_code=201)
async def bulk_create_facts(facts: list[FactCreate], db: AsyncSession = Depends(get_db)):
    try:
        return await fact_service.bulk_create_facts(db, facts)
    except ValueError as e:
        msg = str(e)
        if msg.startswith("CONFLICT:"):
            raise HTTPException(status_code=409, detail=msg.split(":", 1)[1])
        elif msg.startswith("BADREF:"):
            raise HTTPException(status_code=400, detail=msg.split(":", 1)[1])
        else:
            raise HTTPException(status_code=422, detail=msg)
