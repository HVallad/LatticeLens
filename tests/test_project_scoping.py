"""Integration tests for project scoping across model, store, index, and context."""

from __future__ import annotations

from pathlib import Path

import pytest

from lattice_lens.models import FactLayer
from lattice_lens.services.context_service import assemble_context
from lattice_lens.services.project_service import write_project_registry
from lattice_lens.store.index import FactIndex
from lattice_lens.store.yaml_store import YamlFileStore

from conftest import make_fact


class TestFactModelProjects:
    def test_default_empty_projects(self):
        fact = make_fact()
        assert fact.projects == []

    def test_projects_set(self):
        fact = make_fact(projects=["billing", "payments"])
        assert fact.projects == ["billing", "payments"]

    def test_projects_normalized_sorted_deduped(self):
        fact = make_fact(projects=["payments", "billing", "payments"])
        assert fact.projects == ["billing", "payments"]

    def test_projects_lowercased(self):
        fact = make_fact(projects=["Billing"])
        assert fact.projects == ["billing"]

    def test_group_prefix_preserved(self):
        fact = make_fact(projects=["group:pci-scope"])
        assert fact.projects == ["group:pci-scope"]

    def test_invalid_project_name_rejected(self):
        with pytest.raises(ValueError, match="alphanumeric"):
            make_fact(projects=["invalid name!"])

    def test_invalid_group_ref_rejected(self):
        with pytest.raises(ValueError, match="Invalid group"):
            make_fact(projects=["group:"])


class TestIndexByProject:
    def test_codes_by_project(self):
        idx = FactIndex()
        f1 = make_fact(code="ADR-01", projects=["billing"])
        f2 = make_fact(code="ADR-02", projects=["payments"])
        f3 = make_fact(code="ADR-03", projects=["billing", "payments"])
        idx._add(f1)
        idx._add(f2)
        idx._add(f3)

        assert idx.codes_by_project("billing") == {"ADR-01", "ADR-03"}
        assert idx.codes_by_project("payments") == {"ADR-02", "ADR-03"}
        assert idx.codes_by_project("unknown") == set()

    def test_global_codes(self):
        idx = FactIndex()
        f1 = make_fact(code="ADR-01", projects=[])
        f2 = make_fact(code="ADR-02", projects=["billing"])
        idx._add(f1)
        idx._add(f2)

        assert idx.global_codes() == {"ADR-01"}


class TestYamlStoreProjectFilter:
    def test_filter_returns_matching_and_global(self, yaml_store: YamlFileStore):
        global_fact = make_fact(
            code="AUP-01",
            layer=FactLayer.GUARDRAILS,
            type="Acceptable Use Policy Rule",
            projects=[],
        )
        billing_fact = make_fact(
            code="AUP-02",
            layer=FactLayer.GUARDRAILS,
            type="Acceptable Use Policy Rule",
            projects=["billing"],
        )
        docs_fact = make_fact(
            code="AUP-03",
            layer=FactLayer.GUARDRAILS,
            type="Acceptable Use Policy Rule",
            projects=["docs"],
        )
        yaml_store.create(global_fact)
        yaml_store.create(billing_fact)
        yaml_store.create(docs_fact)

        results = yaml_store.list_facts(project="billing")
        codes = {f.code for f in results}
        assert "AUP-01" in codes  # global
        assert "AUP-02" in codes  # billing
        assert "AUP-03" not in codes  # docs only

    def test_no_project_filter_returns_all(self, yaml_store: YamlFileStore):
        f1 = make_fact(code="ADR-01", projects=[])
        f2 = make_fact(code="ADR-02", projects=["billing"])
        yaml_store.create(f1)
        yaml_store.create(f2)

        results = yaml_store.list_facts()
        assert len(results) == 2

    def test_group_filter(self, yaml_store: YamlFileStore):
        # Write projects.yaml with a group
        write_project_registry(
            yaml_store.root,
            ["billing", "payments", "docs"],
            {"pci-scope": ["billing", "payments"]},
        )

        f1 = make_fact(
            code="AUP-01",
            layer=FactLayer.GUARDRAILS,
            type="Acceptable Use Policy Rule",
            projects=["group:pci-scope"],
        )
        f2 = make_fact(
            code="AUP-02",
            layer=FactLayer.GUARDRAILS,
            type="Acceptable Use Policy Rule",
            projects=["docs"],
        )
        yaml_store.create(f1)
        yaml_store.create(f2)

        results = yaml_store.list_facts(project="billing")
        codes = {f.code for f in results}
        assert "AUP-01" in codes  # billing is in pci-scope
        assert "AUP-02" not in codes  # docs only


class TestContextAssemblyWithProject:
    def _build_index_with_project_facts(self):
        """Build an index with facts scoped to different projects."""
        idx = FactIndex()
        # Global guardrail
        idx._add(
            make_fact(
                code="AUP-01",
                layer=FactLayer.GUARDRAILS,
                type="Acceptable Use Policy Rule",
                projects=[],
            )
        )
        # Billing-only guardrail
        idx._add(
            make_fact(
                code="AUP-02",
                layer=FactLayer.GUARDRAILS,
                type="Acceptable Use Policy Rule",
                projects=["billing"],
            )
        )
        # Docs-only guardrail
        idx._add(
            make_fact(
                code="AUP-03",
                layer=FactLayer.GUARDRAILS,
                type="Acceptable Use Policy Rule",
                projects=["docs"],
            )
        )
        return idx

    def test_project_filter_in_context(self):
        idx = self._build_index_with_project_facts()
        template = {
            "query": {
                "layers": ["GUARDRAILS"],
                "tags": [],
            },
        }

        result = assemble_context(idx, "test", template, project="billing")
        codes = {f.code for f in result.loaded_facts}
        assert "AUP-01" in codes  # global
        assert "AUP-02" in codes  # billing
        assert "AUP-03" not in codes  # docs

    def test_no_project_loads_all(self):
        idx = self._build_index_with_project_facts()
        template = {
            "query": {
                "layers": ["GUARDRAILS"],
                "tags": [],
            },
        }

        result = assemble_context(idx, "test", template)
        assert len(result.loaded_facts) == 3


class TestSqliteStoreProjectRoundtrip:
    def test_create_and_read_projects(self, tmp_path: Path):
        from lattice_lens.config import FACTS_DIR, HISTORY_DIR
        from lattice_lens.store.sqlite_store import SqliteStore

        lattice_root = tmp_path / ".lattice"
        (lattice_root / FACTS_DIR).mkdir(parents=True)
        (lattice_root / HISTORY_DIR).mkdir(parents=True)

        store = SqliteStore(lattice_root)
        fact = make_fact(projects=["billing", "payments"])
        store.create(fact)

        loaded = store.get(fact.code)
        assert loaded is not None
        assert loaded.projects == ["billing", "payments"]

        store.close()

    def test_update_projects(self, tmp_path: Path):
        from lattice_lens.config import FACTS_DIR, HISTORY_DIR
        from lattice_lens.store.sqlite_store import SqliteStore

        lattice_root = tmp_path / ".lattice"
        (lattice_root / FACTS_DIR).mkdir(parents=True)
        (lattice_root / HISTORY_DIR).mkdir(parents=True)

        store = SqliteStore(lattice_root)
        fact = make_fact(projects=["billing"])
        store.create(fact)

        updated = store.update(fact.code, {"projects": ["billing", "docs"]}, "add docs")
        assert updated.projects == ["billing", "docs"]

        reloaded = store.get(fact.code)
        assert reloaded is not None
        assert reloaded.projects == ["billing", "docs"]

        store.close()

    def test_project_filter(self, tmp_path: Path):
        from lattice_lens.config import FACTS_DIR, HISTORY_DIR
        from lattice_lens.store.sqlite_store import SqliteStore

        lattice_root = tmp_path / ".lattice"
        (lattice_root / FACTS_DIR).mkdir(parents=True)
        (lattice_root / HISTORY_DIR).mkdir(parents=True)

        store = SqliteStore(lattice_root)
        store.create(make_fact(code="ADR-01", projects=[]))
        store.create(make_fact(code="ADR-02", projects=["billing"]))
        store.create(make_fact(code="ADR-03", projects=["docs"]))

        results = store.list_facts(project="billing")
        codes = {f.code for f in results}
        assert "ADR-01" in codes  # global
        assert "ADR-02" in codes  # billing
        assert "ADR-03" not in codes  # docs

        store.close()
