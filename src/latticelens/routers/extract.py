from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from latticelens.db import get_db
from latticelens.schemas import ExtractionRequest, ExtractionResponse
from latticelens.services.extract_service import extract_facts

router = APIRouter(tags=["extract"])


@router.post("/extract", response_model=ExtractionResponse)
async def extract(request: ExtractionRequest, db: AsyncSession = Depends(get_db)):
    try:
        return await extract_facts(db, request)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Extraction failed: {str(e)}")
