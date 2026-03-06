#!/bin/bash
# Post-task governance audit: validates lattice integrity after implementation.
# Runs on TaskCompleted — blocks completion (exit 2) if validation fails.

INPUT=$(cat)

# Check if .lattice/ exists (skip audit if not initialized)
if ! lattice status > /dev/null 2>&1; then
  exit 0
fi

# Run lattice validation
RESULT=$(lattice validate 2>&1)
EXIT_CODE=$?

if [ $EXIT_CODE -ne 0 ]; then
  echo "Governance audit FAILED. Fix issues before completing task:" >&2
  echo "$RESULT" >&2
  exit 2
fi

# Check for uncommitted fact changes that might indicate missing governance updates
FACT_CHANGES=$(git diff --name-only -- .lattice/facts/ 2>/dev/null | wc -l)
NEW_FACTS=$(git ls-files --others --exclude-standard -- .lattice/facts/ 2>/dev/null | wc -l)

if [ "$FACT_CHANGES" -gt 0 ] || [ "$NEW_FACTS" -gt 0 ]; then
  echo "Governance audit passed. Note: $((FACT_CHANGES + NEW_FACTS)) lattice fact(s) have uncommitted changes." >&2
fi

exit 0
