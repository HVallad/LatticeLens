#!/bin/bash
# PostToolUse hook (Edit|Write): validates lattice integrity after file changes.
# Silent on pass, blocks (exit 2) on validation failure.

INPUT=$(cat)

# Derive project directory from this script's location (.claude/hooks/ -> project root)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." 2>/dev/null && pwd)"
cd "$PROJECT_DIR" 2>/dev/null || exit 0

# Check if .lattice/ exists (skip if not initialized)
if ! lattice status > /dev/null 2>&1; then
  exit 0
fi

# Run lattice validation
RESULT=$(lattice validate 2>&1)
EXIT_CODE=$?

if [ $EXIT_CODE -ne 0 ]; then
  echo "# Governance Audit: FAILED"
  echo ""
  echo "lattice validate found issues. You MUST fix these before continuing:"
  echo ""
  echo "$RESULT"
  exit 2
fi

# Silent on pass — the Stop hook handles the compliance audit
exit 0
