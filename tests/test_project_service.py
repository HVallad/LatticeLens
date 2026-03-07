"""Tests for project_service — registry load/write, group resolution, validation."""

from __future__ import annotations

from pathlib import Path

import pytest

from lattice_lens.services.project_service import (
    fact_matches_project,
    is_scoping_enabled,
    read_project_registry,
    resolve_projects,
    validate_fact_projects,
    validate_project_registry,
    write_project_registry,
)


class TestReadWriteRoundtrip:
    def test_write_then_read(self, tmp_path: Path):
        projects = ["billing", "checkout", "payments"]
        groups = {"pci-scope": ["billing", "checkout", "payments"]}
        write_project_registry(tmp_path, projects, groups)

        registry = read_project_registry(tmp_path)
        assert registry is not None
        assert set(registry["projects"]) == set(projects)
        assert registry["groups"]["pci-scope"] == sorted(groups["pci-scope"])

    def test_write_without_groups(self, tmp_path: Path):
        write_project_registry(tmp_path, ["alpha", "beta"])
        registry = read_project_registry(tmp_path)
        assert registry is not None
        assert registry["projects"] == ["alpha", "beta"]
        assert registry["groups"] == {}

    def test_read_missing_file(self, tmp_path: Path):
        assert read_project_registry(tmp_path) is None


class TestScopingEnabled:
    def test_enabled_when_file_exists(self, tmp_path: Path):
        write_project_registry(tmp_path, ["a"])
        assert is_scoping_enabled(tmp_path) is True

    def test_disabled_when_no_file(self, tmp_path: Path):
        assert is_scoping_enabled(tmp_path) is False


class TestResolveProjects:
    def test_literal_projects_pass_through(self):
        result = resolve_projects(["billing", "payments"], None)
        assert result == {"billing", "payments"}

    def test_group_expansion(self):
        registry = {
            "projects": ["billing", "payments", "checkout"],
            "groups": {"pci-scope": ["billing", "payments", "checkout"]},
        }
        result = resolve_projects(["group:pci-scope"], registry)
        assert result == {"billing", "payments", "checkout"}

    def test_mixed_literals_and_groups(self):
        registry = {
            "projects": ["billing", "payments", "docs"],
            "groups": {"pci-scope": ["billing", "payments"]},
        }
        result = resolve_projects(["docs", "group:pci-scope"], registry)
        assert result == {"billing", "payments", "docs"}

    def test_empty_entries(self):
        assert resolve_projects([], None) == set()

    def test_unknown_group_raises(self):
        registry = {"projects": ["a"], "groups": {}}
        with pytest.raises(ValueError, match="Unknown group"):
            resolve_projects(["group:nonexistent"], registry)

    def test_group_without_registry_raises(self):
        with pytest.raises(ValueError, match="no projects.yaml"):
            resolve_projects(["group:foo"], None)


class TestFactMatchesProject:
    def test_global_fact_always_visible(self):
        assert fact_matches_project([], "billing") is True

    def test_matching_project(self):
        assert fact_matches_project(["billing"], "billing") is True

    def test_non_matching_project(self):
        assert fact_matches_project(["billing"], "docs") is False

    def test_group_match(self):
        registry = {
            "projects": ["billing", "payments"],
            "groups": {"pci-scope": ["billing", "payments"]},
        }
        assert fact_matches_project(["group:pci-scope"], "billing", registry) is True
        assert fact_matches_project(["group:pci-scope"], "docs", registry) is False

    def test_multiple_projects(self):
        assert fact_matches_project(["billing", "payments"], "payments") is True
        assert fact_matches_project(["billing", "payments"], "docs") is False


class TestValidateProjectRegistry:
    def test_valid_registry(self):
        registry = {
            "projects": ["billing", "payments", "checkout"],
            "groups": {"pci-scope": ["billing", "payments"]},
        }
        errors = validate_project_registry(registry)
        assert errors == []

    def test_name_collision(self):
        registry = {
            "projects": ["billing", "pci-scope"],
            "groups": {"pci-scope": ["billing"]},
        }
        errors = validate_project_registry(registry)
        assert len(errors) == 1
        assert "collides" in errors[0]

    def test_unknown_member(self):
        registry = {
            "projects": ["billing"],
            "groups": {"scope": ["billing", "nonexistent"]},
        }
        errors = validate_project_registry(registry)
        assert len(errors) == 1
        assert "nonexistent" in errors[0]

    def test_empty_registry_valid(self):
        registry = {"projects": [], "groups": {}}
        assert validate_project_registry(registry) == []


class TestValidateFactProjects:
    def test_valid_literal(self):
        registry = {"projects": ["billing"], "groups": {}}
        assert validate_fact_projects(["billing"], registry) == []

    def test_valid_group_ref(self):
        registry = {"projects": ["billing"], "groups": {"pci": ["billing"]}}
        assert validate_fact_projects(["group:pci"], registry) == []

    def test_unknown_project(self):
        registry = {"projects": ["billing"], "groups": {}}
        errors = validate_fact_projects(["nonexistent"], registry)
        assert len(errors) == 1
        assert "Unknown project" in errors[0]

    def test_unknown_group(self):
        registry = {"projects": ["billing"], "groups": {}}
        errors = validate_fact_projects(["group:nope"], registry)
        assert len(errors) == 1
        assert "Unknown group" in errors[0]
