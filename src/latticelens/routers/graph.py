from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from latticelens.db import get_db
from latticelens.schemas import ContradictionCandidate, ImpactAnalysisResponse, RefsResponse
from latticelens.services import fact_service, graph_service

router = APIRouter(prefix="/graph", tags=["graph"])


@router.get("/{code}/impact", response_model=ImpactAnalysisResponse)
async def get_impact(code: str, db: AsyncSession = Depends(get_db)):
    fact = await fact_service.get_fact(db, code)
    if not fact:
        raise HTTPException(status_code=404, detail=f"Fact '{code}' not found")
    return await graph_service.get_impact(db, code)


@router.get("/{code}/refs", response_model=RefsResponse)
async def get_refs(code: str, db: AsyncSession = Depends(get_db)):
    fact = await fact_service.get_fact(db, code)
    if not fact:
        raise HTTPException(status_code=404, detail=f"Fact '{code}' not found")
    return await graph_service.get_refs(db, code)


@router.get("/orphans", response_model=list[str])
async def get_orphans(db: AsyncSession = Depends(get_db)):
    return await graph_service.get_orphans(db)


@router.get("/contradictions", response_model=list[ContradictionCandidate])
async def get_contradictions(db: AsyncSession = Depends(get_db)):
    return await graph_service.get_contradictions(db)
