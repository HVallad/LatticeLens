"""Semantic embedding and similarity search for lattice facts."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lattice_lens.models import Fact

try:
    import numpy as np
    from sentence_transformers import SentenceTransformer

    HAS_SENTENCE_TRANSFORMERS = True
except ImportError:
    HAS_SENTENCE_TRANSFORMERS = False
    np = None  # type: ignore[assignment]
    SentenceTransformer = None  # type: ignore[assignment,misc]

try:
    import faiss

    HAS_FAISS = True
except ImportError:
    HAS_FAISS = False

EMBEDDINGS_FILE = "embeddings.json"
DEFAULT_MODEL = "all-MiniLM-L6-v2"
DEFAULT_TOP_K = 10
DEFAULT_THRESHOLD = 0.3


def _fact_text(fact: Fact) -> str:
    """Build the text to embed for a fact: title + body."""
    # 'type' serves as the title/category, 'fact' is the body
    return f"{fact.type}. {fact.fact}"


def _fact_checksum(fact: Fact) -> str:
    """Compute a content checksum for staleness detection."""
    content = f"{fact.type}|{fact.fact}|{fact.version}"
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def _cosine_similarity(query_vec: "np.ndarray", matrix: "np.ndarray") -> "np.ndarray":
    """Compute cosine similarity between a query vector and a matrix of vectors."""
    # Normalize
    query_norm = query_vec / (np.linalg.norm(query_vec) + 1e-10)
    norms = np.linalg.norm(matrix, axis=1, keepdims=True) + 1e-10
    matrix_norm = matrix / norms
    return matrix_norm @ query_norm


class EmbeddingIndex:
    """Manages fact embeddings and similarity search."""

    def __init__(self, model_name: str = DEFAULT_MODEL):
        if not HAS_SENTENCE_TRANSFORMERS:
            raise ImportError(
                "sentence-transformers is required for semantic search. "
                "Install with: pip install lattice-lens[semantic]"
            )
        self._model_name = model_name
        self._model: SentenceTransformer | None = None
        self._embeddings: np.ndarray | None = None
        self._fact_codes: list[str] = []
        self._checksums: dict[str, str] = {}
        self._built_at: str | None = None
        self._faiss_index = None

    @property
    def model(self) -> SentenceTransformer:
        if self._model is None:
            self._model = SentenceTransformer(self._model_name)
        return self._model

    @property
    def fact_codes(self) -> list[str]:
        return list(self._fact_codes)

    @property
    def fact_count(self) -> int:
        return len(self._fact_codes)

    def build_index(self, facts: list[Fact]) -> None:
        """Embed all facts and build the search index."""
        if not facts:
            self._embeddings = np.zeros((0, 0))
            self._fact_codes = []
            self._checksums = {}
            self._built_at = datetime.now(timezone.utc).isoformat()
            return

        texts = [_fact_text(f) for f in facts]
        embeddings = self.model.encode(texts, show_progress_bar=False)
        self._embeddings = np.array(embeddings, dtype=np.float32)
        self._fact_codes = [f.code for f in facts]
        self._checksums = {f.code: _fact_checksum(f) for f in facts}
        self._built_at = datetime.now(timezone.utc).isoformat()

        # Build FAISS index if available
        self._faiss_index = None
        if HAS_FAISS and len(facts) > 0:
            dim = self._embeddings.shape[1]
            self._faiss_index = faiss.IndexFlatIP(dim)
            # Normalize for cosine similarity via inner product
            norms = np.linalg.norm(self._embeddings, axis=1, keepdims=True) + 1e-10
            normalized = self._embeddings / norms
            self._faiss_index.add(normalized)

    def search(
        self,
        query: str,
        top_k: int = DEFAULT_TOP_K,
        threshold: float = DEFAULT_THRESHOLD,
    ) -> list[tuple[str, float]]:
        """Semantic search: find facts similar to query.

        Returns list of (fact_code, similarity_score) tuples, sorted by score descending.
        """
        if self._embeddings is None or len(self._fact_codes) == 0:
            return []

        query_embedding = self.model.encode([query], show_progress_bar=False)
        query_vec = np.array(query_embedding, dtype=np.float32)[0]

        if self._faiss_index is not None:
            # FAISS path — normalized inner product = cosine similarity
            query_norm = query_vec / (np.linalg.norm(query_vec) + 1e-10)
            scores, indices = self._faiss_index.search(
                query_norm.reshape(1, -1), min(top_k, len(self._fact_codes))
            )
            results = []
            for score, idx in zip(scores[0], indices[0]):
                if idx < 0:
                    continue
                if score >= threshold:
                    results.append((self._fact_codes[idx], float(score)))
            return results
        else:
            # NumPy fallback
            scores = _cosine_similarity(query_vec, self._embeddings)
            ranked_indices = np.argsort(scores)[::-1][:top_k]
            results = []
            for idx in ranked_indices:
                score = float(scores[idx])
                if score >= threshold:
                    results.append((self._fact_codes[idx], score))
            return results

    def save(self, path: str | Path) -> None:
        """Save embeddings to .lattice/embeddings.json."""
        if self._embeddings is None:
            return

        data = {
            "model": self._model_name,
            "built_at": self._built_at,
            "fact_count": len(self._fact_codes),
            "fact_codes": self._fact_codes,
            "checksums": self._checksums,
            "embeddings": {
                code: emb.tolist() for code, emb in zip(self._fact_codes, self._embeddings)
            },
        }

        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(data, f)

    def load(self, path: str | Path) -> bool:
        """Load saved embeddings. Returns False if missing or corrupt."""
        path = Path(path)
        if not path.exists():
            return False

        try:
            with open(path) as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            return False

        if data.get("model") != self._model_name:
            return False

        fact_codes = data.get("fact_codes", [])
        embeddings_dict = data.get("embeddings", {})

        if not fact_codes or not embeddings_dict:
            return False

        # Reconstruct numpy matrix in code order
        try:
            matrix = np.array([embeddings_dict[code] for code in fact_codes], dtype=np.float32)
        except (KeyError, ValueError):
            return False

        self._fact_codes = fact_codes
        self._checksums = data.get("checksums", {})
        self._built_at = data.get("built_at")
        self._embeddings = matrix

        # Rebuild FAISS index if available
        self._faiss_index = None
        if HAS_FAISS and len(self._fact_codes) > 0:
            dim = self._embeddings.shape[1]
            self._faiss_index = faiss.IndexFlatIP(dim)
            norms = np.linalg.norm(self._embeddings, axis=1, keepdims=True) + 1e-10
            normalized = self._embeddings / norms
            self._faiss_index.add(normalized)

        return True

    def is_stale(self, facts: list[Fact]) -> bool:
        """Check if index needs rebuilding (new/changed facts)."""
        if self._embeddings is None:
            return True

        current_codes = {f.code for f in facts}
        indexed_codes = set(self._fact_codes)

        # New or removed facts
        if current_codes != indexed_codes:
            return True

        # Changed content
        for fact in facts:
            stored = self._checksums.get(fact.code)
            if stored is None or stored != _fact_checksum(fact):
                return True

        return False


def semantic_search(
    facts: list[Fact],
    query: str,
    lattice_root: Path | None = None,
    model_name: str = DEFAULT_MODEL,
    top_k: int = DEFAULT_TOP_K,
    threshold: float = DEFAULT_THRESHOLD,
    force_rebuild: bool = False,
    tag: str | None = None,
    layer: str | None = None,
    status: str | None = None,
    project: str | None = None,
) -> list[dict]:
    """High-level semantic search function.

    Loads or builds the embedding index, searches, applies post-filters,
    and returns enriched results.
    """
    if not HAS_SENTENCE_TRANSFORMERS:
        raise ImportError(
            "sentence-transformers is required for semantic search. "
            "Install with: pip install lattice-lens[semantic]"
        )

    index = EmbeddingIndex(model_name=model_name)

    # Try loading cached embeddings
    embeddings_path = lattice_root / EMBEDDINGS_FILE if lattice_root else None
    loaded = False
    if embeddings_path and not force_rebuild:
        loaded = index.load(embeddings_path)

    # Rebuild if stale or not loaded
    if not loaded or force_rebuild or index.is_stale(facts):
        index.build_index(facts)
        if embeddings_path:
            index.save(embeddings_path)

    # Search
    raw_results = index.search(query, top_k=top_k * 3, threshold=threshold)

    # Build fact lookup
    fact_map = {f.code: f for f in facts}

    # Apply post-filters and enrich
    results = []
    for code, score in raw_results:
        fact = fact_map.get(code)
        if fact is None:
            continue

        if tag and tag.lower() not in fact.tags:
            continue
        if layer and fact.layer.value != layer:
            continue
        if status and fact.status.value != status:
            continue
        if project and project.lower() not in [p.lower() for p in fact.projects]:
            continue

        # Snippet: first 150 chars of fact text
        snippet = fact.fact[:150]
        if len(fact.fact) > 150:
            snippet += "..."

        results.append(
            {
                "code": fact.code,
                "type": fact.type,
                "score": round(score, 4),
                "layer": fact.layer.value,
                "status": fact.status.value,
                "tags": fact.tags,
                "projects": fact.projects,
                "snippet": snippet,
            }
        )

        if len(results) >= top_k:
            break

    return results
