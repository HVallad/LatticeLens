"""lattice validate + reindex commands."""

from __future__ import annotations

import typer
from rich.console import Console
from ruamel.yaml import YAML

from lattice_lens.cli.helpers import is_lens_mode, require_lattice, require_local_lattice
from lattice_lens.config import INDEX_FILE
from lattice_lens.services.validate_service import fix_lattice, validate_lattice

console = Console()
err_console = Console(stderr=True)
yaml_writer = YAML()
yaml_writer.default_flow_style = False


def validate(
    fix: bool = typer.Option(False, "--fix", help="Auto-fix correctable issues"),
):
    """Check lattice integrity: YAML parsing, refs, tags, staleness."""
    # In lens mode, delegate to remote validation (--fix is not supported)
    if is_lens_mode():
        if fix:
            err_console.print(
                "[red]Error:[/red] 'validate --fix' is not available in lens mode.\n"
                "Fixes must be applied on the remote lattice server."
            )
            raise typer.Exit(1)

        # Call remote validation via the LensStore
        store = require_lattice()
        from lattice_lens.mcp.tools import tool_lattice_validate

        result_data = tool_lattice_validate(store)
        if result_data.get("errors"):
            console.print(f"\n[red]Errors ({len(result_data['errors'])}):[/red]")
            for e in result_data["errors"]:
                console.print(f"  [red]\u2717[/red] {e}")
        if result_data.get("warnings"):
            console.print(f"\n[yellow]Warnings ({len(result_data['warnings'])}):[/yellow]")
            for w in result_data["warnings"]:
                console.print(f"  [yellow]\u2022[/yellow] {w}")
        if result_data.get("ok") and not result_data.get("warnings"):
            console.print("[green]All checks passed.[/green]")
        elif result_data.get("ok"):
            console.print(
                f"\n[green]No errors.[/green] {len(result_data.get('warnings', []))} warning(s)."
            )
        else:
            console.print(
                f"\n[red]{len(result_data.get('errors', []))} error(s)[/red], "
                f"{len(result_data.get('warnings', []))} warning(s)."
            )
            raise typer.Exit(1)
        return

    store = require_lattice()
    facts_dir = store.facts_dir

    if fix:
        fix_result, files_fixed = fix_lattice(facts_dir)
        if files_fixed:
            console.print(f"[green]Fixed[/green] {files_fixed} file(s)")
        for w in fix_result.warnings:
            console.print(f"  [yellow]•[/yellow] {w}")

    result = validate_lattice(facts_dir)

    if result.errors:
        console.print(f"\n[red]Errors ({len(result.errors)}):[/red]")
        for e in result.errors:
            console.print(f"  [red]✗[/red] {e}")

    if result.warnings:
        console.print(f"\n[yellow]Warnings ({len(result.warnings)}):[/yellow]")
        for w in result.warnings:
            console.print(f"  [yellow]•[/yellow] {w}")

    if result.ok and not result.warnings:
        console.print("[green]All checks passed.[/green]")
    elif result.ok:
        console.print(f"\n[green]No errors.[/green] {len(result.warnings)} warning(s).")
    else:
        console.print(
            f"\n[red]{len(result.errors)} error(s)[/red], {len(result.warnings)} warning(s)."
        )
        raise typer.Exit(1)


def reindex():
    """Rebuild index.yaml from scanning all fact files."""
    store = require_local_lattice()

    # Force rebuild
    store.invalidate_index()
    index = store.index

    # Write index.yaml
    facts = index.all_facts()
    tag_index: dict[str, list[str]] = {}
    layer_groups: dict[str, list[str]] = {}
    refs_forward: dict[str, list[str]] = {}
    refs_reverse: dict[str, list[str]] = {}
    by_status: dict[str, int] = {}
    by_layer: dict[str, int] = {}

    for f in facts:
        for tag in f.tags:
            tag_index.setdefault(tag, []).append(f.code)
        layer_groups.setdefault(f.layer.value, []).append(f.code)
        if f.refs:
            refs_forward[f.code] = f.ref_codes
        for ref in f.refs:
            refs_reverse.setdefault(ref.code, []).append(f.code)
        by_status[f.status.value] = by_status.get(f.status.value, 0) + 1
        by_layer[f.layer.value] = by_layer.get(f.layer.value, 0) + 1

    index_data = {
        "generated_at": __import__("datetime").datetime.now().isoformat(),
        "total_facts": len(facts),
        "by_layer": by_layer,
        "by_status": by_status,
        "tag_index": {k: sorted(v) for k, v in sorted(tag_index.items())},
        "layer_groups": {k: sorted(v) for k, v in sorted(layer_groups.items())},
        "refs_forward": {k: sorted(v) for k, v in sorted(refs_forward.items())},
        "refs_reverse": {k: sorted(v) for k, v in sorted(refs_reverse.items())},
    }

    index_path = store.root / INDEX_FILE
    with open(index_path, "w") as f:
        yaml_writer.dump(index_data, f)

    console.print(f"[green]Rebuilt[/green] {index_path} ({len(facts)} facts indexed)")
