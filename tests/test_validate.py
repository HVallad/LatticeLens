"""Integrity check tests."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from ruamel.yaml import YAML

from lattice_lens.services.validate_service import validate_lattice
from lattice_lens.store.yaml_store import YamlFileStore
from tests.conftest import make_fact

yaml_rw = YAML()
yaml_rw.default_flow_style = False


class TestValidation:
    def test_valid_lattice_passes(self, seeded_store: YamlFileStore):
        result = validate_lattice(seeded_store.facts_dir)
        assert result.ok
        # There will be ref warnings because seed data refs non-existent codes
        # (RISK-03, ETH-01, etc.) but no errors

    def test_broken_ref_detected(self, yaml_store: YamlFileStore):
        fact = make_fact(code="ADR-10", refs=["NOPE-99"])
        yaml_store.create(fact)
        result = validate_lattice(yaml_store.facts_dir)
        assert any("NOPE-99" in w for w in result.warnings)

    def test_duplicate_code_detected(self, yaml_store: YamlFileStore):
        # Write two files with the same code field
        fact = make_fact(code="ADR-10")
        yaml_store.create(fact)

        # Manually write a second file with the same code
        dup_path = yaml_store.facts_dir / "ADR-10-dup.yaml"
        with open(dup_path, "w") as f:
            yaml_rw.dump(fact.model_dump(mode="json"), f)

        result = validate_lattice(yaml_store.facts_dir)
        assert not result.ok
        assert any("Duplicate code" in e for e in result.errors)

    def test_malformed_yaml_detected(self, yaml_store: YamlFileStore):
        bad_path = yaml_store.facts_dir / "BAD-01.yaml"
        bad_path.write_text("{{invalid yaml: [")

        result = validate_lattice(yaml_store.facts_dir)
        assert not result.ok
        assert any("YAML parse error" in e or "Validation error" in e for e in result.errors)

    def test_stale_facts_listed(self, yaml_store: YamlFileStore):
        fact = make_fact(code="ADR-10", review_by=date.today() - timedelta(days=1))
        yaml_store.create(fact)

        result = validate_lattice(yaml_store.facts_dir)
        assert any("stale" in w.lower() for w in result.warnings)

    def test_empty_facts_dir(self, tmp_lattice: Path):
        from lattice_lens.config import FACTS_DIR

        result = validate_lattice(tmp_lattice / FACTS_DIR)
        assert result.ok  # no errors
        assert any("No fact files" in w for w in result.warnings)
