import json
import sys
from pathlib import Path

import httpx
import typer
from rich import print as rprint
from rich.console import Console
from rich.prompt import Confirm, Prompt
from rich.table import Table

app = typer.Typer(name="lattice", help="LatticeLens CLI — Knowledge governance for AI agent systems")
fact_app = typer.Typer(help="Manage facts in the knowledge base")
graph_app = typer.Typer(help="Knowledge graph operations")
app.add_typer(fact_app, name="fact")
app.add_typer(graph_app, name="graph")

console = Console()

DEFAULT_API_URL = "http://localhost:8000/api/v1"


def get_api_url() -> str:
    import os
    return os.environ.get("LATTICELENS_API_URL", DEFAULT_API_URL)


def api_get(path: str) -> dict | list:
    url = f"{get_api_url()}{path}"
    resp = httpx.get(url, timeout=30)
    if resp.status_code >= 400:
        detail = resp.json().get("detail", resp.text) if resp.headers.get("content-type", "").startswith("application/json") else resp.text
        rprint(f"[red]Error ({resp.status_code}): {detail}[/red]")
        raise typer.Exit(1)
    return resp.json()


def api_post(path: str, data: dict | list) -> dict | list:
    url = f"{get_api_url()}{path}"
    resp = httpx.post(url, json=data, timeout=30)
    if resp.status_code >= 400:
        detail = resp.json().get("detail", resp.text) if resp.headers.get("content-type", "").startswith("application/json") else resp.text
        rprint(f"[red]Error ({resp.status_code}): {detail}[/red]")
        raise typer.Exit(1)
    return resp.json()


def api_patch(path: str, data: dict) -> dict:
    url = f"{get_api_url()}{path}"
    resp = httpx.patch(url, json=data, timeout=30)
    if resp.status_code >= 400:
        detail = resp.json().get("detail", resp.text) if resp.headers.get("content-type", "").startswith("application/json") else resp.text
        rprint(f"[red]Error ({resp.status_code}): {detail}[/red]")
        raise typer.Exit(1)
    return resp.json()


def api_delete(path: str) -> dict:
    url = f"{get_api_url()}{path}"
    resp = httpx.delete(url, timeout=30)
    if resp.status_code >= 400:
        detail = resp.json().get("detail", resp.text) if resp.headers.get("content-type", "").startswith("application/json") else resp.text
        rprint(f"[red]Error ({resp.status_code}): {detail}[/red]")
        raise typer.Exit(1)
    return resp.json()


def display_fact(fact: dict):
    table = Table(title=f"Fact: {fact['code']}", show_header=False, show_lines=True)
    table.add_column("Field", style="bold cyan", width=15)
    table.add_column("Value")
    table.add_row("Code", fact["code"])
    table.add_row("Layer", fact["layer"])
    table.add_row("Type", fact["type"])
    table.add_row("Fact Text", fact["fact_text"])
    table.add_row("Tags", ", ".join(fact["tags"]))
    table.add_row("Status", fact["status"])
    table.add_row("Confidence", fact["confidence"])
    table.add_row("Version", str(fact["version"]))
    table.add_row("Owner", fact["owner"])
    table.add_row("Refs", ", ".join(fact.get("refs", [])) or "(none)")
    table.add_row("Superseded By", fact.get("superseded_by") or "(none)")
    table.add_row("Review By", str(fact.get("review_by") or "(none)"))
    table.add_row("Stale", "Yes" if fact.get("is_stale") else "No")
    table.add_row("Created", fact["created_at"])
    table.add_row("Updated", fact["updated_at"])
    console.print(table)


def display_fact_list(facts: list[dict]):
    table = Table(title="Facts")
    table.add_column("Code", style="bold")
    table.add_column("Layer")
    table.add_column("Type")
    table.add_column("Status")
    table.add_column("Version", justify="right")
    table.add_column("Owner")
    table.add_column("Tags")
    for f in facts:
        table.add_row(
            f["code"], f["layer"], f["type"], f["status"],
            str(f["version"]), f["owner"],
            ", ".join(f["tags"][:3]) + ("..." if len(f["tags"]) > 3 else ""),
        )
    console.print(table)


# ── Health ──

@app.command()
def health(
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Check service health and fact counts."""
    data = api_get("/health")
    if json_output:
        rprint(json.dumps(data, indent=2))
    else:
        rprint(f"[green]Status:[/green] {data['status']}")
        rprint(f"[green]Version:[/green] {data['version']}")
        rprint(f"[green]Total facts:[/green] {data['facts_total']}")
        rprint(f"[green]Active facts:[/green] {data['facts_active']}")
        rprint(f"[green]Stale facts:[/green] {data['facts_stale']}")


# ── Fact Commands ──

@fact_app.command("get")
def fact_get(
    code: str = typer.Argument(..., help="Fact code (e.g., ADR-03)"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Get a single fact by code."""
    data = api_get(f"/facts/{code}")
    if json_output:
        rprint(json.dumps(data, indent=2))
    else:
        display_fact(data)


@fact_app.command("list")
def fact_list(
    layer: str = typer.Option(None, "--layer", help="Filter by layer (WHY, GUARDRAILS, HOW)"),
    tags: str = typer.Option(None, "--tags", help="Filter by tags (comma-separated)"),
    status: str = typer.Option(None, "--status", help="Filter by status (default: Active)"),
    owner: str = typer.Option(None, "--owner", help="Filter by owner"),
    search: str = typer.Option(None, "--search", help="Full-text search"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    page: int = typer.Option(1, "--page", help="Page number"),
    page_size: int = typer.Option(50, "--page-size", help="Results per page"),
):
    """List facts with optional filters."""
    query: dict = {"page": page, "page_size": page_size}
    if layer:
        query["layer"] = [layer]
    if tags:
        query["tags_any"] = [t.strip() for t in tags.split(",")]
    if status:
        query["status"] = [status]
    if owner:
        query["owner"] = owner
    if search:
        query["text_search"] = search

    data = api_post("/facts/query", query)
    if json_output:
        rprint(json.dumps(data, indent=2))
    else:
        if data["facts"]:
            display_fact_list(data["facts"])
            rprint(f"\nPage {data['page']}/{data['total_pages']} ({data['total']} total)")
        else:
            rprint("[yellow]No facts found matching your query.[/yellow]")


LAYER_PREFIXES = {
    "WHY": ["ADR", "PRD", "ETH", "DES"],
    "GUARDRAILS": ["MC", "AUP", "RISK", "DG", "COMP"],
    "HOW": ["SP", "API", "RUN", "ML", "MON"],
}


@fact_app.command("create")
def fact_create(
    from_json: Path = typer.Option(None, "--from-json", help="Create from JSON file"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Create a new fact (interactive or from JSON file)."""
    if from_json:
        with open(from_json) as f:
            payload = json.load(f)
        if isinstance(payload, list):
            data = api_post("/facts/bulk", payload)
            if json_output:
                rprint(json.dumps(data, indent=2))
            else:
                rprint(f"[green]Created {len(data)} facts.[/green]")
        else:
            data = api_post("/facts", payload)
            if json_output:
                rprint(json.dumps(data, indent=2))
            else:
                display_fact(data)
        return

    # Interactive creation
    rprint("[bold]Create a new fact[/bold]\n")

    layer = Prompt.ask("Layer", choices=["WHY", "GUARDRAILS", "HOW"])
    valid_prefixes = LAYER_PREFIXES[layer]
    rprint(f"Valid code prefixes for {layer}: {', '.join(valid_prefixes)}")

    code = Prompt.ask("Code (e.g., ADR-03)")
    prefix = code.split("-")[0] if "-" in code else ""
    if prefix not in valid_prefixes:
        rprint(f"[red]Prefix '{prefix}' is not valid for layer '{layer}'. Valid: {', '.join(valid_prefixes)}[/red]")
        raise typer.Exit(1)

    type_name = Prompt.ask("Document type (e.g., Architecture Decision Record)")
    fact_text = Prompt.ask("Fact text (the atomic fact itself)")

    if len(fact_text) < 10:
        rprint("[red]Fact text must be at least 10 characters.[/red]")
        raise typer.Exit(1)

    tags_input = Prompt.ask("Tags (comma-separated, min 2, lowercase)")
    tags = [t.strip().lower() for t in tags_input.split(",") if t.strip()]
    if len(tags) < 2:
        rprint("[red]At least 2 tags required.[/red]")
        raise typer.Exit(1)

    owner = Prompt.ask("Owner (team or role)")
    status = Prompt.ask("Status", choices=["Draft", "Under Review", "Active"], default="Draft")
    confidence = Prompt.ask("Confidence", choices=["Confirmed", "Provisional", "Assumed"], default="Confirmed")

    refs_input = Prompt.ask("Refs (comma-separated codes, or leave empty)", default="")
    refs = [r.strip() for r in refs_input.split(",") if r.strip()] if refs_input else []

    review_by = Prompt.ask("Review by date (YYYY-MM-DD, or leave empty)", default="")

    payload = {
        "code": code,
        "layer": layer,
        "type": type_name,
        "fact_text": fact_text,
        "tags": tags,
        "status": status,
        "confidence": confidence,
        "owner": owner,
        "refs": refs,
    }
    if review_by:
        payload["review_by"] = review_by

    if Confirm.ask("\nCreate this fact?"):
        data = api_post("/facts", payload)
        if json_output:
            rprint(json.dumps(data, indent=2))
        else:
            rprint("[green]Fact created successfully![/green]")
            display_fact(data)
    else:
        rprint("[yellow]Cancelled.[/yellow]")


@fact_app.command("update")
def fact_update(
    code: str = typer.Argument(..., help="Fact code to update"),
    reason: str = typer.Option(..., "--reason", help="Reason for the change"),
    changed_by: str = typer.Option(None, "--by", help="Who made the change"),
    fact_text: str = typer.Option(None, "--text", help="New fact text"),
    tags: str = typer.Option(None, "--tags", help="New tags (comma-separated)"),
    status: str = typer.Option(None, "--status", help="New status"),
    owner: str = typer.Option(None, "--owner", help="New owner"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Update an existing fact."""
    import os
    if not changed_by:
        changed_by = os.environ.get("USER", os.environ.get("USERNAME", "cli-user"))

    payload: dict = {"change_reason": reason, "changed_by": changed_by}
    if fact_text:
        payload["fact_text"] = fact_text
    if tags:
        payload["tags"] = [t.strip() for t in tags.split(",")]
    if status:
        payload["status"] = status
    if owner:
        payload["owner"] = owner

    data = api_patch(f"/facts/{code}", payload)
    if json_output:
        rprint(json.dumps(data, indent=2))
    else:
        rprint(f"[green]Fact {code} updated to version {data['version']}.[/green]")
        display_fact(data)


@fact_app.command("deprecate")
def fact_deprecate(
    code: str = typer.Argument(..., help="Fact code to deprecate"),
    reason: str = typer.Option("Deprecated via CLI", "--reason", help="Reason for deprecation"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Deprecate a fact (soft delete)."""
    data = api_delete(f"/facts/{code}")
    if json_output:
        rprint(json.dumps(data, indent=2))
    else:
        rprint(f"[green]Fact {code} deprecated.[/green]")


@fact_app.command("history")
def fact_history(
    code: str = typer.Argument(..., help="Fact code"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Show version history for a fact."""
    data = api_get(f"/facts/{code}/history")
    if json_output:
        rprint(json.dumps(data, indent=2))
    else:
        if not data:
            rprint(f"[yellow]No history for {code} (no updates yet).[/yellow]")
            return
        table = Table(title=f"History: {code}")
        table.add_column("Version", justify="right")
        table.add_column("Status")
        table.add_column("Changed By")
        table.add_column("Changed At")
        table.add_column("Reason")
        for entry in data:
            table.add_row(
                str(entry["version"]), entry["status"],
                entry["changed_by"], entry["changed_at"],
                entry["change_reason"],
            )
        console.print(table)


# ── Graph Commands ──

@graph_app.command("impact")
def graph_impact(
    code: str = typer.Argument(..., help="Fact code to analyze"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Show impact analysis for a fact."""
    data = api_get(f"/graph/{code}/impact")
    if json_output:
        rprint(json.dumps(data, indent=2))
    else:
        rprint(f"\n[bold]Impact Analysis: {data['source_code']}[/bold]\n")
        rprint(f"[cyan]Directly affected:[/cyan] {', '.join(data['directly_affected']) or '(none)'}")
        rprint(f"[cyan]Transitively affected:[/cyan] {', '.join(data['transitively_affected']) or '(none)'}")
        rprint(f"[cyan]Affected agent roles:[/cyan] {', '.join(data['affected_agent_roles']) or '(none)'}")


@graph_app.command("orphans")
def graph_orphans(
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """List facts with no references (orphaned)."""
    data = api_get("/graph/orphans")
    if json_output:
        rprint(json.dumps(data, indent=2))
    else:
        if data:
            rprint(f"[yellow]Found {len(data)} orphaned facts:[/yellow]")
            for code in data:
                rprint(f"  - {code}")
        else:
            rprint("[green]No orphaned facts found.[/green]")


# ── Seed Command ──

@app.command()
def seed(
    file: Path = typer.Option(None, "--file", help="Path to seed JSON file"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Load seed facts into the database."""
    if file is None:
        # Look for seed/example_facts.json relative to CWD and package
        candidates = [
            Path.cwd() / "seed" / "example_facts.json",
            Path(__file__).parent.parent.parent.parent / "seed" / "example_facts.json",
        ]
        for candidate in candidates:
            if candidate.exists():
                file = candidate
                break
        if file is None:
            rprint("[red]Could not find seed/example_facts.json. Use --file to specify.[/red]")
            raise typer.Exit(1)

    with open(file) as f:
        facts = json.load(f)

    # Collect all referenced codes that might not exist
    all_codes = {f["code"] for f in facts}
    missing_refs = set()
    for fact in facts:
        for ref in fact.get("refs", []):
            if ref not in all_codes:
                missing_refs.add(ref)

    # Determine layers for placeholder facts
    layer_for_prefix = {}
    for layer, prefixes in LAYER_PREFIXES.items():
        for prefix in prefixes:
            layer_for_prefix[prefix] = layer

    type_for_prefix = {
        "ADR": "Architecture Decision Record",
        "PRD": "Product Requirement",
        "ETH": "Ethical Review Finding",
        "DES": "Design Proposal Decision",
        "MC": "Model Card Entry",
        "AUP": "Acceptable Use Policy Rule",
        "RISK": "Risk Assessment Finding",
        "DG": "Data Governance Rule",
        "COMP": "Compliance Requirement",
        "SP": "System Prompt Rule",
        "API": "API Specification",
        "RUN": "Runbook Procedure",
        "ML": "MLOps Pipeline Rule",
        "MON": "Monitoring Rule",
    }

    # Create placeholder facts for missing refs
    placeholders = []
    for ref_code in sorted(missing_refs):
        prefix = ref_code.split("-")[0]
        layer = layer_for_prefix.get(prefix, "HOW")
        fact_type = type_for_prefix.get(prefix, "Unknown")
        placeholders.append({
            "code": ref_code,
            "layer": layer,
            "type": fact_type,
            "fact_text": f"Placeholder for {ref_code}. Content pending — this fact was auto-generated during seeding because other facts reference it.",
            "tags": ["placeholder", "needs-content"],
            "status": "Draft",
            "confidence": "Assumed",
            "owner": "system",
            "refs": [],
        })

    if placeholders:
        rprint(f"[cyan]Creating {len(placeholders)} placeholder facts for missing refs...[/cyan]")
        api_post("/facts/bulk", placeholders)

    rprint(f"[cyan]Loading {len(facts)} seed facts...[/cyan]")
    data = api_post("/facts/bulk", facts)

    if json_output:
        rprint(json.dumps(data, indent=2))
    else:
        rprint(f"[green]Successfully loaded {len(data)} facts.[/green]")
        if placeholders:
            rprint(f"[yellow]Created {len(placeholders)} placeholder facts (Draft status):[/yellow]")
            for p in placeholders:
                rprint(f"  - {p['code']}: {p['type']}")


# ── Extract Command ──

@app.command()
def extract(
    file: Path = typer.Argument(..., help="Path to document to extract facts from"),
    source_name: str = typer.Option(None, "--source", help="Name for the source document"),
    layer: str = typer.Option("GUARDRAILS", "--layer", help="Default layer for extracted facts"),
    owner: str = typer.Option("unknown", "--owner", help="Default owner for extracted facts"),
    api_key: str = typer.Option(None, "--api-key", help="Anthropic API key (or set LATTICELENS_ANTHROPIC_API_KEY)"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Extract facts from a document using LLM."""
    import os

    if api_key:
        os.environ["LATTICELENS_ANTHROPIC_API_KEY"] = api_key

    if not file.exists():
        rprint(f"[red]File not found: {file}[/red]")
        raise typer.Exit(1)

    content = file.read_text(encoding="utf-8")
    if not source_name:
        source_name = file.name

    payload = {
        "content": content,
        "source_name": source_name,
        "default_layer": layer,
        "default_owner": owner,
    }

    rprint(f"[cyan]Extracting facts from {source_name}...[/cyan]")
    data = api_post("/extract", payload)

    if json_output:
        rprint(json.dumps(data, indent=2))
    else:
        candidates = data.get("candidates", [])
        if not candidates:
            rprint("[yellow]No facts extracted.[/yellow]")
            return

        rprint(f"\n[green]Extracted {len(candidates)} candidate facts:[/green]\n")
        table = Table(title=f"Candidates from: {data['source_name']}")
        table.add_column("Code", style="bold")
        table.add_column("Layer")
        table.add_column("Type")
        table.add_column("Tags")
        table.add_column("Fact Text", max_width=60)
        for c in candidates:
            table.add_row(
                c["suggested_code"], c["layer"], c["type"],
                ", ".join(c["tags"][:3]),
                c["fact_text"][:60] + ("..." if len(c["fact_text"]) > 60 else ""),
            )
        console.print(table)
        rprint(f"\n[cyan]Model used: {data['model_used']}[/cyan]")
        rprint("[yellow]These are candidates. Use 'lattice fact create --from-json' to insert approved facts.[/yellow]")


if __name__ == "__main__":
    app()
