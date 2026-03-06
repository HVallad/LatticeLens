#!/bin/bash
# Stop hook: fires once when Claude finishes responding.
# Audits source file changes against lattice governance rules.
# Always reports findings to the user. Blocks (exit 2) if source changes need audit.

INPUT=$(cat)

# Derive project directory from this script's location (.claude/hooks/ -> project root)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." 2>/dev/null && pwd)"
cd "$PROJECT_DIR" 2>/dev/null || exit 0

# Check if .lattice/ exists (skip if not initialized)
if ! lattice status > /dev/null 2>&1; then
  exit 0
fi

# Count modified source files
CODE_CHANGES=$(git diff --name-only -- src/ 2>/dev/null | wc -l)
NEW_CODE=$(git ls-files --others --exclude-standard -- src/ 2>/dev/null | wc -l)
TOTAL_CODE=$((CODE_CHANGES + NEW_CODE))

# Count modified fact files
FACT_CHANGES=$(git diff --name-only -- .lattice/facts/ 2>/dev/null | wc -l)
NEW_FACTS=$(git ls-files --others --exclude-standard -- .lattice/facts/ 2>/dev/null | wc -l)
TOTAL_FACTS=$((FACT_CHANGES + NEW_FACTS))

if [ "$TOTAL_CODE" -gt 0 ]; then
  echo "# GOVERNANCE COMPLIANCE AUDIT"
  echo ""
  echo "$TOTAL_CODE source file(s) were modified:"
  echo ""
  git diff --name-only -- src/ 2>/dev/null
  git ls-files --others --exclude-standard -- src/ 2>/dev/null
  echo ""
  echo "## Instructions"
  echo ""
  echo "You MUST audit each changed file against the lattice governance rules and report"
  echo "your findings to the user. For each file:"
  echo ""
  echo "1. Identify which governance rules (AUP, DG, RISK, etc.) are relevant"
  echo "2. Confirm compliance OR identify violations"
  echo ""
  echo "If a violation is found, you MUST either:"
  echo "  - Fix the code to comply with the governance rule, OR"
  echo "  - Create/update a Draft fact to document a new decision, risk, or procedure"
  echo ""
  echo "After the audit, report your findings to the user in a brief summary like:"
  echo "  'Governance audit: 4 files reviewed — all compliant with DG-10, RISK-03.'"
  echo "  or: 'Governance audit: violation found in X — fixed by updating Y.'"

  if [ "$TOTAL_FACTS" -gt 0 ]; then
    echo ""
    echo "Note: $TOTAL_FACTS lattice fact(s) also have uncommitted changes."
  fi

  exit 2
fi

# No source changes — still report to the user for transparency
echo "# GOVERNANCE AUDIT: CLEAN"
echo ""
echo "No source files were modified. No compliance audit needed."
echo "Briefly inform the user: 'No source changes — governance audit not required.'"
exit 0
