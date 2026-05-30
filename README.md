# EPO – Evolutionary Prompt Optimization

A closed-loop system that makes LLM outputs better over time – without fine-tuning.

EPO measures how much you change AI-generated code and text, extracts rules from your corrections, and injects them into future prompts. The result: outputs that converge toward what you actually want.

## How it works

1. **Edit-Distance Tracking** – Measures how much you change LLM outputs (per file, per commit)
2. **Convention Extraction** – Turns recurring corrections into rules ("use real Umlaute", "no Base64 logos")
3. **Prompt Injection** – Injects learned rules into `CLAUDE.md` so the LLM remembers across sessions
4. **Convergence** – Edit scores drop over time as the system learns your preferences

No fine-tuning. No model access needed. Works with any LLM via prompt-level optimization.

## Results

Tested across 30 projects with 5,000+ datapoints over 8 weeks:

- Edit scores dropped from 3.8% to 0.0% (weekly average)
- 96% of outputs accepted unchanged
- 45 learned conventions active

See the [whitepaper](docs/whitepaper-evolutionary-prompt-optimization.md) for methodology and evaluation.

## Installation

```bash
pip install -e .
epo setup
```

`epo setup` installs a `SessionEnd` hook into Claude Code that automatically captures edit data after every session.

## CLI Usage

```bash
epo analyze     # Analyze git history (Claude commits vs. user edits)
epo learn       # Extract conventions from collected data
epo feedback "Use real Umlaute, not ae/oe/ue"  # Add a rule directly
epo inject      # Write learned rules into CLAUDE.md
epo status      # Show current EPO state
epo doctor      # Diagnose installation
epo export      # Backup all data as JSON
```

## Convention Scopes

EPO distinguishes three scopes to prevent data leakage:

| Scope | Stored as | Injected into |
|---|---|---|
| `global` | `source_type = "global"` | All repos |
| `personal` | `source_type = "personal"` | Only your own repos (not team/org repos) |
| `project:X` | `source_type = "project:X"` | Only project X |

Team repos (e.g. GitHub org repos) never receive `personal` conventions. Public repos receive no injection at all.

Configure team orgs via environment variable:

```bash
export EPO_TEAM_ORGS="my-company,other-org"
```

## FastAPI Integration

EPO can also run as a middleware in any FastAPI application:

```python
from epo.router import create_router
from epo.service import get_conventions_for_prompt, format_conventions_for_prompt

epo_router = create_router(get_db=get_db, get_user=get_current_user)
app.include_router(epo_router)

# Before LLM call: inject learned conventions
conventions = await get_conventions_for_prompt(db, user_id)
system_prompt += format_conventions_for_prompt(conventions)
```

## Related Work

EPO was developed independently and in parallel with [CIPHER](https://arxiv.org/abs/2404.15269) (Microsoft Research + Cornell, NeurIPS 2024), which uses a similar core mechanism (learning from user edits via edit distance, without fine-tuning). Key differences: EPO uses a scored multi-rule convention database with scope-aware injection, a template genome for structural optimization, and a convergence indicator – CIPHER derives a single natural-language preference description.

## License

AGPL-3.0-only. See [LICENSE](LICENSE).

Copyright (c) 2026 Thomas Körting.
