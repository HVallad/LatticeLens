"""SqliteStore — SQLite-backed LatticeStore implementation for Tier 2 scale."""

from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime
from pathlib import Path

from lattice_lens.config import HISTORY_DIR
from lattice_lens.models import Fact, FactConfidence, FactLayer, FactStatus
from lattice_lens.services.project_service import fact_matches_project, read_project_registry
from lattice_lens.store.index import FactIndex

DB_FILE = "lattice.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS facts (
    code        TEXT PRIMARY KEY,
    layer       TEXT NOT NULL CHECK (layer IN ('WHY', 'GUARDRAILS', 'HOW')),
    type        TEXT NOT NULL,
    fact        TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'Draft',
    confidence  TEXT NOT NULL DEFAULT 'Provisional',
    version     INTEGER NOT NULL DEFAULT 1,
    owner       TEXT NOT NULL,
    review_by   TEXT,
    superseded_by TEXT,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    FOREIGN KEY (superseded_by) REFERENCES facts(code)
);

CREATE TABLE IF NOT EXISTS fact_tags (
    code TEXT NOT NULL REFERENCES facts(code) ON DELETE CASCADE,
    tag  TEXT NOT NULL,
    PRIMARY KEY (code, tag)
);

CREATE TABLE IF NOT EXISTS fact_refs (
    source_code TEXT NOT NULL REFERENCES facts(code) ON DELETE CASCADE,
    target_code TEXT NOT NULL,
    rel_type    TEXT NOT NULL DEFAULT 'relates',
    PRIMARY KEY (source_code, target_code)
);

CREATE TABLE IF NOT EXISTS changelog (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    action    TEXT NOT NULL,
    code      TEXT NOT NULL,
    reason    TEXT
);

CREATE INDEX IF NOT EXISTS idx_facts_layer ON facts(layer);
CREATE INDEX IF NOT EXISTS idx_facts_status ON facts(status);
CREATE TABLE IF NOT EXISTS fact_projects (
    code    TEXT NOT NULL REFERENCES facts(code) ON DELETE CASCADE,
    project TEXT NOT NULL,
    PRIMARY KEY (code, project)
);

CREATE INDEX IF NOT EXISTS idx_fact_tags_tag ON fact_tags(tag);
CREATE INDEX IF NOT EXISTS idx_fact_refs_target ON fact_refs(target_code);
CREATE INDEX IF NOT EXISTS idx_fact_projects_project ON fact_projects(project);
"""


class SqliteStore:
    """SQLite-backed LatticeStore implementation.

    Uses WAL mode for concurrent read access.
    Implements the same LatticeStore protocol as YamlFileStore.
    """

    def __init__(self, lattice_root: Path):
        self.root = lattice_root
        self.db_path = lattice_root / DB_FILE
        self.history_dir = lattice_root / HISTORY_DIR
        self._conn: sqlite3.Connection | None = None
        self._index: FactIndex | None = None
        self._ensure_schema()

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path))
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def _ensure_schema(self):
        """Create tables if they don't exist, and run migrations."""
        self.conn.executescript(_SCHEMA)
        self.conn.commit()
        self._migrate_schema()

    def _migrate_schema(self):
        """Run schema migrations for existing databases."""
        # Migration: add rel_type column to fact_refs if missing
        cols = {row[1] for row in self.conn.execute("PRAGMA table_info(fact_refs)").fetchall()}
        if "rel_type" not in cols:
            self.conn.execute(
                "ALTER TABLE fact_refs ADD COLUMN rel_type TEXT NOT NULL DEFAULT 'relates'"
            )
            self.conn.commit()

    @property
    def index(self) -> FactIndex:
        if self._index is None:
            idx = FactIndex()
            for fact in self._list_all_facts():
                idx._add(fact)
            self._index = idx
        return self._index

    def invalidate_index(self):
        self._index = None

    # ── LatticeStore protocol methods ──

    def get(self, code: str) -> Fact | None:
        """Single indexed lookup by primary key."""
        row = self.conn.execute("SELECT * FROM facts WHERE code = ?", (code,)).fetchone()
        if row is None:
            return None
        return self._fact_from_row(row)

    def list_facts(self, **filters) -> list[Fact]:
        """Build SQL WHERE clause from filters. Uses indexed columns."""
        # Start with all facts and apply filters in Python for consistency
        # with the YAML store's behavior
        facts = self._list_all_facts()

        # Layer filter
        layer = filters.get("layer")
        if layer:
            layers = [layer] if isinstance(layer, str) else layer
            facts = [f for f in facts if f.layer.value in layers]

        # Status filter (default: Active)
        status = filters.get("status", ["Active"])
        if status:
            statuses = [status] if isinstance(status, str) else status
            facts = [f for f in facts if f.status.value in statuses]

        # Tag filters
        tags_any = filters.get("tags_any")
        if tags_any:
            facts = [f for f in facts if set(f.tags) & set(tags_any)]

        tags_all = filters.get("tags_all")
        if tags_all:
            tag_set = set(tags_all)
            facts = [f for f in facts if tag_set.issubset(set(f.tags))]

        # Type filter
        type_filter = filters.get("type")
        if type_filter:
            types = [type_filter] if isinstance(type_filter, str) else type_filter
            facts = [f for f in facts if f.type in types]

        # Text search
        text_search = filters.get("text_search")
        if text_search:
            query = text_search.lower()
            facts = [f for f in facts if query in f.fact.lower()]

        project = filters.get("project")
        if project:
            registry = read_project_registry(self.root)
            facts = [f for f in facts if fact_matches_project(f.projects, project, registry)]

        return facts

    def create(self, fact: Fact) -> Fact:
        """INSERT fact + tags + refs in a transaction. Append to changelog."""
        if self.exists(fact.code):
            raise FileExistsError(f"Fact {fact.code} already exists")

        with self.conn:
            self.conn.execute(
                """INSERT INTO facts
                   (code, layer, type, fact, status, confidence, version,
                    owner, review_by, superseded_by, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    fact.code,
                    fact.layer.value,
                    fact.type,
                    fact.fact,
                    fact.status.value,
                    fact.confidence.value,
                    fact.version,
                    fact.owner,
                    fact.review_by.isoformat() if fact.review_by else None,
                    fact.superseded_by,
                    fact.created_at.isoformat(),
                    fact.updated_at.isoformat(),
                ),
            )
            for tag in fact.tags:
                self.conn.execute(
                    "INSERT INTO fact_tags (code, tag) VALUES (?, ?)",
                    (fact.code, tag),
                )
            for ref in fact.refs:
                self.conn.execute(
                    "INSERT INTO fact_refs (source_code, target_code, rel_type) VALUES (?, ?, ?)",
                    (fact.code, ref.code, ref.rel.value),
                )
            for project in fact.projects:
                self.conn.execute(
                    "INSERT INTO fact_projects (code, project) VALUES (?, ?)",
                    (fact.code, project),
                )
            self._append_changelog("create", fact.code, "Initial creation")

        self.invalidate_index()
        return fact

    def update(self, code: str, changes: dict, reason: str) -> Fact:
        """UPDATE within transaction. Auto-increment version, set updated_at."""
        current = self.get(code)
        if current is None:
            raise FileNotFoundError(f"Fact {code} not found")

        # Reject code changes (AUP-02)
        if "code" in changes and changes["code"] != code:
            raise ValueError("Fact code is immutable (AUP-02)")

        # Build updated fact via Pydantic for validation
        data = current.model_dump()
        data.update(changes)
        data["version"] = current.version + 1
        data["updated_at"] = datetime.now()
        updated = Fact(**data)

        with self.conn:
            self.conn.execute(
                """UPDATE facts SET
                   layer=?, type=?, fact=?, status=?, confidence=?, version=?,
                   owner=?, review_by=?, superseded_by=?, updated_at=?
                   WHERE code=?""",
                (
                    updated.layer.value,
                    updated.type,
                    updated.fact,
                    updated.status.value,
                    updated.confidence.value,
                    updated.version,
                    updated.owner,
                    updated.review_by.isoformat() if updated.review_by else None,
                    updated.superseded_by,
                    updated.updated_at.isoformat(),
                    code,
                ),
            )
            # Replace tags
            self.conn.execute("DELETE FROM fact_tags WHERE code = ?", (code,))
            for tag in updated.tags:
                self.conn.execute(
                    "INSERT INTO fact_tags (code, tag) VALUES (?, ?)",
                    (code, tag),
                )
            # Replace refs
            self.conn.execute("DELETE FROM fact_refs WHERE source_code = ?", (code,))
            for ref in updated.refs:
                self.conn.execute(
                    "INSERT INTO fact_refs (source_code, target_code, rel_type) VALUES (?, ?, ?)",
                    (code, ref.code, ref.rel.value),
                )
            # Replace projects
            self.conn.execute("DELETE FROM fact_projects WHERE code = ?", (code,))
            for project in updated.projects:
                self.conn.execute(
                    "INSERT INTO fact_projects (code, project) VALUES (?, ?)",
                    (code, project),
                )
            self._append_changelog("update", code, reason)

        self.invalidate_index()
        return updated

    def deprecate(self, code: str, reason: str) -> Fact:
        """Set status=Deprecated within transaction."""
        return self.update(code, {"status": "Deprecated"}, reason)

    def exists(self, code: str) -> bool:
        """SELECT 1 WHERE code = ?"""
        row = self.conn.execute("SELECT 1 FROM facts WHERE code = ?", (code,)).fetchone()
        return row is not None

    def all_codes(self) -> list[str]:
        """SELECT code FROM facts ORDER BY code"""
        rows = self.conn.execute("SELECT code FROM facts ORDER BY code").fetchall()
        return [row["code"] for row in rows]

    def stats(self) -> dict:
        """Aggregate counts using SQL GROUP BY."""
        facts = self._list_all_facts()
        by_layer: dict[str, int] = {}
        by_status: dict[str, int] = {}
        stale = 0
        today = datetime.now().date()
        for f in facts:
            by_layer[f.layer.value] = by_layer.get(f.layer.value, 0) + 1
            by_status[f.status.value] = by_status.get(f.status.value, 0) + 1
            if f.review_by and f.review_by < today:
                stale += 1
        return {
            "total": len(facts),
            "by_layer": by_layer,
            "by_status": by_status,
            "stale": stale,
            "backend": "sqlite",
        }

    # ── Private helpers ──

    def _list_all_facts(self) -> list[Fact]:
        """Load all facts from the database."""
        rows = self.conn.execute("SELECT * FROM facts ORDER BY code").fetchall()
        return [self._fact_from_row(row) for row in rows]

    def _fact_from_row(self, row: sqlite3.Row) -> Fact:
        """Convert a database row to a Fact model instance."""
        code = row["code"]

        # Fetch tags
        tag_rows = self.conn.execute(
            "SELECT tag FROM fact_tags WHERE code = ? ORDER BY tag",
            (code,),
        ).fetchall()
        tags = [r["tag"] for r in tag_rows]

        # Fetch refs (typed)
        ref_rows = self.conn.execute(
            "SELECT target_code, rel_type FROM fact_refs WHERE source_code = ? ORDER BY target_code",
            (code,),
        ).fetchall()
        refs = [{"code": r["target_code"], "rel": r["rel_type"]} for r in ref_rows]

        # Fetch projects
        project_rows = self.conn.execute(
            "SELECT project FROM fact_projects WHERE code = ? ORDER BY project",
            (code,),
        ).fetchall()
        projects = [r["project"] for r in project_rows]

        return Fact(
            code=code,
            layer=FactLayer(row["layer"]),
            type=row["type"],
            fact=row["fact"],
            status=FactStatus(row["status"]),
            confidence=FactConfidence(row["confidence"]),
            version=row["version"],
            owner=row["owner"],
            review_by=date.fromisoformat(row["review_by"]) if row["review_by"] else None,
            superseded_by=row["superseded_by"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            tags=tags,
            refs=refs,
            projects=projects,
        )

    def _append_changelog(self, action: str, code: str, reason: str):
        """Append to both the SQLite changelog table and the JSONL file."""
        now = datetime.now().isoformat()
        self.conn.execute(
            "INSERT INTO changelog (timestamp, action, code, reason) VALUES (?, ?, ?, ?)",
            (now, action, code, reason),
        )
        # Also write to JSONL for compatibility
        self.history_dir.mkdir(parents=True, exist_ok=True)
        entry = {
            "timestamp": now,
            "action": action,
            "code": code,
            "reason": reason,
        }
        changelog = self.history_dir / "changelog.jsonl"
        with open(changelog, "a") as f:
            f.write(json.dumps(entry) + "\n")

    def close(self):
        """Close the database connection."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False
