#!/bin/bash
# Stop hook: fires once when Claude finishes responding.
# Audits source file changes against lattice governance rules.
# Always reports findings to the user. Blocks (exit 2) on NEW source changes.
#
# Anti-loop: a stamp file records the fingerprint of already-audited changes.
# If the current changes match the stamp, we skip blocking to avoid an
# infinite re-prompt cycle (Stop fires → Claude responds → Stop fires again).

INPUT=$(cat)

# Derive project directory from this script's location (.claude/hooks/ -> project root)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." 2>/dev/null && pwd)"
cd "$PROJECT_DIR" 2>/dev/null || exit 0

# Check if .lattice/ exists (skip if not initialized)
if ! lattice status > /dev/null 2>&1; then
  exit 0
fi

STAMP_FILE="$PROJECT_DIR/.claude/.audit-stamp"

# Count modified source files
CODE_CHANGES=$(git diff --name-only -- src/ 2>/dev/null | wc -l)
NEW_CODE=$(git ls-files --others --exclude-standard -- src/ 2>/dev/null | wc -l)
TOTAL_CODE=$((CODE_CHANGES + NEW_CODE))

# Count modified fact files
FACT_CHANGES=$(git diff --name-only -- .lattice/facts/ 2>/dev/null | wc -l)
NEW_FACTS=$(git ls-files --others --exclude-standard -- .lattice/facts/ 2>/dev/null | wc -l)
TOTAL_FACTS=$((FACT_CHANGES + NEW_FACTS))

if [ "$TOTAL_CODE" -gt 0 ]; then
  # Build a fingerprint of current source changes (file list + content hash)
  FINGERPRINT=$(
    {
      git diff --name-only -- src/ 2>/dev/null
      git ls-files --others --exclude-standard -- src/ 2>/dev/null
    } | sort | md5sum | cut -d' ' -f1
  )

  # Check if we already audited this exact set of changes
  ALREADY_AUDITED=false
  if [ -f "$STAMP_FILE" ] && [ "$(cat "$STAMP_FILE" 2>/dev/null)" = "$FINGERPRINT" ]; then
    ALREADY_AUDITED=true
  fi

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
  echo "## Remediation"
  echo ""
  echo "If a violation is found, there are two categories of remediation:"
  echo ""
  echo "### Code fixes (autonomous)"
  echo "If the violation can be resolved by changing source code to comply with an"
  echo "existing governance rule, you MAY fix the code directly without asking."
  echo ""
  echo "### Fact changes (require developer approval)"
  echo "If the violation suggests a gap in governance (missing rule, outdated fact,"
  echo "or obsolete procedure), you MUST NOT create, update, or deprecate facts on"
  echo "your own. Instead, present the developer with your recommendation and options:"
  echo ""
  echo "  1. **Create a new fact** — suggest the code, layer, type, and summary."
  echo "     Example: 'I recommend creating DG-12 (Data Governance) to cover X.'"
  echo "  2. **Update an existing fact** — identify which fact and what should change."
  echo "     Example: 'RISK-03 should be updated to include mitigation for Y.'"
  echo "  3. **Deprecate an existing fact** — explain why it is no longer relevant."
  echo "     Example: 'ADR-05 is superseded by the new approach — recommend deprecation.'"
  echo ""
  echo "Always wait for the developer to approve, modify, or reject your recommendation"
  echo "before making any changes to lattice facts."
  echo ""
  echo "## Reporting"
  echo ""
  echo "After the audit, report your findings to the user in a brief summary like:"
  echo "  'Governance audit: 4 files reviewed — all compliant with DG-10, RISK-03.'"
  echo "  'Governance audit: violation in X — fixed code to comply with RISK-03.'"
  echo "  'Governance audit: gap found — recommending new fact DG-12 (awaiting approval).'"

  if [ "$TOTAL_FACTS" -gt 0 ]; then
    echo ""
    echo "Note: $TOTAL_FACTS lattice fact(s) also have uncommitted changes."
  fi

  # Write stamp so next firing recognizes these changes were already audited
  echo "$FINGERPRINT" > "$STAMP_FILE"

  if [ "$ALREADY_AUDITED" = true ]; then
    # Same changes already audited — don't block, just inform
    echo ""
    echo "(These changes were already audited in a prior turn. Reporting only.)"
    exit 0
  else
    # New source changes — block to force Claude to report the audit
    exit 2
  fi
fi

# No source changes — clean up any stale stamp and report
rm -f "$STAMP_FILE" 2>/dev/null
echo "# GOVERNANCE AUDIT: CLEAN"
echo ""
echo "No source files were modified. No compliance audit needed."
echo "Briefly inform the user: 'No source changes — governance audit not required.'"
exit 0
