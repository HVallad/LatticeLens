"""Fixtures: temp .lattice dirs, seed data."""

from __future__ import annotations

from pathlib import Path

import pytest
from ruamel.yaml import YAML

from lattice_lens.config import FACTS_DIR, HISTORY_DIR, LATTICE_DIR, ROLES_DIR
from lattice_lens.models import Fact, FactConfidence, FactLayer, FactStatus
from lattice_lens.store.yaml_store import YamlFileStore

yaml_rw = YAML()
yaml_rw.default_flow_style = False

SEED_FILE = Path(__file__).resolve().parent.parent / "seed" / "example_facts.yaml"


@pytest.fixture
def tmp_lattice(tmp_path: Path) -> Path:
    """Create a temporary .lattice/ directory structure, return its path."""
    lattice_root = tmp_path / LATTICE_DIR
    (lattice_root / FACTS_DIR).mkdir(parents=True)
    (lattice_root / ROLES_DIR).mkdir(parents=True)
    (lattice_root / HISTORY_DIR).mkdir(parents=True)
    return lattice_root


@pytest.fixture
def yaml_store(tmp_lattice: Path) -> YamlFileStore:
    """Return a YamlFileStore pointed at tmp_lattice."""
    return YamlFileStore(tmp_lattice)


@pytest.fixture
def seeded_store(yaml_store: YamlFileStore) -> YamlFileStore:
    """Load the 12 seed facts into yaml_store, return the store."""
    with open(SEED_FILE) as f:
        seed_data = yaml_rw.load(f)

    for item in seed_data:
        fact = Fact(**item)
        yaml_store.create(fact)

    yaml_store.invalidate_index()
    return yaml_store


def make_fact(**overrides) -> Fact:
    """Helper to create a Fact with sensible defaults."""
    defaults = {
        "code": "ADR-99",
        "layer": FactLayer.WHY,
        "type": "Architecture Decision Record",
        "fact": "This is a test fact with sufficient length.",
        "tags": ["test", "example"],
        "status": FactStatus.ACTIVE,
        "confidence": FactConfidence.CONFIRMED,
        "owner": "test-team",
    }
    defaults.update(overrides)
    return Fact(**defaults)
