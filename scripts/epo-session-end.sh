#!/bin/bash
# EPO SessionEnd Hook -- Analyze, Learn, Inject, Export, Memory-Backup, Commit
# Runs automatically after every Claude Code session.
# Fehlertolerant: Kein Abbruch bei Fehlern, kein Output bei Erfolg.

# KEIN set -e -- jeder Befehl darf fehlschlagen ohne den Rest zu blockieren

# Only run if epo is installed
command -v epo >/dev/null 2>&1 || exit 0

# Only run in a git repo
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || exit 0

PROJECT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null)
PROJECT_NAME=$(basename "$PROJECT_ROOT")

# Public-Repo-Check: Kein EPO-Inject und kein Auto-Push in public Repos
IS_PUBLIC=false
ORIGIN_URL=$(git remote get-url origin 2>/dev/null || true)
if [ -n "$ORIGIN_URL" ]; then
    # GitHub-Repo-Name aus URL extrahieren (HTTPS + SSH)
    REPO_SLUG=$(echo "$ORIGIN_URL" | sed -E 's|.*github\.com[:/]||; s|\.git$||')
    if [ -n "$REPO_SLUG" ]; then
        VISIBILITY=$(gh repo view "$REPO_SLUG" --json visibility -q '.visibility' 2>/dev/null || true)
        if [ "$VISIBILITY" = "PUBLIC" ]; then
            IS_PUBLIC=true
        fi
    fi
fi

# Analyze + Learn laufen immer (lokale DB, kein Leak-Risiko)
epo analyze --catchup --quiet 2>&1 || true
epo learn >/dev/null 2>&1 || true
epo sync >/dev/null 2>&1 || true

# Inject nur in private Repos
if [ "$IS_PUBLIC" = "false" ]; then
    epo inject >/dev/null 2>&1 || true
    epo inject --global >/dev/null 2>&1 || true
fi

# Export data (lokale Datei, kein Leak-Risiko)
epo export >/dev/null 2>&1 || true

# Memory-Backup + Auto-Commit nur in private Repos
if [ "$IS_PUBLIC" = "false" ]; then
    PROJECT_PATH=$(echo "$PROJECT_ROOT" | sed 's|/|-|g' | sed 's|^-||')
    MEMORY_DIR="$HOME/.claude/projects/-${PROJECT_PATH}/memory"
    BACKUP_DIR="$PROJECT_ROOT/.epo/memory-backup"

    if [ -d "$MEMORY_DIR" ]; then
        mkdir -p "$BACKUP_DIR" 2>/dev/null || true
        if ! diff -rq "$MEMORY_DIR" "$BACKUP_DIR" >/dev/null 2>&1; then
            cp "$MEMORY_DIR"/*.md "$BACKUP_DIR/" 2>/dev/null || true
        fi
    fi

    if [ -d .epo ]; then
        git add .epo/ 2>/dev/null || true
        git add CLAUDE.md 2>/dev/null || true
        if ! git diff --cached --quiet 2>/dev/null; then
            git commit -m "EPO: Daten-Snapshot (automatisch)" --no-verify >/dev/null 2>&1 || true
            git push >/dev/null 2>&1 || true
        fi
    fi
fi
