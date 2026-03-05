---
name: lattice
description: Guide for using LatticeLens — the knowledge governance CLI. Use when the user asks about creating, querying, editing, or managing facts in a .lattice/ knowledge base.
user-invocable: true
argument-hint: "[command or question]"
---

# LatticeLens Usage Guide

LatticeLens is a git-native knowledge governance layer for AI agent systems. It stores atomic facts as individual YAML files in a `.lattice/` directory, organized into three layers: **WHY** (decisions, requirements), **GUARDRAILS** (constraints, policies, risks), and **HOW** (procedures, specs, runbooks).

## Setup

```bash
# Install (from the lattice-lens repo root)
pip install -e .

# Initialize a lattice in any project
lattice init

# Load 12 example facts + placeholder drafts
lattice seed
```

## Fact Lifecycle

### Creating facts

```bash
# Interactive — prompts for each field
lattice fact add

# From a YAML file
lattice fact add --from path/to/fact.yaml
```

A fact YAML file looks like:

```yaml
code: RISK-07
layer: GUARDRAILS
type: Risk Assessment Finding
fact: >-
  Prompt injection via user-uploaded documents rated HIGH severity.
  Mitigation: input sanitization + document content sandboxing.
tags:
- security
- prompt-injection
status: Active
confidence: Confirmed
owner: security-team
refs:
- ADR-03
- SP-03
review_by: 2026-06-01
```

**Required fields**: code, layer, type, fact (min 10 chars), tags (min 2), owner.

**Code prefixes by layer**:
- WHY: ADR, PRD, ETH, DES
- GUARDRAILS: MC, AUP, RISK, DG, COMP
- HOW: SP, API, RUN, ML, MON

### Reading facts

```bash
# Rich panel display
lattice fact get ADR-01

# JSON output (for piping to jq, feeding to agents, etc.)
lattice fact get ADR-01 --json
```

### Listing and filtering

```bash
# All non-deprecated facts
lattice fact ls

# Filter by layer
lattice fact ls --layer WHY
lattice fact ls --layer GUARDRAILS

# Filter by tag
lattice fact ls --tag security

# Filter by status
lattice fact ls --status Draft

# Filter by type
lattice fact ls --type "Risk Assessment Finding"

# JSON array output
lattice fact ls --json
```

### Editing

```bash
# Opens in $EDITOR, validates on save, auto-bumps version
lattice fact edit ADR-03
```

### Promoting through lifecycle

```bash
# Draft -> Under Review (one step per invocation)
lattice fact promote ADR-03 --reason "Ready for peer review"

# Under Review -> Active
lattice fact promote ADR-03 --reason "Reviewed and approved"
```

New facts default to `Draft`. They must be promoted through `Under Review` to `Active` before they appear in agent context. The `--reason` flag is required.

### Deprecating (no hard deletes)

```bash
lattice fact deprecate ADR-03 --reason "Superseded by ADR-04"
```

## Knowledge Graph (Phase 2)

### Impact analysis

```bash
# What breaks if I change ADR-03?
lattice graph impact ADR-03

# Limit traversal depth (default: 3)
lattice graph impact ADR-03 --depth 1

# JSON output
lattice graph impact ADR-03 --json
```

Shows directly affected facts (those that reference the code), transitively affected facts (2+ hops away), and which agent roles would be impacted.

### Orphan detection

```bash
# Find facts with no references in or out
lattice graph orphans

# JSON list of orphan codes
lattice graph orphans --json
```

### Contradiction candidates

```bash
# Find active fact pairs sharing 2+ tags across different layers/owners
lattice graph contradictions

# Adjust sensitivity (default: 2 shared tags)
lattice graph contradictions --min-tags 3

# JSON output
lattice graph contradictions --json
```

These are candidates for human review — not confirmed contradictions.

## Context Assembly (Phase 3)

Assemble governed, token-budgeted facts for an agent role:

```bash
# Assemble facts for the planning role
lattice context planning

# With a token budget — loads highest-priority facts first
lattice context planning --budget 4000

# JSON output for piping into agent prompts
lattice context planning --json
```

**Priority loading** (per AUP-07):
1. Confirmed facts first, sorted by tag relevance to the role
2. Provisional facts if budget remains
3. Never Draft, Deprecated, or Superseded

Facts that exist but weren't loaded are listed as **REFS pointers** so the agent knows what it's missing.

Available roles are defined in `.lattice/roles/*.yaml`. Default roles: `planning`, `architecture`, `implementation`, `qa`, `deploy`.

## Git Integration (Phase 2)

### Fact-level diffs

```bash
# Show which facts changed (unstaged)
lattice diff

# Show only staged changes
lattice diff --staged
```

Parses `git diff` scoped to `.lattice/facts/` and shows a summary: which fact codes changed, which fields, and counts of added/modified/deleted.

### Fact history

```bash
# Recent changes to any fact
lattice log

# History of a specific fact
lattice log ADR-03

# Limit entries (default: 20)
lattice log --limit 5
```

## Upgrading

```bash
# Migrate lattice to latest schema version
lattice upgrade
```

Runs versioned migrations (e.g., v0.1.0 → v0.2.0 role template format change). Safe to run at any time — idempotent and skips already-applied migrations. The current version is tracked in `.lattice/config.yaml`.

## Validation and Maintenance

```bash
# Check integrity: YAML parsing, refs, schemas, staleness
lattice validate

# Auto-fix tags (normalize to lowercase, sort, deduplicate)
lattice validate --fix

# Rebuild the index file
lattice reindex

# Show summary: backend, counts by layer/status, stale count
lattice status
```

## Business Rules

These are enforced on every write:

1. Code prefix must match its layer (e.g., ADR-* must be in WHY)
2. Tags are always normalized to lowercase, sorted, deduplicated
3. Version increments by exactly 1 on each update
4. Codes are immutable after creation
5. Deprecation is a soft delete — the YAML file is never removed
6. Facts past their `review_by` date are flagged as stale
7. Every mutation appends to `history/changelog.jsonl`
8. Status "Superseded" requires `superseded_by` to be set
9. Refs to non-existent codes produce warnings (not errors)
10. `created_at` is never modified after initial creation

## Role Templates (Phase 2 format)

Role templates in `.lattice/roles/*.yaml` define which facts matter to each agent role. Used by `lattice graph impact` to determine affected roles.

```yaml
# .lattice/roles/planning.yaml
name: Planning Agent
description: "Product Strategist — scopes work, defines acceptance criteria"
query:
  layers: ["WHY"]
  types: ["Architecture Decision Record", "Product Requirement"]
  tags: ["architecture", "scaling", "performance-requirement"]
  max_facts: 20
  extra:
    - layer: "GUARDRAILS"
      types: ["Acceptable Use Policy Rule"]
```

Five default roles are created by `lattice init`: planning, architecture, implementation, qa, deploy.

## Directory Structure

```
.lattice/
├── config.yaml          # Backend settings + schema version
├── facts/               # One YAML file per fact ({CODE}.yaml)
├── roles/               # Role query templates (planning, architecture, etc.)
├── history/             # changelog.jsonl (append-only audit log)
├── index.yaml           # Generated index (in .gitignore)
└── .gitignore
```

The entire `.lattice/` directory is designed to be committed to git and work after `git clone`.

If the user asked about something specific: $ARGUMENTS
