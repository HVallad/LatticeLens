from contextlib import asynccontextmanager

from fastapi import FastAPI

from latticelens.db import engine
from latticelens.routers import extract, facts, graph, health


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await engine.dispose()


app = FastAPI(
    title="LatticeLens",
    description="Knowledge governance layer for AI agent systems",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(health.router, prefix="/api/v1")
app.include_router(facts.router, prefix="/api/v1")
app.include_router(graph.router, prefix="/api/v1")
app.include_router(extract.router, prefix="/api/v1")


@app.get("/")
async def root():
    return {"message": "LatticeLens API", "docs": "/docs"}
