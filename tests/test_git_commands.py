"""CLI integration tests for git commands (diff, log)."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from ruamel.yaml import YAML
from typer.testing import CliRunner

from lattice_lens.cli.main import app
from lattice_lens.config import FACTS_DIR, LATTICE_DIR

runner = CliRunner()
yaml_rw = YAML()
yaml_rw.default_flow_style = False


@pytest.fixture
def cli_dir(tmp_path: Path, monkeypatch):
    """Set cwd to tmp_path for CLI tests."""
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.fixture
def git_repo(cli_dir: Path):
    """Initialize a git repo in cli_dir."""
    subprocess.run(["git", "init"], cwd=str(cli_dir), capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=str(cli_dir),
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=str(cli_dir),
        capture_output=True,
    )
    return cli_dir


@pytest.fixture
def seeded_git_dir(git_repo: Path):
    """Lattice init + seed + initial commit in a git repo."""
    result = runner.invoke(app, ["init"])
    assert result.exit_code == 0

    seed_src = Path(__file__).resolve().parent.parent / "seed"
    seed_dst = git_repo / "seed"
    if seed_src.exists():
        shutil.copytree(seed_src, seed_dst, dirs_exist_ok=True)

    result = runner.invoke(app, ["seed"])
    assert result.exit_code == 0

    # Initial commit
    subprocess.run(
        ["git", "add", "."],
        cwd=str(git_repo),
        capture_output=True,
    )
    subprocess.run(
        ["git", "commit", "-m", "Initial seed"],
        cwd=str(git_repo),
        capture_output=True,
    )
    return git_repo


class TestDiffCommand:
    def test_diff_no_changes(self, seeded_git_dir: Path):
        """No changes should show 'No changes' message."""
        result = runner.invoke(app, ["diff"])
        assert result.exit_code == 0
        assert "No changes" in result.output

    def test_diff_detects_changes(self, seeded_git_dir: Path):
        """After modifying a fact, lattice diff should show the code."""
        # Modify ADR-01
        fact_file = seeded_git_dir / LATTICE_DIR / FACTS_DIR / "ADR-01.yaml"
        with open(fact_file) as f:
            data = yaml_rw.load(f)
        data["fact"] = "Modified fact text for testing diff detection."
        with open(fact_file, "w") as f:
            yaml_rw.dump(data, f)

        result = runner.invoke(app, ["diff"])
        assert result.exit_code == 0
        assert "ADR-01" in result.output

    def test_diff_staged(self, seeded_git_dir: Path):
        """--staged shows only staged changes."""
        # Modify and stage ADR-01
        fact_file = seeded_git_dir / LATTICE_DIR / FACTS_DIR / "ADR-01.yaml"
        with open(fact_file) as f:
            data = yaml_rw.load(f)
        data["fact"] = "Staged change for testing diff command."
        with open(fact_file, "w") as f:
            yaml_rw.dump(data, f)

        subprocess.run(
            ["git", "add", str(fact_file)],
            cwd=str(seeded_git_dir),
            capture_output=True,
        )

        result = runner.invoke(app, ["diff", "--staged"])
        assert result.exit_code == 0
        assert "ADR-01" in result.output

    def test_diff_no_git(self, cli_dir: Path):
        """Should show error when not in a git repo."""
        # Init lattice but not git
        runner.invoke(app, ["init"])
        result = runner.invoke(app, ["diff"])
        assert result.exit_code != 0
        assert "git" in result.output.lower() or "Not a git" in result.output


class TestLogCommand:
    def test_log_shows_history(self, seeded_git_dir: Path):
        """After commits, lattice log shows entries."""
        result = runner.invoke(app, ["log"])
        assert result.exit_code == 0
        assert "Initial seed" in result.output

    def test_log_specific_fact(self, seeded_git_dir: Path):
        """lattice log ADR-01 shows history for that fact."""
        result = runner.invoke(app, ["log", "ADR-01"])
        assert result.exit_code == 0
        # Should at least show the initial commit
        assert "Initial seed" in result.output or "Git history" in result.output

    def test_log_limit(self, seeded_git_dir: Path):
        """--limit controls max entries."""
        result = runner.invoke(app, ["log", "--limit", "1"])
        assert result.exit_code == 0

    def test_log_no_git(self, cli_dir: Path):
        """Should show error when not in a git repo."""
        runner.invoke(app, ["init"])
        result = runner.invoke(app, ["log"])
        assert result.exit_code != 0


class TestUpgradeCommand:
    def test_upgrade_migrates_old_roles(self, cli_dir: Path):
        """lattice upgrade should migrate v0.1.0 role format to v0.2.0."""
        # Create a Phase 1 lattice manually (no version in config)
        lattice_dir = cli_dir / LATTICE_DIR
        roles_dir = lattice_dir / "roles"
        facts_dir = lattice_dir / FACTS_DIR
        history_dir = lattice_dir / "history"
        facts_dir.mkdir(parents=True)
        roles_dir.mkdir(parents=True)
        history_dir.mkdir(parents=True)

        # Write a Phase 1 config (no version field)
        config = {"backend": "yaml", "auto_promote": {"enabled": False}}
        with open(lattice_dir / "config.yaml", "w") as f:
            yaml_rw.dump(config, f)

        old_role = {
            "name": "Test Agent",
            "description": "Test",
            "layers": ["WHY"],
            "tags": ["architecture"],
            "max_facts": 20,
        }
        with open(roles_dir / "test.yaml", "w") as f:
            yaml_rw.dump(old_role, f)

        result = runner.invoke(app, ["upgrade"])
        assert result.exit_code == 0
        assert "Migrated" in result.output

        # Verify new role format
        with open(roles_dir / "test.yaml") as f:
            data = yaml_rw.load(f)
        assert "query" in data
        assert data["query"]["layers"] == ["WHY"]
        assert data["query"]["tags"] == ["architecture"]
        assert "layers" not in data  # top-level removed

        # Verify version stamped in config
        with open(lattice_dir / "config.yaml") as f:
            config = yaml_rw.load(f)
        assert config["version"] == "0.4.0"

    def test_upgrade_noop_new_format(self, cli_dir: Path):
        """lattice upgrade on v0.2.0 lattice is a no-op."""
        # Init creates latest format with version stamped
        result = runner.invoke(app, ["init"])
        assert result.exit_code == 0

        result = runner.invoke(app, ["upgrade"])
        assert result.exit_code == 0
        assert "already" in result.output.lower()

    def test_upgrade_idempotent(self, cli_dir: Path):
        """Running upgrade twice doesn't break anything."""
        lattice_dir = cli_dir / LATTICE_DIR
        roles_dir = lattice_dir / "roles"
        (lattice_dir / FACTS_DIR).mkdir(parents=True)
        roles_dir.mkdir(parents=True)
        (lattice_dir / "history").mkdir(parents=True)

        config = {"backend": "yaml"}
        with open(lattice_dir / "config.yaml", "w") as f:
            yaml_rw.dump(config, f)

        old_role = {"name": "Test", "layers": ["WHY"], "tags": ["test", "example"], "max_facts": 10}
        with open(roles_dir / "test.yaml", "w") as f:
            yaml_rw.dump(old_role, f)

        # First upgrade
        result = runner.invoke(app, ["upgrade"])
        assert result.exit_code == 0
        assert "Migrated" in result.output

        # Second upgrade — should be no-op
        result = runner.invoke(app, ["upgrade"])
        assert result.exit_code == 0
        assert "already" in result.output.lower()
