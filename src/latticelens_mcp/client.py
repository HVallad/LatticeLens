"""HTTP client wrapper for the LatticeLens API (per ADR-19).

Thin wrapper around httpx — all business logic stays in the API server.
"""

import httpx


class LatticeLensClient:
    """Async HTTP client for LatticeLens API endpoints."""

    def __init__(self, api_url: str, timeout: float = 30.0):
        self.api_url = api_url.rstrip("/")
        self.timeout = timeout

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=self.timeout)

    async def health(self) -> dict:
        async with self._client() as client:
            resp = await client.get(f"{self.api_url}/health")
            resp.raise_for_status()
            return resp.json()

    async def get_fact(self, code: str) -> dict:
        async with self._client() as client:
            resp = await client.get(f"{self.api_url}/facts/{code}")
            if resp.status_code == 404:
                return {"error": f"Fact '{code}' not found"}
            resp.raise_for_status()
            return resp.json()

    async def query_facts(self, query: dict) -> dict:
        async with self._client() as client:
            resp = await client.post(f"{self.api_url}/facts/query", json=query)
            resp.raise_for_status()
            return resp.json()

    async def create_fact(self, payload: dict) -> dict:
        async with self._client() as client:
            resp = await client.post(f"{self.api_url}/facts", json=payload)
            if resp.status_code == 409:
                return {"error": "conflict", "detail": resp.json().get("detail", "Code conflict")}
            if resp.status_code == 422:
                return {"error": "validation", "detail": resp.json().get("detail", "Validation error")}
            resp.raise_for_status()
            return resp.json()

    async def update_fact(self, code: str, payload: dict) -> dict:
        async with self._client() as client:
            resp = await client.patch(f"{self.api_url}/facts/{code}", json=payload)
            if resp.status_code == 404:
                return {"error": f"Fact '{code}' not found"}
            if resp.status_code == 422:
                return {"error": "validation", "detail": resp.json().get("detail", "Validation error")}
            resp.raise_for_status()
            return resp.json()

    async def deprecate_fact(self, code: str) -> dict:
        async with self._client() as client:
            resp = await client.delete(f"{self.api_url}/facts/{code}")
            if resp.status_code == 404:
                return {"error": f"Fact '{code}' not found"}
            resp.raise_for_status()
            return resp.json()

    async def get_fact_history(self, code: str) -> dict | list:
        async with self._client() as client:
            resp = await client.get(f"{self.api_url}/facts/{code}/history")
            if resp.status_code == 404:
                return {"error": f"Fact '{code}' not found"}
            resp.raise_for_status()
            return resp.json()

    async def bulk_create(self, facts: list) -> dict | list:
        async with self._client() as client:
            resp = await client.post(f"{self.api_url}/facts/bulk", json=facts)
            if resp.status_code == 422:
                return {"error": "validation", "detail": resp.json().get("detail", "Validation error")}
            resp.raise_for_status()
            return resp.json()

    async def get_impact(self, code: str) -> dict:
        async with self._client() as client:
            resp = await client.get(f"{self.api_url}/graph/{code}/impact")
            if resp.status_code == 404:
                return {"error": f"Fact '{code}' not found"}
            resp.raise_for_status()
            return resp.json()

    async def get_refs(self, code: str) -> dict:
        async with self._client() as client:
            resp = await client.get(f"{self.api_url}/graph/{code}/refs")
            if resp.status_code == 404:
                return {"error": f"Fact '{code}' not found"}
            resp.raise_for_status()
            return resp.json()

    async def get_orphans(self) -> list:
        async with self._client() as client:
            resp = await client.get(f"{self.api_url}/graph/orphans")
            resp.raise_for_status()
            return resp.json()

    async def get_contradictions(self) -> list:
        async with self._client() as client:
            resp = await client.get(f"{self.api_url}/graph/contradictions")
            resp.raise_for_status()
            return resp.json()

    async def extract(self, payload: dict) -> dict:
        async with self._client() as client:
            resp = await client.post(f"{self.api_url}/extract", json=payload, timeout=120.0)
            resp.raise_for_status()
            return resp.json()
