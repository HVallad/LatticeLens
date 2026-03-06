#!/bin/bash
# Post-task governance audit: validates lattice integrity after implementation.
# Runs on TaskCompleted — stdout is injected into agent context.
# Blocks completion (exit 2) if validation fails.

INPUT=$(cat)

# Check if .lattice/ exists (skip audit if not initialized)
if ! lattice status > /dev/null 2>&1; then
  exit 0
fi

# Run lattice validation
RESULT=$(lattice validate 2>&1)
EXIT_CODE=$?

if [ $EXIT_CODE -ne 0 ]; then
  echo "# Governance Audit: FAILED"
  echo ""
  echo "lattice validate found issues. You MUST fix these before completing the task:"
  echo ""
  echo "$RESULT"
  exit 2
fi

# Build audit report (stdout = injected into agent context)
echo "# Governance Audit: PASSED"
echo ""
echo "lattice validate: all checks passed."

# Check for modified source files that might need new/updated facts
CODE_CHANGES=$(git diff --name-only -- src/ 2>/dev/null | wc -l)
NEW_CODE=$(git ls-files --others --exclude-standard -- src/ 2>/dev/null | wc -l)
TOTAL_CODE=$((CODE_CHANGES + NEW_CODE))

if [ "$TOTAL_CODE" -gt 0 ]; then
  echo ""
  echo "## Action Required: Verify Governance Compliance"
  echo ""
  echo "$TOTAL_CODE source file(s) were changed. Review the changes against the lattice facts"
  echo "and confirm that no governance rules were violated. If new architectural decisions,"
  echo "risks, or procedures were introduced, add corresponding Draft facts."
fi

# Note uncommitted fact changes
FACT_CHANGES=$(git diff --name-only -- .lattice/facts/ 2>/dev/null | wc -l)
NEW_FACTS=$(git ls-files --others --exclude-standard -- .lattice/facts/ 2>/dev/null | wc -l)
TOTAL_FACTS=$((FACT_CHANGES + NEW_FACTS))

if [ "$TOTAL_FACTS" -gt 0 ]; then
  echo ""
  echo "Note: $TOTAL_FACTS lattice fact(s) have uncommitted changes."
fi

exit 0
