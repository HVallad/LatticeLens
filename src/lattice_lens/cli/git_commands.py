"""lattice diff / log — git-aware change tracking scoped to .lattice/facts/."""

from __future__ import annotations

import re
import subprocess
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from lattice_lens.cli.helpers import require_local_lattice

console = Console()
err_console = Console(stderr=True)


def _check_git() -> bool:
    """Check if git is available and we're in a git repo."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            capture_output=True,
            text=True,
        )
        return result.returncode == 0
    except FileNotFoundError:
        return False


def _git_error_message():
    err_console.print(
        "[red]Error:[/red] Not a git repository or git is not installed.\n"
        "LatticeLens git commands require a git repository."
    )
    raise typer.Exit(1)


def diff(
    staged: bool = typer.Option(False, "--staged", help="Show only staged changes"),
):
    """Show fact-level summary of git changes in .lattice/facts/."""
    store = require_local_lattice()

    if not _check_git():
        _git_error_message()

    facts_path = str(store.root / "facts")
    cmd = ["git", "diff"]
    if staged:
        cmd.append("--staged")
    cmd.append("--")
    cmd.append(facts_path)

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        err_console.print(f"[red]Error:[/red] git diff failed: {result.stderr.strip()}")
        raise typer.Exit(1)

    diff_output = result.stdout
    if not diff_output.strip():
        console.print("[dim]No changes to lattice facts.[/dim]")
        return

    # Parse diff to extract changed facts and fields
    changed_facts: dict[str, list[str]] = {}  # code -> list of changed fields
    added_facts: list[str] = []
    deleted_facts: list[str] = []

    current_file = None
    for line in diff_output.splitlines():
        # Detect file header
        if line.startswith("diff --git"):
            match = re.search(r"b/.*?/facts/([A-Z]+-\d+)\.yaml", line)
            if match:
                current_file = match.group(1)
            else:
                current_file = None
            continue

        if current_file is None:
            continue

        # New file
        if line.startswith("new file"):
            added_facts.append(current_file)
            continue

        # Deleted file
        if line.startswith("deleted file"):
            deleted_facts.append(current_file)
            continue

        # Changed field (lines starting with + or - that contain a YAML key)
        if line.startswith("+") and not line.startswith("+++"):
            field_match = re.match(r"^\+(\w+):", line)
            if field_match and current_file not in added_facts:
                field_name = field_match.group(1)
                if current_file not in changed_facts:
                    changed_facts[current_file] = []
                if field_name not in changed_facts[current_file]:
                    changed_facts[current_file].append(field_name)

    # Display results
    if added_facts or deleted_facts or changed_facts:
        table = Table(title="Lattice Fact Changes")
        table.add_column("Code", style="bold")
        table.add_column("Change")
        table.add_column("Fields")

        for code in sorted(added_facts):
            table.add_row(code, "[green]added[/green]", "—")

        for code in sorted(changed_facts.keys()):
            if code not in added_facts and code not in deleted_facts:
                fields = ", ".join(changed_facts[code])
                table.add_row(code, "[yellow]modified[/yellow]", fields)

        for code in sorted(deleted_facts):
            table.add_row(code, "[red]deleted[/red]", "—")

        console.print(table)

    modified_count = len(
        [c for c in changed_facts if c not in added_facts and c not in deleted_facts]
    )
    console.print(
        f"\n[dim]{modified_count} modified, "
        f"{len(added_facts)} added, "
        f"{len(deleted_facts)} deleted[/dim]"
    )


def log(
    code: Optional[str] = typer.Argument(
        None, help="Fact code (e.g., ADR-03). Omit for all facts."
    ),
    limit: int = typer.Option(20, "--limit", "-n", help="Max entries to show"),
):
    """Show git history for lattice facts."""
    store = require_local_lattice()

    if not _check_git():
        _git_error_message()

    facts_path = str(store.root / "facts")

    if code:
        fact_file = str(store.root / "facts" / f"{code}.yaml")
        cmd = ["git", "log", "--oneline", "--no-decorate", "--follow", f"-{limit}", "--", fact_file]
    else:
        cmd = ["git", "log", "--oneline", "--no-decorate", f"-{limit}", "--", facts_path]

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        err_console.print(f"[red]Error:[/red] git log failed: {result.stderr.strip()}")
        raise typer.Exit(1)

    output = result.stdout.strip()
    if not output:
        if code:
            console.print(f"[dim]No git history found for {code}.[/dim]")
        else:
            console.print("[dim]No git history found for lattice facts.[/dim]")
        return

    # Format output with Rich
    if code:
        console.print(f"[bold]Git history for {code}[/bold]\n")
    else:
        console.print("[bold]Git history for lattice facts[/bold]\n")

    for line in output.splitlines():
        # Split hash from message
        parts = line.split(" ", 1)
        if len(parts) == 2:
            commit_hash, message = parts
            console.print(f"  [cyan]{commit_hash}[/cyan] {message}")
        else:
            console.print(f"  {line}")
