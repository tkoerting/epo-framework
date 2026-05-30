# EPO – Evolutionary Prompt Optimization

## Was ist EPO?
Standalone Python-Package für Closed-Loop Prompt-Optimierung. Lernt aus User-Edits und Feedback, verbessert LLM-Outputs über Zeit. Kein Fine-Tuning, nur Prompt-Evolution.

## Struktur
```
epo/
  __init__.py       # Public API + Exports
  models.py         # SQLAlchemy Models (OutputFeedback, Convention, TemplateGenome, GenomeSection)
  service.py        # Feedback/Convention CRUD + Prompt-Injection + Seeds
  genome.py         # Template-Genom (Welford's Running Average, Pruning)
  schemas.py        # Pydantic Schemas (SourceType Enum, typisierte Responses)
  router.py         # FastAPI Router (create_router DI-Pattern)
  edit_distance.py  # Edit-Score + Section-Survival + Section-Edit-Distances
  metrics.py        # Paper-Metriken (Convergence, Effectiveness)
  exceptions.py     # Framework-unabhängige Business-Exceptions
  cli.py            # CLI für Claude Code (analyze, learn, feedback, inject, etc.)
  db.py             # SQLite Session-Setup für lokalen CLI-Betrieb
  git_tracker.py    # Git-Analyse (Claude-Commits erkennen, Edit-Scores pro Datei)
  claude_md.py      # CLAUDE.md Injection mit Markern (idempotent)
scripts/
  epo-session-end.sh  # SessionEnd Hook (analyze + learn + inject + export)
```

## CLI
```bash
epo setup       # Einrichten + Selbsttest
epo analyze     # Git-History analysieren (Claude-Commits vs. User-Edits)
epo learn       # Conventions aus Daten extrahieren
epo feedback    # Regel direkt eingeben
epo inject      # Regeln in CLAUDE.md schreiben
epo export      # Alle Daten als JSON sichern
epo import      # Daten importieren
epo doctor      # Installation diagnostizieren
```

## Convention Scopes
- `global` – Stilregeln, die überall gelten
- `personal` – Geschäftliche Regeln, nur in eigenen Repos (nicht in Team/Org-Repos)
- `project:X` – Nur in Projekt X

## Team-Repo-Erkennung
Team-Repos werden über die Umgebungsvariable `EPO_TEAM_ORGS` konfiguriert:
```bash
export EPO_TEAM_ORGS="my-company,other-org"
```

## Docs
- `docs/whitepaper-evolutionary-prompt-optimization.md` – Akademisches Paper
