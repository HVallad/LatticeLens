from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from latticelens import __version__
from latticelens.db import get_db
from latticelens.schemas import HealthResponse
from latticelens.services.fact_service import get_fact_counts

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health_check(db: AsyncSession = Depends(get_db)):
    counts = await get_fact_counts(db)
    return HealthResponse(
        status="healthy",
        version=__version__,
        facts_total=counts["total"],
        facts_active=counts["active"],
        facts_stale=counts["stale"],
    )
