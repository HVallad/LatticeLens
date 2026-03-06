"""Typer app entrypoint."""

from __future__ import annotations

import typer

from lattice_lens.cli.context_commands import context
from lattice_lens.cli.evaluate_command import evaluate
from lattice_lens.cli.exchange_commands import export_cmd, import_cmd
from lattice_lens.cli.extract_command import extract
from lattice_lens.cli.fact_commands import fact_app
from lattice_lens.cli.git_commands import diff, log
from lattice_lens.cli.graph_commands import graph_app
from lattice_lens.cli.init_command import init
from lattice_lens.cli.seed_command import seed
from lattice_lens.cli.status_command import status
from lattice_lens.cli.upgrade_command import upgrade
from lattice_lens.cli.validate_command import reindex, validate

app = typer.Typer(
    name="lattice",
    help="LatticeLens — Knowledge governance for AI agent systems.",
    no_args_is_help=True,
)

app.add_typer(fact_app, name="fact", help="Manage facts (add, get, ls, edit, promote, deprecate).")
app.add_typer(graph_app, name="graph", help="Knowledge graph analysis.")
app.command()(init)
app.command()(validate)
app.command()(reindex)
app.command()(seed)
app.command()(status)
app.command()(diff)
app.command("log")(log)
app.command()(upgrade)
app.command()(context)
app.command()(evaluate)
app.command()(extract)
app.command("export")(export_cmd)
app.command("import")(import_cmd)


if __name__ == "__main__":
    app()
