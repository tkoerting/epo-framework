# EPO – Evolutionary Prompt Optimization

## What is EPO?
Standalone Python package for closed-loop prompt optimization. Learns from user edits and feedback, improves LLM outputs over time. No fine-tuning, just prompt evolution.

## Structure
```
epo/
  __init__.py       # Public API + Exports
  models.py         # SQLAlchemy Models (OutputFeedback, Convention, TemplateGenome, GenomeSection)
  service.py        # Feedback/Convention CRUD + Prompt Injection + Seeds
  genome.py         # Template Genome (Welford's Running Average, Pruning)
  schemas.py        # Pydantic Schemas (SourceType Enum, typed responses)
  router.py         # FastAPI Router (create_router DI pattern)
  edit_distance.py  # Edit Score + Section Survival + Section Edit Distances
  metrics.py        # Paper Metrics (Convergence, Effectiveness)
  exceptions.py     # Framework-agnostic business exceptions
  cli.py            # CLI for Claude Code (analyze, learn, feedback, inject, etc.)
  db.py             # SQLite session setup for local CLI usage
  git_tracker.py    # Git analysis (detect Claude commits, per-file edit scores)
  claude_md.py      # CLAUDE.md injection with markers (idempotent)
scripts/
  epo-session-end.sh  # SessionEnd hook (analyze + learn + inject + export)
```

## CLI
```bash
epo setup       # Set up + self-test
epo analyze     # Analyze git history (Claude commits vs. user edits)
epo learn       # Extract conventions from collected data
epo feedback    # Add a rule directly
epo inject      # Write rules into CLAUDE.md
epo export      # Backup all data as JSON
epo import      # Import data
epo doctor      # Diagnose installation
```

## Convention Scopes
- `global` – Style rules that apply everywhere
- `personal` – Business rules, only in your own repos (not in team/org repos)
- `project:X` – Only in project X

## Team Repo Detection
Team repos are configured via the `EPO_TEAM_ORGS` environment variable:
```bash
export EPO_TEAM_ORGS="my-company,other-org"
```

## Docs
- `docs/whitepaper-evolutionary-prompt-optimization.md` – Academic paper
