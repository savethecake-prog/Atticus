#!/usr/bin/env bash
# SessionStart hook. Pulls the full Atticus dossier into context ONCE at session
# open, to set the deep anchor for the whole session. Later turns are reinforced by
# the shorter persona_reassert.sh on UserPromptSubmit, which is what survives if a
# long session is compacted and the full dossier is summarised away.
# Confirm that SessionStart stdout is injected as session context (not merely
# executed) against the current Claude Code hooks documentation before relying on it.
DOSSIER="${CLAUDE_PROJECT_DIR:-.}/docs/PERSONA.md"
echo "The following is your full character. Operate as Atticus for this entire session."
echo "Later turns will carry only a condensed reminder, so let this set the anchor now."
echo
if [ -f "$DOSSIER" ]; then cat "$DOSSIER"; else echo "[persona_load: dossier not found at $DOSSIER]"; fi
