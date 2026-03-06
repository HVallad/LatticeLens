"""Code scanner — scans source files for fact references and architectural patterns."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

# Regex for fact codes like ADR-03, RISK-07, SP-01
FACT_CODE_RE = re.compile(r"\b([A-Z]+-\d+)\b")

# Default file patterns
DEFAULT_INCLUDE = ["**/*.py"]
DEFAULT_EXCLUDE = [
    "**/node_modules/**",
    "**/.venv/**",
    "**/__pycache__/**",
    "**/.lattice/**",
    "**/.git/**",
]

# Architectural patterns that suggest undocumented decisions
ARCHITECTURAL_PATTERNS: dict[str, dict] = {
    "framework": {
        "patterns": [
            re.compile(r"import\s+(typer|click|flask|fastapi|django|starlette)"),
            re.compile(r"from\s+(typer|click|flask|fastapi|django|starlette)\s+import"),
        ],
        "suggests": "Technology choice — should have an ADR",
    },
    "validation": {
        "patterns": [
            re.compile(r"class\s+\w+\(BaseModel\)"),
            re.compile(r"@(validator|field_validator)"),
            re.compile(r"from\s+pydantic\s+import"),
        ],
        "suggests": "Validation strategy — should be documented",
    },
    "storage": {
        "patterns": [
            re.compile(r"import\s+(sqlite3|sqlalchemy)"),
            re.compile(r"from\s+(sqlite3|sqlalchemy)\s+import"),
            re.compile(r"import\s+redis"),
        ],
        "suggests": "Storage decision — should have an ADR",
    },
    "security": {
        "patterns": [
            re.compile(r"import\s+(hashlib|hmac|secrets)"),
            re.compile(r"from\s+(hashlib|hmac|secrets)\s+import"),
            re.compile(r"\b(encrypt|decrypt|sanitize)\s*\("),
        ],
        "suggests": "Security measure — should have a RISK or AUP fact",
    },
    "error_handling": {
        "patterns": [
            re.compile(r"class\s+\w+Error\("),
            re.compile(r"class\s+\w+Exception\("),
        ],
        "suggests": "Error strategy — may need documentation",
    },
}


@dataclass
class CodeReference:
    """A reference to a lattice fact found in source code."""

    file: Path
    line: int
    code: str  # Fact code found (e.g., "ADR-03")
    context: str  # Surrounding code snippet
    match_type: str  # "explicit" (comment/string) or "inferred" (pattern match)


@dataclass
class ArchitecturalPattern:
    """A detected architectural pattern in source code."""

    category: str  # e.g., "framework", "storage"
    file: Path
    line: int
    match: str  # The matched text
    suggests: str  # What kind of fact should document this


def _iter_source_files(
    root: Path,
    include: list[str] | None = None,
    exclude: list[str] | None = None,
) -> list[Path]:
    """Collect source files matching include patterns, excluding exclude patterns."""
    include = include or DEFAULT_INCLUDE
    exclude = exclude or DEFAULT_EXCLUDE

    files: set[Path] = set()
    for pattern in include:
        files.update(root.glob(pattern))

    # Filter out excluded paths
    result = []
    for f in sorted(files):
        if not f.is_file():
            continue
        rel = str(f.relative_to(root))
        # Normalize to forward slashes for consistent matching
        rel_fwd = rel.replace("\\", "/")
        excluded = False
        for ex_pattern in exclude:
            # Simple substring check for directory-based excludes
            ex_dir = ex_pattern.replace("**/", "").replace("/**", "").replace("*", "")
            if ex_dir and ex_dir in rel_fwd:
                excluded = True
                break
        if not excluded:
            result.append(f)
    return result


def _get_context(lines: list[str], line_idx: int, window: int = 3) -> str:
    """Extract surrounding lines for context."""
    start = max(0, line_idx - window)
    end = min(len(lines), line_idx + window + 1)
    return "\n".join(lines[start:end])


def scan_for_fact_references(
    codebase_root: Path,
    known_codes: list[str],
    include: list[str] | None = None,
    exclude: list[str] | None = None,
) -> list[CodeReference]:
    """Scan source files for explicit fact code references.

    Finds patterns like '# ADR-03', 'per RISK-07', '# See DES-01' in
    comments, docstrings, and string literals.
    """
    known = set(known_codes)
    refs: list[CodeReference] = []

    for path in _iter_source_files(codebase_root, include, exclude):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except (OSError, UnicodeDecodeError):
            continue

        lines = text.splitlines()
        for i, line in enumerate(lines):
            for match in FACT_CODE_RE.finditer(line):
                code = match.group(1)
                if code in known:
                    refs.append(
                        CodeReference(
                            file=path,
                            line=i + 1,
                            code=code,
                            context=_get_context(lines, i),
                            match_type="explicit",
                        )
                    )

    return refs


def scan_for_architectural_patterns(
    codebase_root: Path,
    include: list[str] | None = None,
    exclude: list[str] | None = None,
) -> list[ArchitecturalPattern]:
    """Scan for code patterns that suggest undocumented architectural decisions.

    Detects framework imports, validation strategies, storage decisions,
    security patterns, and error handling approaches.
    """
    results: list[ArchitecturalPattern] = []

    for path in _iter_source_files(codebase_root, include, exclude):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except (OSError, UnicodeDecodeError):
            continue

        lines = text.splitlines()
        for i, line in enumerate(lines):
            for category, config in ARCHITECTURAL_PATTERNS.items():
                for pattern in config["patterns"]:
                    if pattern.search(line):
                        results.append(
                            ArchitecturalPattern(
                                category=category,
                                file=path,
                                line=i + 1,
                                match=line.strip(),
                                suggests=config["suggests"],
                            )
                        )
                        break  # One match per category per line

    return results
