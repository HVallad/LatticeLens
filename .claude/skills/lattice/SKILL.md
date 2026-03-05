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

### Deprecating (no hard deletes)

```bash
lattice fact deprecate ADR-03 --reason "Superseded by ADR-04"
```

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

## Directory Structure

```
.lattice/
├── config.yaml          # Backend settings
├── facts/               # One YAML file per fact ({CODE}.yaml)
├── roles/               # Role query templates for context assembly
├── history/             # changelog.jsonl (append-only audit log)
├── index.yaml           # Generated index (in .gitignore)
└── .gitignore
```

The entire `.lattice/` directory is designed to be committed to git and work after `git clone`.

If the user asked about something specific: $ARGUMENTS
