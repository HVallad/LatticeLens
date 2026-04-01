"""Fact access tracking for maintenance and pruning.

Tracks how many times each fact is accessed/pulled so teams can identify
unused, low-priority, or incorrectly tagged facts that agents are missing.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from ruamel.yaml import YAML

ACCESS_LOG_FILE = "access_log.yaml"

yaml = YAML()
yaml.default_flow_style = False


class AccessTracker:
    """Tracks fact access counts. Stored in .lattice/access_log.yaml."""

    def __init__(self, lattice_root: Path):
        self.log_path = lattice_root / ACCESS_LOG_FILE
        self.data: dict[str, dict] = self._load()

    def _load(self) -> dict[str, dict]:
        """Load access log from YAML file. Returns empty dict if missing."""
        if not self.log_path.exists():
            return {}
        with open(self.log_path) as f:
            raw = yaml.load(f)
        if raw is None:
            return {}
        # Normalize loaded data to plain dicts
        result: dict[str, dict] = {}
        for code, entry in raw.items():
            result[str(code)] = {
                "count": int(entry.get("count", 0)),
                "last_accessed": entry.get("last_accessed"),
                "first_accessed": entry.get("first_accessed"),
                "sources": dict(entry.get("sources", {})),
            }
        return result

    def record_access(self, code: str, source: str = "unknown") -> None:
        """Record a fact being accessed.

        Args:
            code: The fact code (e.g., ADR-01).
            source: Access source — one of "cli", "context", "api", "mcp", "search".
        """
        now = datetime.now(timezone.utc).isoformat()

        if code not in self.data:
            self.data[code] = {
                "count": 0,
                "last_accessed": None,
                "first_accessed": now,
                "sources": {},
            }

        entry = self.data[code]
        entry["count"] = entry.get("count", 0) + 1
        entry["last_accessed"] = now
        if entry.get("first_accessed") is None:
            entry["first_accessed"] = now

        sources = entry.setdefault("sources", {})
        sources[source] = sources.get(source, 0) + 1

        self.save()

    def get_counts(self) -> dict[str, dict]:
        """Return {code: {count, last_accessed, first_accessed, sources}} for all facts."""
        return dict(self.data)

    def get_stats(self, code: str) -> dict | None:
        """Return stats for a specific fact code, or None if not tracked."""
        return self.data.get(code)

    def get_cold_facts(self, threshold: int = 0, days: int = 30) -> list[dict]:
        """Find facts never accessed or not accessed in N days.

        Args:
            threshold: Maximum access count to be considered cold (default 0 = never accessed).
            days: Facts not accessed in this many days are cold.

        Returns:
            List of {code, count, last_accessed, days_since} dicts, sorted by count ascending.
        """
        now = datetime.now(timezone.utc)
        results: list[dict] = []

        for code, entry in self.data.items():
            count = entry.get("count", 0)
            last = entry.get("last_accessed")

            if count <= threshold:
                days_since = None
                if last:
                    last_dt = datetime.fromisoformat(last)
                    days_since = (now - last_dt).days
                results.append(
                    {"code": code, "count": count, "last_accessed": last, "days_since": days_since}
                )
                continue

            if last:
                last_dt = datetime.fromisoformat(last)
                days_since = (now - last_dt).days
                if days_since >= days:
                    results.append(
                        {
                            "code": code,
                            "count": count,
                            "last_accessed": last,
                            "days_since": days_since,
                        }
                    )

        results.sort(key=lambda x: x["count"])
        return results

    def get_hot_facts(self, top_k: int = 10) -> list[dict]:
        """Find most frequently accessed facts.

        Args:
            top_k: Number of top facts to return.

        Returns:
            List of {code, count, last_accessed, sources} dicts, sorted by count descending.
        """
        items = [
            {
                "code": code,
                "count": entry.get("count", 0),
                "last_accessed": entry.get("last_accessed"),
                "sources": entry.get("sources", {}),
            }
            for code, entry in self.data.items()
        ]
        items.sort(key=lambda x: x["count"], reverse=True)
        return items[:top_k]

    def reset(self, code: str | None = None) -> None:
        """Reset counts for one fact or all facts.

        Args:
            code: If provided, reset only this fact. Otherwise reset all.
        """
        if code is not None:
            if code in self.data:
                self.data[code] = {
                    "count": 0,
                    "last_accessed": None,
                    "first_accessed": None,
                    "sources": {},
                }
        else:
            self.data = {}
        self.save()

    def save(self) -> None:
        """Persist access log to access_log.yaml."""
        # Ensure parent directory exists
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.log_path, "w") as f:
            yaml.dump(dict(self.data) if self.data else {}, f)


def get_tracker(lattice_root: Path) -> AccessTracker:
    """Create an AccessTracker for the given lattice root.

    This is the primary entry point for obtaining a tracker instance.
    """
    return AccessTracker(lattice_root)
