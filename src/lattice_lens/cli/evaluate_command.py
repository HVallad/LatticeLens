"""lattice evaluate — governance evaluation for Claude Code hooks.

When invoked as a Claude Code ``UserPromptSubmit`` hook the command reads
the hook payload from *stdin*, locates the project's ``.lattice/``
directory, and prints a governance briefing to *stdout*.  Claude Code
captures that stdout and injects it as context the model sees before
processing the user's prompt.

Can also be run standalone for debugging or manual evaluation::

    lattice evaluate              # text briefing
    lattice evaluate --json       # JSON output
    lattice evaluate --verbose    # diagnostics on stderr
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

from lattice_lens.services.evaluate_service import (
    evaluate_governance,
    parse_hook_input,
)

err_console = Console(stderr=True)


def evaluate(
    as_json: bool = typer.Option(False, "--json", help="Output governance briefing as JSON."),
    path: Optional[Path] = typer.Option(
        None,
        "--path",
        help="Directory to evaluate (default: hook stdin cwd, or cwd).",
    ),
    verbose: bool = typer.Option(False, "--verbose", help="Print diagnostics to stderr."),
) -> None:
    """Evaluate governance rules for Claude Code hook injection.

    When used as a Claude Code UserPromptSubmit hook, reads stdin JSON to
    get the project directory.  When used standalone, uses --path or the
    current working directory.

    Exit codes:
      0 — success (stdout may have governance briefing, or empty if no lattice)
    """
    target_path: Path | None = path

    # Try reading stdin for hook mode (non-interactive only)
    if target_path is None:
        try:
            if not sys.stdin.isatty():
                stdin_data = sys.stdin.read()
                hook_input = parse_hook_input(stdin_data)
                if hook_input and hook_input.cwd:
                    target_path = Path(hook_input.cwd)
                    if verbose:
                        err_console.print(
                            f"[dim]Hook mode: cwd={hook_input.cwd}, "
                            f"event={hook_input.hook_event_name}[/dim]"
                        )
        except Exception:
            # Never crash on stdin issues — fall through to cwd discovery
            pass

    # Run the evaluation
    result = evaluate_governance(start_path=target_path)

    if verbose:
        err_console.print(
            f"[dim]Lattice found: {result.lattice_found}, "
            f"guardrails: {len(result.guardrails)}, "
            f"tokens: {result.total_tokens}, "
            f"roles: {len(result.available_roles)}[/dim]"
        )

    # Output — always exit 0.  Empty stdout = silent no-op for the hook.
    if as_json:
        sys.stdout.write(json.dumps(result.to_dict(), indent=2))
        sys.stdout.write("\n")
    else:
        briefing = result.render_briefing()
        if briefing:
            sys.stdout.write(briefing)
            sys.stdout.write("\n")
