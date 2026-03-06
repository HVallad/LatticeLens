#!/bin/bash
# Stop hook: fires once when Claude finishes responding.
# Checks if source files were modified and forces a governance compliance audit.
# Blocks (exit 2) if source changes exist, requiring Claude to explicitly audit.

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

if [ "$TOTAL_CODE" -gt 0 ]; then
  echo "# COMPLIANCE AUDIT REQUIRED"
  echo ""
  echo "You modified $TOTAL_CODE source file(s) in this response:"
  echo ""
  git diff --name-only -- src/ 2>/dev/null
  git ls-files --others --exclude-standard -- src/ 2>/dev/null
  echo ""
  echo "You MUST audit these changes against the lattice governance rules before finishing."
  echo "For each changed file, state which governance rules apply and confirm no violations."
  echo "If new architectural decisions, risks, or procedures were introduced, create Draft facts."
  echo ""
  echo "After completing the audit, state: 'Governance audit complete — no violations found.'"
  echo "or describe the violations and remediation steps taken."

  # Note uncommitted fact changes too
  FACT_CHANGES=$(git diff --name-only -- .lattice/facts/ 2>/dev/null | wc -l)
  NEW_FACTS=$(git ls-files --others --exclude-standard -- .lattice/facts/ 2>/dev/null | wc -l)
  TOTAL_FACTS=$((FACT_CHANGES + NEW_FACTS))

  if [ "$TOTAL_FACTS" -gt 0 ]; then
    echo ""
    echo "Note: $TOTAL_FACTS lattice fact(s) also have uncommitted changes."
  fi

  exit 2
fi

exit 0
