"""Integrity check tests."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from ruamel.yaml import YAML

from lattice_lens.config import FACTS_DIR
from lattice_lens.services.validate_service import ValidationResult, fix_lattice, validate_lattice
from lattice_lens.store.yaml_store import YamlFileStore
from tests.conftest import make_fact

yaml_rw = YAML()
yaml_rw.default_flow_style = False


# ── ValidationResult unit tests ──


class TestValidationResult:
    def test_ok_when_empty(self):
        r = ValidationResult()
        assert r.ok
        assert r.errors == []
        assert r.warnings == []

    def test_not_ok_with_error(self):
        r = ValidationResult()
        r.add_error("something broke")
        assert not r.ok
        assert "something broke" in r.errors

    def test_ok_with_only_warnings(self):
        r = ValidationResult()
        r.add_warning("heads up")
        assert r.ok  # warnings don't fail
        assert "heads up" in r.warnings

    def test_multiple_errors_and_warnings(self):
        r = ValidationResult()
        r.add_error("err1")
        r.add_error("err2")
        r.add_warning("warn1")
        assert not r.ok
        assert len(r.errors) == 2
        assert len(r.warnings) == 1


# ── validate_lattice tests ──


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
        result = validate_lattice(tmp_lattice / FACTS_DIR)
        assert result.ok  # no errors
        assert any("No fact files" in w for w in result.warnings)

    def test_nonexistent_facts_dir(self, tmp_path: Path):
        """Nonexistent directory produces an error."""
        result = validate_lattice(tmp_path / "no_such_dir")
        assert not result.ok
        assert any("does not exist" in e for e in result.errors)

    def test_empty_yaml_file_detected(self, yaml_store: YamlFileStore):
        """An empty YAML file produces an error."""
        empty = yaml_store.facts_dir / "EMPTY-01.yaml"
        empty.write_text("")
        result = validate_lattice(yaml_store.facts_dir)
        assert not result.ok
        assert any("Empty YAML" in e for e in result.errors)

    def test_code_layer_prefix_mismatch(self, yaml_store: YamlFileStore):
        """A code prefix that doesn't match the layer is an error.

        We write raw YAML to bypass Pydantic's model validator (which would
        reject the mismatch before the file is ever written).
        """
        bad_data = make_fact(code="ADR-01").model_dump(mode="json")
        bad_data["layer"] = "GUARDRAILS"  # ADR is a WHY prefix
        path = yaml_store.facts_dir / "ADR-01.yaml"
        with open(path, "w") as f:
            yaml_rw.dump(bad_data, f)

        result = validate_lattice(yaml_store.facts_dir)
        assert not result.ok
        assert any("prefix" in e.lower() for e in result.errors)

    def test_pydantic_normalizes_tags_so_no_unsorted_warning(self, yaml_store: YamlFileStore):
        """Pydantic's normalize_tags sorts tags on load, so validate_lattice
        never sees unsorted tags from well-formed facts. This test confirms
        that writing tags in any order results in no 'not sorted' warning."""
        fact = make_fact(code="ADR-10", tags=["zebra", "alpha"])
        yaml_store.create(fact)

        result = validate_lattice(yaml_store.facts_dir)
        # Tags were normalized by Pydantic on create, so no unsorted warning
        assert not any("not sorted" in w.lower() for w in result.warnings)

    def test_raw_unsorted_tags_also_normalized(self, yaml_store: YamlFileStore):
        """Even raw unsorted tags in YAML don't trigger a 'not sorted' warning
        because validate_lattice parses via Fact(**data), which normalizes."""
        data = make_fact(code="ADR-10").model_dump(mode="json")
        data["tags"] = ["zebra", "alpha"]  # Write unsorted directly
        path = yaml_store.facts_dir / "ADR-10.yaml"
        with open(path, "w") as f:
            yaml_rw.dump(data, f)

        result = validate_lattice(yaml_store.facts_dir)
        # Pydantic normalizes tags on Fact(**data), so no unsorted warning
        assert not any("not sorted" in w.lower() for w in result.warnings)

    def test_superseded_without_target_is_validation_error(self, yaml_store: YamlFileStore):
        """Superseded status without superseded_by field is rejected by Pydantic
        (model validator), appearing as a 'Validation error' in validate_lattice."""
        data = make_fact(code="ADR-10").model_dump(mode="json")
        data["status"] = "Superseded"
        data["superseded_by"] = None
        path = yaml_store.facts_dir / "ADR-10.yaml"
        with open(path, "w") as f:
            yaml_rw.dump(data, f)

        result = validate_lattice(yaml_store.facts_dir)
        assert not result.ok
        assert any("Validation error" in e for e in result.errors)

    def test_superseded_with_superseded_by_field_passes(self, yaml_store: YamlFileStore):
        """Superseded fact with superseded_by field set is valid."""
        # First create the target fact
        target = make_fact(code="ADR-11")
        yaml_store.create(target)

        data = make_fact(code="ADR-10").model_dump(mode="json")
        data["status"] = "Superseded"
        data["superseded_by"] = "ADR-11"
        path = yaml_store.facts_dir / "ADR-10.yaml"
        with open(path, "w") as f:
            yaml_rw.dump(data, f)

        result = validate_lattice(yaml_store.facts_dir)
        assert result.ok

    def test_superseded_with_inbound_supersedes_edge_passes(self, yaml_store: YamlFileStore):
        """Superseded fact targeted by a 'supersedes' edge from another fact is valid."""
        # The superseded fact (has superseded_by to pass Pydantic)
        old = make_fact(code="ADR-10")
        old_data = old.model_dump(mode="json")
        old_data["status"] = "Superseded"
        old_data["superseded_by"] = "ADR-11"
        path = yaml_store.facts_dir / "ADR-10.yaml"
        with open(path, "w") as f:
            yaml_rw.dump(old_data, f)

        # The new fact that supersedes ADR-10
        new = make_fact(code="ADR-11", refs=[{"code": "ADR-10", "rel": "supersedes"}])
        yaml_store.create(new)

        result = validate_lattice(yaml_store.facts_dir)
        assert result.ok

    def test_type_mismatch_warning(self, yaml_store: YamlFileStore):
        """Non-canonical type for a prefix produces a warning."""
        fact = make_fact(code="ADR-10", type="Some Random Type")
        yaml_store.create(fact)

        result = validate_lattice(yaml_store.facts_dir)
        # ADR prefix should map to "Architecture Decision Record"
        assert any("differs from canonical" in w for w in result.warnings)

    def test_frequent_free_tag_warning(self, yaml_store: YamlFileStore):
        """A free tag appearing in ≥3 facts triggers DG-07 warning."""
        # Create 3 facts all sharing the same free tag
        for i in range(3):
            fact = make_fact(code=f"ADR-{10 + i:02d}", tags=["xyzzy-custom", "example"])
            yaml_store.create(fact)

        result = validate_lattice(yaml_store.facts_dir)
        assert any("xyzzy-custom" in w and "DG-07" in w for w in result.warnings)

    def test_project_scoping_validation(self, yaml_store: YamlFileStore):
        """Project scoping validation catches unknown projects."""
        # Enable project scoping by creating projects.yaml
        lattice_root = yaml_store.facts_dir.parent
        registry_data = {
            "projects": ["alpha", "beta"],
            "groups": {"frontend": ["alpha"]},
        }
        projects_path = lattice_root / "projects.yaml"
        with open(projects_path, "w") as f:
            yaml_rw.dump(registry_data, f)

        # Create a fact referencing an unknown project
        fact = make_fact(code="ADR-10", projects=["alpha", "gamma"])
        yaml_store.create(fact)

        result = validate_lattice(yaml_store.facts_dir)
        assert any("gamma" in w for w in result.warnings)

    def test_valid_refs_no_warning(self, yaml_store: YamlFileStore):
        """Valid refs between existing facts produce no warning."""
        fact1 = make_fact(code="ADR-10")
        fact2 = make_fact(code="ADR-11", refs=["ADR-10"])
        yaml_store.create(fact1)
        yaml_store.create(fact2)

        result = validate_lattice(yaml_store.facts_dir)
        # No broken ref warnings
        assert not any("does not exist" in w for w in result.warnings)

    def test_non_stale_fact_no_warning(self, yaml_store: YamlFileStore):
        """A fact with review_by in the future produces no staleness warning."""
        fact = make_fact(code="ADR-10", review_by=date.today() + timedelta(days=30))
        yaml_store.create(fact)

        result = validate_lattice(yaml_store.facts_dir)
        assert not any("stale" in w.lower() for w in result.warnings)


# ── fix_lattice tests ──


class TestFixLattice:
    def test_fix_normalizes_tags(self, yaml_store: YamlFileStore):
        """fix_lattice normalizes unsorted/mixed-case tags in raw YAML."""
        data = make_fact(code="ADR-10").model_dump(mode="json")
        data["tags"] = ["Zebra", "alpha", "Zebra"]
        path = yaml_store.facts_dir / "ADR-10.yaml"
        with open(path, "w") as f:
            yaml_rw.dump(data, f)

        result, fixed = fix_lattice(yaml_store.facts_dir)
        assert fixed == 1
        assert any("Auto-fixed" in w for w in result.warnings)

        # Re-read and verify tags are normalized
        with open(path) as f:
            updated = yaml_rw.load(f)
        assert updated["tags"] == ["alpha", "zebra"]

    def test_fix_no_changes_needed(self, yaml_store: YamlFileStore):
        """fix_lattice on a clean lattice changes nothing."""
        fact = make_fact(code="ADR-10", tags=["alpha", "zebra"])
        yaml_store.create(fact)

        result, fixed = fix_lattice(yaml_store.facts_dir)
        assert fixed == 0

    def test_fix_nonexistent_dir(self, tmp_path: Path):
        """fix_lattice with nonexistent dir returns error."""
        result, fixed = fix_lattice(tmp_path / "no_such_dir")
        assert not result.ok
        assert fixed == 0

    def test_fix_skips_malformed_yaml(self, yaml_store: YamlFileStore):
        """fix_lattice skips files with broken YAML."""
        bad = yaml_store.facts_dir / "BAD-01.yaml"
        bad.write_text("{{bad yaml [")

        result, fixed = fix_lattice(yaml_store.facts_dir)
        assert fixed == 0  # couldn't parse, so nothing fixed

    def test_fix_deduplicates_tags(self, yaml_store: YamlFileStore):
        """fix_lattice deduplicates tags."""
        data = make_fact(code="ADR-10").model_dump(mode="json")
        data["tags"] = ["test", "test", "example"]
        path = yaml_store.facts_dir / "ADR-10.yaml"
        with open(path, "w") as f:
            yaml_rw.dump(data, f)

        result, fixed = fix_lattice(yaml_store.facts_dir)
        assert fixed == 1

        with open(path) as f:
            updated = yaml_rw.load(f)
        assert updated["tags"] == ["example", "test"]  # sorted, deduplicated

    def test_fix_empty_yaml_skipped(self, yaml_store: YamlFileStore):
        """fix_lattice skips empty YAML files."""
        empty = yaml_store.facts_dir / "EMPTY-01.yaml"
        empty.write_text("")

        result, fixed = fix_lattice(yaml_store.facts_dir)
        assert fixed == 0
