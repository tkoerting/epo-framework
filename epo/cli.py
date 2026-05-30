"""
EPO CLI -- Local prompt optimization for Claude Code.

Usage:
    epo analyze     Analyze git history for Claude edits
    epo learn       Extract conventions from collected data
    epo feedback    Add a convention from user feedback
    epo inject      Write learned rules to CLAUDE.md
    epo sync        Import conventions from Claude Code memory files
    epo import      Import conventions from CLAUDE.md (new machine bootstrap)
    epo status      Show current EPO state for this project
    epo prune       Remove stale or low-value conventions
"""

import argparse
import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

from sqlalchemy import select, func

from epo import __version__
from epo.db import get_session, DEFAULT_DB_PATH
from epo.models import EPOBase, OutputFeedback, Convention
from epo.edit_distance import calculate_edit_score
from epo.git_tracker import (
    get_project_root,
    find_claude_commits,
    find_next_commit,
    analyze_session,
    analyze_latest_sessions,
    SessionAnalysis,
)
from epo.claude_md import inject_into_claude_md, read_conventions_from_claude_md

# Hard limit: max active conventions per project to prevent drift
MAX_ACTIVE_CONVENTIONS = 30

# Conventions older than this without positive effect get deactivated
STALE_DAYS = 30


# =============================================================================
# Storage -- thin sync wrappers around SQLite
# =============================================================================


class LocalStore:
    """Sync SQLite storage for CLI usage."""

    def __init__(self, db_path: Path | None = None):
        self.session = get_session(db_path)

    def close(self):
        self.session.close()

    def store_analysis(self, project: str, analysis: SessionAnalysis):
        """Store file-level edit scores as OutputFeedback records."""
        for edit in analysis.file_edits:
            existing = self.session.execute(
                select(OutputFeedback).where(
                    OutputFeedback.user_id == 0,  # CLI mode: single user
                    OutputFeedback.source_type == "claude_code",
                    OutputFeedback.source_id == f"{project}:{analysis.claude_commit}:{edit.file_path}",
                )
            ).scalar_one_or_none()

            if existing:
                existing.rating = self._score_to_rating(edit.edit_score)
                existing.comment = f"edit_score={edit.edit_score}"
            else:
                feedback = OutputFeedback(
                    user_id=0,
                    source_type="claude_code",
                    source_id=f"{project}:{analysis.claude_commit}:{edit.file_path}",
                    rating=self._score_to_rating(edit.edit_score),
                    comment=f"edit_score={edit.edit_score}",
                )
                self.session.add(feedback)

        self.session.commit()

    def is_commit_tracked(self, project: str, commit_hash: str) -> bool:
        """Check if a commit has already been analyzed."""
        short_hash = commit_hash[:8]
        result = self.session.execute(
            select(OutputFeedback).where(
                OutputFeedback.source_type == "claude_code",
                OutputFeedback.source_id.like(f"{project}:{short_hash}:%"),
            ).limit(1)
        ).scalar_one_or_none()
        return result is not None

    def get_all_edit_scores(self, project: str) -> list[float]:
        """Get all edit scores for a project."""
        result = self.session.execute(
            select(OutputFeedback.comment).where(
                OutputFeedback.source_type == "claude_code",
                OutputFeedback.source_id.like(f"{project}:%"),
            )
        )
        scores = []
        for (comment,) in result.all():
            if comment and comment.startswith("edit_score="):
                try:
                    scores.append(float(comment.split("=")[1]))
                except ValueError:
                    pass
        return scores

    def get_conventions(self, project: str, scope: str = "project") -> list[Convention]:
        """
        Get active conventions, limited to MAX_ACTIVE_CONVENTIONS.

        scope: "project"  = nur Conventions für dieses Projekt (source_type == 'project:<name>')
               "global"   = nur globale Conventions (source_type == 'global')
               "personal" = nur persönliche Conventions (source_type == 'personal')
               "all"      = alle
        """
        filters = [Convention.user_id == 0, Convention.active == True]  # noqa: E712
        if scope == "project":
            filters.append(Convention.source_type == f"project:{project}")
        elif scope == "global":
            filters.append(Convention.source_type == "global")
        elif scope == "personal":
            filters.append(Convention.source_type == "personal")

        result = self.session.execute(
            select(Convention).where(*filters)
            .order_by(Convention.score.desc()).limit(MAX_ACTIVE_CONVENTIONS)
        )
        return list(result.scalars().all())

    def get_all_conventions(self) -> list[Convention]:
        """Get all conventions including inactive."""
        result = self.session.execute(
            select(Convention).where(Convention.user_id == 0).order_by(Convention.score.desc())
        )
        return list(result.scalars().all())

    _UMLAUT_STEMS = {
        "aet": "ät", "oet": "öt", "uet": "üt",
        "aer": "är", "oer": "ör", "uer": "ür",
        "ael": "äl", "oel": "öl", "uel": "ül",
        "aen": "än", "oen": "ön", "uen": "ün",
        "aes": "äs", "oes": "ös", "ues": "üs",
        "aeg": "äg", "oeg": "ög", "ueg": "üg",
        "aef": "äf", "oef": "öf", "uef": "üf",
        "aeh": "äh", "oeh": "öh", "ueh": "üh",
        "aem": "äm", "oem": "öm", "uem": "üm",
        "aep": "äp", "oep": "öp", "uep": "üp",
        "aeb": "äb", "oeb": "öb", "ueb": "üb",
        "aec": "äc", "oec": "öc", "uec": "üc",
        "aed": "äd", "oed": "öd", "ued": "üd",
    }
    _UMLAUT_SAFE = {"true", "blue", "due", "queue", "cue", "issue", "value",
                    "rescue", "argue", "venue", "tissue", "pursue", "continue",
                    "evaluate", "league", "vague", "technique", "unique", "critique",
                    "colleague", "catalogue", "opaque", "clue", "glue", "rue",
                    "hue", "sue", "ague", "ensue", "residue", "statue", "virtue",
                    "revenue", "avenue", "revue", "subdue", "imbue", "accrue",
                    "construe", "misconstrue", "overdue", "undue", "fondue"}

    @classmethod
    def _fix_umlauts(cls, text: str) -> str:
        """Replace German ASCII-Umlaut patterns with correct Umlaute."""
        import re
        words = re.split(r'(\W+)', text)
        result = []
        for word in words:
            if word.lower() in cls._UMLAUT_SAFE:
                result.append(word)
                continue
            for wrong, right in cls._UMLAUT_STEMS.items():
                word = word.replace(wrong, right)
                word = word.replace(wrong.capitalize(), right.capitalize())
            result.append(word)
        return "".join(result)

    def add_convention(
        self,
        name: str,
        rule: str,
        category: str = "code",
        source_type: str | None = None,
        score: float = 1.0,
    ) -> Convention | None:
        """
        Add a convention. Returns None if a duplicate exists.
        Enforces MAX_ACTIVE_CONVENTIONS by deactivating the weakest.
        """
        name = self._fix_umlauts(name)
        rule = self._fix_umlauts(rule)

        # Check for duplicates (similar rule text)
        existing = self.session.execute(
            select(Convention).where(
                Convention.user_id == 0,
                Convention.name == name,
            )
        ).scalar_one_or_none()

        if existing:
            if existing.active:
                return None  # Already exists and active
            # Reactivate with updated rule
            existing.active = True
            existing.rule = rule
            existing.score = score
            self.session.commit()
            self.session.refresh(existing)
            return existing

        # Default empty/None source_type to "global"
        if not source_type:
            source_type = "global"

        # Determine project for scope-aware checks
        if source_type.startswith("project:"):
            scope_project = source_type.split(":", 1)[1]
            scope = "project"
        elif source_type == "global":
            scope_project = ""
            scope = "global"
        else:
            scope_project = ""
            scope = "all"

        # Check similarity against existing rules in same scope
        all_active = self.get_conventions(scope_project, scope=scope)
        for conv in all_active:
            similarity = 1.0 - calculate_edit_score(conv.rule, rule)
            if similarity > 0.8:
                return None  # Too similar to existing

        # Enforce limit: deactivate weakest if at capacity
        if len(all_active) >= MAX_ACTIVE_CONVENTIONS:
            weakest = all_active[-1]  # Lowest score (sorted desc)
            if score > weakest.score:
                weakest.active = False
                self.session.flush()
            else:
                return None  # New convention is weaker than all existing

        convention = Convention(
            user_id=0,
            name=name,
            rule=rule,
            category=category,
            source_type=source_type,
            score=score,
        )
        self.session.add(convention)
        self.session.commit()
        self.session.refresh(convention)
        return convention

    def export_all(self, project: str) -> dict:
        """Export all data as a JSON-serializable dict."""
        # Feedback / edit scores
        feedbacks = self.session.execute(
            select(OutputFeedback).where(
                OutputFeedback.source_type == "claude_code",
                OutputFeedback.source_id.like(f"{project}:%"),
            ).order_by(OutputFeedback.created_at)
        ).scalars().all()

        feedback_data = []
        for fb in feedbacks:
            feedback_data.append({
                "source_id": fb.source_id,
                "rating": fb.rating,
                "comment": fb.comment,
                "created_at": fb.created_at.isoformat() if fb.created_at else None,
            })

        # Conventions
        conventions = self.get_all_conventions()
        convention_data = []
        for c in conventions:
            convention_data.append({
                "name": c.name,
                "rule": c.rule,
                "category": c.category,
                "source_type": c.source_type,
                "score": c.score,
                "active": c.active,
                "created_at": c.created_at.isoformat() if c.created_at else None,
                "updated_at": c.updated_at.isoformat() if c.updated_at else None,
            })

        return {
            "epo_version": __version__,
            "project": project,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "feedbacks": feedback_data,
            "conventions": convention_data,
        }

    def import_data(self, data: dict) -> dict:
        """Import data from an export dict. Returns counts."""
        imported_feedbacks = 0
        imported_conventions = 0

        for fb in data.get("feedbacks", []):
            existing = self.session.execute(
                select(OutputFeedback).where(
                    OutputFeedback.user_id == 0,
                    OutputFeedback.source_type == "claude_code",
                    OutputFeedback.source_id == fb["source_id"],
                )
            ).scalar_one_or_none()
            if not existing:
                self.session.add(OutputFeedback(
                    user_id=0,
                    source_type="claude_code",
                    source_id=fb["source_id"],
                    rating=fb["rating"],
                    comment=fb.get("comment"),
                ))
                imported_feedbacks += 1

        for c in data.get("conventions", []):
            existing = self.session.execute(
                select(Convention).where(
                    Convention.user_id == 0,
                    Convention.name == c["name"],
                )
            ).scalar_one_or_none()
            if not existing:
                self.session.add(Convention(
                    user_id=0,
                    name=c["name"],
                    rule=c["rule"],
                    category=c.get("category", "imported"),
                    source_type=c.get("source_type"),
                    score=c.get("score", 1.0),
                    active=c.get("active", True),
                ))
                imported_conventions += 1

        self.session.commit()
        return {"feedbacks": imported_feedbacks, "conventions": imported_conventions}

    def prune_stale(self, max_age_days: int = STALE_DAYS) -> int:
        """Deactivate conventions that haven't been updated in max_age_days."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
        result = self.session.execute(
            select(Convention).where(
                Convention.user_id == 0,
                Convention.active == True,  # noqa: E712
                Convention.updated_at < cutoff,
            )
        )
        count = 0
        for conv in result.scalars().all():
            conv.active = False
            count += 1
        if count:
            self.session.commit()
        return count

    def get_stats(self, project: str) -> dict:
        """Get summary stats."""
        scores = self.get_all_edit_scores(project)
        conventions = self.get_conventions(project)
        all_conventions = self.get_all_conventions()
        inactive = [c for c in all_conventions if not c.active]
        return {
            "total_edits": len(scores),
            "avg_edit_score": round(sum(scores) / len(scores), 3) if scores else None,
            "conventions_active": len(conventions),
            "conventions_inactive": len(inactive),
            "conventions_limit": MAX_ACTIVE_CONVENTIONS,
        }

    @staticmethod
    def _score_to_rating(edit_score: float) -> int:
        """Convert edit score (0-1, lower=better) to rating (1-5, higher=better)."""
        return max(1, min(5, round(5 - edit_score * 4)))


# =============================================================================
# CLI Commands
# =============================================================================


def cmd_analyze(args):
    """Analyze git history for Claude Code edits."""
    try:
        project_root = get_project_root()
    except RuntimeError:
        print("Fehler: Kein Git-Repository gefunden.")
        return 1

    project_name = project_root.name

    if args.commit:
        commits_to_analyze = [{"hash": args.commit, "message": "", "date": ""}]
    else:
        limit = 200 if args.catchup else args.limit
        commits_to_analyze = find_claude_commits(limit=limit)

    if not commits_to_analyze:
        if not args.quiet:
            print("Keine Claude-Commits gefunden (suche nach 'Co-Authored-By: Claude').")
        return 0

    store = LocalStore()

    # Filter: bereits erfasste Commits überspringen
    if not args.commit:
        untracked = []
        for commit in commits_to_analyze:
            if not store.is_commit_tracked(project_name, commit["hash"]):
                untracked.append(commit)
        skipped = len(commits_to_analyze) - len(untracked)
        commits_to_analyze = untracked

    if not commits_to_analyze:
        if not args.quiet:
            print(f"EPO: {project_name} – alle {skipped} Commits bereits erfasst.")
        store.close()
        return 0

    if not args.quiet:
        info = f" ({skipped} bereits erfasst)" if not args.commit and skipped > 0 else ""
        print(f"EPO: Analysiere {project_name} – {len(commits_to_analyze)} neue Commits{info}")

    total_files = 0

    for commit in commits_to_analyze:
        try:
            # Vergleiche gegen den nächsten Commit (nicht HEAD),
            # um nur direkte User-Edits zu messen statt spätere Weiterentwicklung
            next_ref = find_next_commit(commit["hash"]) or "HEAD"
            analysis = analyze_session(commit["hash"], compare_to=next_ref)
        except RuntimeError as e:
            if not args.quiet:
                print(f"  Ueberspringe {commit['hash'][:8]}: {e}")
            continue

        store.store_analysis(project_name, analysis)
        total_files += len(analysis.file_edits)

        if not args.quiet:
            # Print summary
            print(f"  {analysis.claude_commit} | {analysis.claude_message[:60]}")
            print(f"    Dateien: {len(analysis.file_edits)} | "
                  f"Unveraendert: {analysis.files_unchanged} | "
                  f"Editiert: {analysis.files_modified} | "
                  f"Avg Edit-Score: {analysis.avg_edit_score}")

            # Show top edits
            top_edits = sorted(analysis.file_edits, key=lambda e: e.edit_score, reverse=True)[:3]
            for edit in top_edits:
                if edit.edit_score > 0:
                    bar = "+" * int(edit.edit_score * 20)
                    print(f"    {edit.edit_score:.2f} [{bar:20s}] {edit.file_path}")
            print()

    store.close()
    if not args.quiet:
        print(f"Gespeichert: {total_files} Datei-Edits in {DEFAULT_DB_PATH}")
    return 0


def cmd_learn(args):
    """Extract conventions from collected edit data."""
    try:
        project_root = get_project_root()
    except RuntimeError:
        print("Fehler: Kein Git-Repository gefunden.")
        return 1

    project_name = project_root.name
    store = LocalStore()
    scores = store.get_all_edit_scores(project_name)

    if len(scores) < 3:
        print(f"Zu wenig Daten ({len(scores)} Edits). Mindestens 3 benoetigt.")
        print("Tipp: Fuehre `epo analyze` nach einigen Claude Code Sessions aus.")
        store.close()
        return 0

    print(f"EPO: Lerne aus {len(scores)} Edits...\n")

    avg_score = sum(scores) / len(scores)
    high_edit_files = [s for s in scores if s > 0.5]
    low_edit_files = [s for s in scores if s < 0.1]

    print(f"  Durchschnittlicher Edit-Score: {avg_score:.3f}")
    print(f"  Stark editiert (>50%): {len(high_edit_files)} Dateien")
    print(f"  Kaum editiert (<10%): {len(low_edit_files)} Dateien")
    print()

    new_conventions = 0
    project_source = f"project:{project_name}"

    if avg_score > 0.4:
        result = store.add_convention(
            name="Kuerzere Outputs",
            rule=f"Outputs werden durchschnittlich um {avg_score:.0%} editiert. Kuerzer und praeziser schreiben.",
            category="content",
            source_type=project_source,
        )
        if result:
            print(f"  + Convention: '{result.name}'")
            new_conventions += 1

    if len(high_edit_files) > len(scores) * 0.5:
        result = store.add_convention(
            name="Mehr Kontext beachten",
            rule="Mehr als die Haelfte der Outputs wird stark editiert. Bestehenden Code gruendlicher lesen bevor Aenderungen vorgeschlagen werden.",
            category="code",
            source_type=project_source,
        )
        if result:
            print(f"  + Convention: '{result.name}'")
            new_conventions += 1

    if len(low_edit_files) > len(scores) * 0.7 and len(scores) >= 5:
        result = store.add_convention(
            name="Gute Qualitaet",
            rule="Outputs werden selten editiert. Aktuellen Stil und Detailgrad beibehalten.",
            category="general",
            source_type=project_source,
        )
        if result:
            print(f"  + Convention: '{result.name}'")
            new_conventions += 1

    if new_conventions == 0:
        print("  Keine neuen Conventions erkannt (evtl. bereits vorhanden).")

    store.close()
    print(f"\n{new_conventions} neue Convention(s) gelernt.")
    if new_conventions > 0:
        print("Tipp: `epo inject` schreibt die Regeln in CLAUDE.md")
    return 0


def cmd_feedback(args):
    """Add a convention from direct user feedback."""
    store = LocalStore()

    rule = args.rule
    name = args.name or rule[:50]
    category = args.category or "feedback"
    is_global = args.global_flag

    # Projektnamen ermitteln für projekt-spezifische Conventions
    if is_global:
        source_type = "global"
    else:
        try:
            project_root = get_project_root()
            source_type = f"project:{project_root.name}"
        except RuntimeError:
            source_type = "project:unknown"

    result = store.add_convention(
        name=name,
        rule=rule,
        category=category,
        source_type=source_type,
        score=2.0,  # User feedback gets higher priority than auto-learned
    )

    if result:
        scope = "GLOBAL" if is_global else "Projekt"
        print(f"EPO: Convention gespeichert ({scope}).")
        print(f"  [{result.category}] {result.name}: {result.rule}")
        if is_global:
            print(f"\nTipp: `epo inject --global` schreibt die Regel in ~/.claude/CLAUDE.md")
        else:
            print(f"\nTipp: `epo inject` schreibt die Regel in CLAUDE.md")
    else:
        print("EPO: Convention existiert bereits oder ist zu ähnlich zu einer bestehenden.")

    store.close()
    return 0


def cmd_sync(args):
    """Import conventions from Claude Code memory files."""
    try:
        project_root = get_project_root()
    except RuntimeError:
        print("Fehler: Kein Git-Repository gefunden.")
        return 1

    # Find memory directory for this project
    project_path = str(project_root).replace("/", "-")
    if project_path.startswith("-"):
        project_path = project_path[1:]
    memory_dir = Path.home() / ".claude" / "projects" / f"-{project_path}" / "memory"

    if not memory_dir.exists():
        print(f"Kein Memory-Verzeichnis gefunden: {memory_dir}")
        return 0

    # Scan for feedback memory files
    feedback_files = list(memory_dir.glob("feedback_*.md"))
    if not feedback_files:
        print("Keine Feedback-Memories gefunden.")
        return 0

    print(f"EPO: Synchronisiere {len(feedback_files)} Feedback-Memory(s)...\n")

    store = LocalStore()
    imported = 0

    for file_path in feedback_files:
        content = file_path.read_text(encoding="utf-8")

        # Extract the rule from the memory content (after frontmatter)
        lines = content.split("\n")
        in_frontmatter = False
        rule_lines = []
        name = file_path.stem.replace("feedback_", "").replace("_", " ").title()

        for line in lines:
            if line.strip() == "---":
                in_frontmatter = not in_frontmatter
                continue
            if in_frontmatter:
                if line.startswith("name:"):
                    name = line.split(":", 1)[1].strip()
                continue
            # After frontmatter: collect non-empty lines as the rule
            stripped = line.strip()
            if stripped and not stripped.startswith("**Why:") and not stripped.startswith("**How to apply:"):
                rule_lines.append(stripped)

        if not rule_lines:
            continue

        rule = rule_lines[0]  # Use first substantive line as the rule
        result = store.add_convention(
            name=name,
            rule=rule,
            category="feedback",
            score=2.0,
        )

        if result:
            print(f"  + [{file_path.name}] {result.name}: {result.rule}")
            imported += 1
        else:
            print(f"  = [{file_path.name}] Bereits vorhanden oder zu aehnlich")

    store.close()
    print(f"\n{imported} Convention(s) aus Memories importiert.")
    if imported > 0:
        print("Tipp: `epo inject` schreibt die Regeln in CLAUDE.md")
    return 0


def cmd_export(args):
    """Export all EPO data as JSON for backup, sync, or paper."""
    try:
        project_root = get_project_root()
    except RuntimeError:
        print("Fehler: Kein Git-Repository gefunden.")
        return 1

    project_name = project_root.name
    store = LocalStore()
    data = store.export_all(project_name)
    store.close()

    # Determine output path
    output_path = Path(args.output) if args.output else project_root / ".epo" / "data.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    output_path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print(f"EPO: Daten exportiert nach {output_path}")
    print(f"  Feedbacks: {len(data['feedbacks'])}")
    print(f"  Conventions: {len(data['conventions'])}")
    print(f"\nDiese Datei ins Repo committen fuer Sync und Paper-Nachvollziehbarkeit.")
    return 0


def cmd_import(args):
    """Import EPO data from JSON export or CLAUDE.md."""
    try:
        project_root = get_project_root()
    except RuntimeError:
        print("Fehler: Kein Git-Repository gefunden.")
        return 1

    # Check if importing from JSON file
    data_file = Path(args.file) if args.file else project_root / ".epo" / "data.json"

    if data_file.exists():
        print(f"EPO: Importiere aus {data_file}...\n")
        data = json.loads(data_file.read_text(encoding="utf-8"))

        store = LocalStore()
        counts = store.import_data(data)
        store.close()

        print(f"  Feedbacks: {counts['feedbacks']} importiert")
        print(f"  Conventions: {counts['conventions']} importiert")
        return 0

    # Fallback: Import from CLAUDE.md
    rules = read_conventions_from_claude_md(project_root)

    if not rules:
        print(f"Weder {data_file} noch EPO-Regeln in CLAUDE.md gefunden.")
        return 0

    print(f"EPO: Importiere {len(rules)} Regel(n) aus CLAUDE.md...\n")

    store = LocalStore()
    imported = 0

    for rule in rules:
        name = rule[:50]
        result = store.add_convention(
            name=name,
            rule=rule,
            category="imported",
            score=1.5,
        )
        if result:
            print(f"  + {result.rule}")
            imported += 1
        else:
            print(f"  = Bereits vorhanden: {rule[:60]}")

    store.close()
    print(f"\n{imported} Convention(s) importiert.")
    return 0


def _is_team_repo() -> bool:
    """Check if the current repo belongs to a GitHub org (= team repo).

    Override by setting EPO_TEAM_ORGS to a comma-separated list of GitHub org names.
    Example: EPO_TEAM_ORGS=my-company,other-org
    """
    import os
    import subprocess

    team_orgs = os.environ.get("EPO_TEAM_ORGS", "")
    if not team_orgs:
        return False

    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True, cwd=Path.cwd(),
        )
        url = result.stdout.decode("utf-8", errors="replace").strip()
        for org in team_orgs.split(","):
            org = org.strip()
            if not org:
                continue
            for prefix in [f"github.com/{org}/", f"github.com:{org}/"]:
                if prefix in url:
                    return True
        return False
    except Exception:
        return False


def cmd_inject(args):
    """Write learned conventions into CLAUDE.md (project or global)."""
    is_global = args.global_flag
    store = LocalStore()

    if is_global:
        global_conventions = store.get_conventions("", scope="global")
        personal_conventions = store.get_conventions("", scope="personal")
        store.close()
        rules = [c.rule for c in global_conventions] + [c.rule for c in personal_conventions]

        global_claude_md = Path.home() / ".claude"
        modified = inject_into_claude_md(
            conventions=rules,
            project_root=global_claude_md,
        )

        if modified:
            print(f"EPO: {len(rules)} Regel(n) in ~/.claude/CLAUDE.md geschrieben "
                  f"({len(global_conventions)} global, {len(personal_conventions)} personal).")
            for rule in rules:
                print(f"  - {rule}")
        else:
            print("EPO: ~/.claude/CLAUDE.md ist bereits aktuell.")
    else:
        try:
            project_root = get_project_root()
        except RuntimeError:
            print("Fehler: Kein Git-Repository gefunden.")
            store.close()
            return 1

        project_conventions = store.get_conventions(project_root.name, scope="project")
        global_conventions = store.get_conventions("", scope="global")
        store.close()

        # Team-Repos bekommen NUR globale + projekt-spezifische Regeln
        # Persönliche Conventions (personal) werden in Team-Repos NICHT injiziert
        all_conventions = list(global_conventions)
        if not _is_team_repo():
            personal_conventions = LocalStore()
            personal = personal_conventions.get_conventions("", scope="personal")
            personal_conventions.close()
            all_conventions.extend(personal)
        all_conventions.extend(project_conventions)

        all_rules = [c.rule for c in all_conventions]

        modified = inject_into_claude_md(
            conventions=all_rules,
            project_root=project_root,
        )

        team_hint = " (Team-Repo: personal ausgeschlossen)" if _is_team_repo() else ""
        if modified:
            n = len(all_rules)
            print(f"EPO: {n} Regel(n) in {project_root / 'CLAUDE.md'} geschrieben.{team_hint}")
            if global_conventions:
                print(f"  Global ({len(global_conventions)}):")
                for c in global_conventions:
                    print(f"    - {c.rule}")
            if project_conventions:
                print(f"  Projekt ({len(project_conventions)}):")
                for c in project_conventions:
                    print(f"    - {c.rule}")
        else:
            print(f"EPO: CLAUDE.md ist bereits aktuell.{team_hint}")

    return 0


def cmd_prune(args):
    """Remove stale or low-value conventions."""
    store = LocalStore()

    pruned = store.prune_stale(max_age_days=args.days)

    if pruned:
        print(f"EPO: {pruned} Convention(s) deaktiviert (aelter als {args.days} Tage ohne Update).")
        print("Tipp: `epo inject` aktualisiert CLAUDE.md")
    else:
        print("EPO: Keine veralteten Conventions gefunden.")

    # Show current state
    all_conv = store.get_all_conventions()
    active = [c for c in all_conv if c.active]
    inactive = [c for c in all_conv if not c.active]
    print(f"\n  Aktiv: {len(active)}/{MAX_ACTIVE_CONVENTIONS} | Inaktiv: {len(inactive)}")

    store.close()
    return 0


def cmd_status(args):
    """Show current EPO state."""
    try:
        project_root = get_project_root()
    except RuntimeError:
        print("Fehler: Kein Git-Repository gefunden.")
        return 1

    project_name = project_root.name
    store = LocalStore()
    stats = store.get_stats(project_name)
    project_conventions = store.get_conventions(project_name, scope="project")
    global_conventions = store.get_conventions("", scope="global")
    store.close()

    print(f"EPO Status: {project_name}")
    print(f"  DB: {DEFAULT_DB_PATH}")
    print(f"  Erfasste Edits: {stats['total_edits']}")
    print(f"  Avg Edit-Score: {stats['avg_edit_score'] or 'n/a'}")

    if global_conventions:
        print(f"\n  Globale Regeln ({len(global_conventions)}):")
        for c in global_conventions:
            print(f"    [{c.category}] {c.name}: {c.rule}")

    if project_conventions:
        print(f"\n  Projekt-Regeln ({len(project_conventions)}):")
        for c in project_conventions:
            print(f"    [{c.category}] {c.name}: {c.rule}")

    claude_commits = find_claude_commits(limit=5)
    if claude_commits:
        print(f"\n  Letzte Claude-Commits:")
        for commit in claude_commits[:5]:
            print(f"    {commit['hash'][:8]} | {commit['date'][:10]} | {commit['message'][:60]}")

    return 0


# =============================================================================
# Setup & Doctor
# =============================================================================


HOOK_SCRIPT_NAME = "epo-session-end.sh"
HOOK_COMMAND_PREFIX = "bash "
CLAUDE_SETTINGS_PATH = Path.home() / ".claude" / "settings.json"


def _find_hook_script() -> Path | None:
    """Find the EPO session-end hook script."""
    # Check common locations
    candidates = [
        Path(__file__).parent.parent / "scripts" / HOOK_SCRIPT_NAME,  # Dev install
        Path.home() / ".local" / "share" / "epo" / HOOK_SCRIPT_NAME,
    ]
    # Also check if epo was pip-installed and find the package root
    try:
        import epo
        pkg_root = Path(epo.__file__).parent.parent
        candidates.insert(0, pkg_root / "scripts" / HOOK_SCRIPT_NAME)
    except Exception:
        pass

    for path in candidates:
        if path.exists():
            return path
    return None


def _check_hook_installed() -> tuple[bool, str]:
    """Check if the EPO hook is in Claude Code settings."""
    if not CLAUDE_SETTINGS_PATH.exists():
        return False, "~/.claude/settings.json existiert nicht"

    settings = json.loads(CLAUDE_SETTINGS_PATH.read_text(encoding="utf-8"))
    hooks = settings.get("hooks", {}).get("SessionEnd", [])

    for hook_group in hooks:
        for hook in hook_group.get("hooks", []):
            cmd = hook.get("command", "")
            if "epo" in cmd and ("analyze" in cmd or "session-end" in cmd):
                return True, cmd

    return False, "Kein EPO-Hook in SessionEnd gefunden"


def _install_hook(script_path: Path) -> bool:
    """Install the EPO hook into Claude Code settings."""
    if CLAUDE_SETTINGS_PATH.exists():
        settings = json.loads(CLAUDE_SETTINGS_PATH.read_text(encoding="utf-8"))
    else:
        CLAUDE_SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        settings = {}

    if "hooks" not in settings:
        settings["hooks"] = {}
    if "SessionEnd" not in settings["hooks"]:
        settings["hooks"]["SessionEnd"] = [{"matcher": "", "hooks": []}]

    # Find the hook group and add EPO hook
    hook_group = settings["hooks"]["SessionEnd"][0]
    if "hooks" not in hook_group:
        hook_group["hooks"] = []

    # Check if already installed
    for hook in hook_group["hooks"]:
        if "epo" in hook.get("command", ""):
            return False  # Already installed

    hook_group["hooks"].append({
        "type": "command",
        "command": f"bash {script_path}",
        "timeout": 60,
    })

    CLAUDE_SETTINGS_PATH.write_text(
        json.dumps(settings, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return True


def cmd_setup(args):
    """Full EPO setup: install hook, test everything, report."""
    print("EPO Setup\n")
    errors = []
    warnings = []

    # 1. Check Python & epo
    print("  [1/6] EPO Installation...")
    try:
        from epo import __version__
        print(f"         OK  epo v{__version__}")
    except ImportError:
        print("         FEHLER  epo nicht importierbar")
        errors.append("epo Package nicht korrekt installiert")

    # 2. Check SQLite DB
    print("  [2/6] Datenbank...")
    try:
        store = LocalStore()
        stats = store.get_stats("_test_")
        store.close()
        print(f"         OK  {DEFAULT_DB_PATH}")
    except Exception as e:
        print(f"         FEHLER  {e}")
        errors.append(f"DB-Fehler: {e}")

    # 3. Check Git
    print("  [3/6] Git...")
    try:
        project_root = get_project_root()
        print(f"         OK  Repo: {project_root.name}")
    except RuntimeError:
        print("         WARNUNG  Kein Git-Repo (EPO braucht Git fuer Analyse)")
        warnings.append("Kein Git-Repository im aktuellen Verzeichnis")

    # 4. Check hook script
    print("  [4/6] Hook-Script...")
    script_path = _find_hook_script()
    if script_path:
        print(f"         OK  {script_path}")
    else:
        print("         WARNUNG  scripts/epo-session-end.sh nicht gefunden")
        warnings.append("Hook-Script nicht gefunden -- epo wird inline im Hook laufen")

    # 5. Check/install Claude Code hook
    print("  [5/6] Claude Code Hook...")
    installed, detail = _check_hook_installed()
    if installed:
        print(f"         OK  Hook aktiv")
    else:
        print(f"         --  {detail}")
        if script_path:
            success = _install_hook(script_path)
            if success:
                print(f"         OK  Hook installiert: bash {script_path}")
            else:
                print(f"         OK  Hook war bereits installiert")
        else:
            # Fallback: inline hook without script
            if CLAUDE_SETTINGS_PATH.exists():
                settings = json.loads(CLAUDE_SETTINGS_PATH.read_text(encoding="utf-8"))
            else:
                settings = {}
            if "hooks" not in settings:
                settings["hooks"] = {}
            if "SessionEnd" not in settings["hooks"]:
                settings["hooks"]["SessionEnd"] = [{"matcher": "", "hooks": []}]
            hook_group = settings["hooks"]["SessionEnd"][0]
            if "hooks" not in hook_group:
                hook_group["hooks"] = []
            already = any("epo" in h.get("command", "") for h in hook_group["hooks"])
            if not already:
                hook_group["hooks"].append({
                    "type": "command",
                    "command": "epo analyze --limit 1 && epo learn && epo inject && epo export",
                    "timeout": 30,
                })
                CLAUDE_SETTINGS_PATH.write_text(
                    json.dumps(settings, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8",
                )
                print(f"         OK  Inline-Hook installiert")
            else:
                print(f"         OK  Hook war bereits installiert")

    # 6. Check existing data
    print("  [6/6] Bestehende Daten...")
    try:
        project_root = get_project_root()
        data_file = project_root / ".epo" / "data.json"
        if data_file.exists():
            data = json.loads(data_file.read_text(encoding="utf-8"))
            print(f"         OK  {len(data.get('feedbacks', []))} Feedbacks, "
                  f"{len(data.get('conventions', []))} Conventions in .epo/data.json")
            # Auto-import if local DB is empty
            store = LocalStore()
            local_scores = store.get_all_edit_scores(project_root.name)
            if not local_scores and data.get("feedbacks"):
                counts = store.import_data(data)
                print(f"         OK  {counts['feedbacks']} Feedbacks importiert (DB war leer)")
            store.close()
        else:
            print(f"         --  Noch keine Export-Daten vorhanden")
    except RuntimeError:
        print(f"         --  Kein Git-Repo, uebersprungen")

    # Summary
    print()
    if errors:
        print(f"  FEHLER: {len(errors)}")
        for e in errors:
            print(f"    - {e}")
        return 1
    elif warnings:
        print(f"  Setup abgeschlossen mit {len(warnings)} Warnung(en).")
        for w in warnings:
            print(f"    - {w}")
    else:
        print("  Setup abgeschlossen. Alles OK.")
        print("  EPO laeuft ab der naechsten Claude Code Session automatisch.")

    return 0


def cmd_doctor(args):
    """Diagnose EPO installation and report issues."""
    print("EPO Doctor\n")
    issues = []

    # Check epo command
    import shutil
    epo_path = shutil.which("epo")
    if epo_path:
        print(f"  epo Command:     OK  ({epo_path})")
    else:
        print(f"  epo Command:     FEHLER  Nicht im PATH")
        issues.append("epo nicht im PATH -- `pip install` wiederholen")

    # Check DB
    if DEFAULT_DB_PATH.exists():
        size_kb = DEFAULT_DB_PATH.stat().st_size / 1024
        print(f"  Datenbank:       OK  ({size_kb:.0f} KB)")
    else:
        print(f"  Datenbank:       --  Noch nicht erstellt (wird beim ersten Lauf angelegt)")

    # Check hook
    installed, detail = _check_hook_installed()
    if installed:
        print(f"  Claude Hook:     OK")
    else:
        print(f"  Claude Hook:     FEHLER  {detail}")
        issues.append("Hook nicht installiert -- `epo setup` ausfuehren")

    # Check hook script
    script = _find_hook_script()
    if script:
        import os
        executable = os.access(script, os.X_OK)
        if executable:
            print(f"  Hook-Script:     OK  ({script})")
        else:
            print(f"  Hook-Script:     WARNUNG  Nicht ausfuehrbar ({script})")
            issues.append(f"chmod +x {script}")
    else:
        print(f"  Hook-Script:     WARNUNG  Nicht gefunden (Inline-Hook wird verwendet)")

    # Check git
    try:
        root = get_project_root()
        print(f"  Git Repo:        OK  ({root.name})")
        commits = find_claude_commits(limit=1)
        if commits:
            print(f"  Claude Commits:  OK  (letzter: {commits[0]['hash'][:8]})")
        else:
            print(f"  Claude Commits:  --  Keine gefunden")
    except RuntimeError:
        print(f"  Git Repo:        --  Kein Repo im aktuellen Verzeichnis")

    # Check settings.json integrity
    if CLAUDE_SETTINGS_PATH.exists():
        try:
            json.loads(CLAUDE_SETTINGS_PATH.read_text(encoding="utf-8"))
            print(f"  settings.json:   OK")
        except json.JSONDecodeError as e:
            print(f"  settings.json:   FEHLER  Ungueltig: {e}")
            issues.append("settings.json ist kein gueltiges JSON")

    print()
    if issues:
        print(f"  {len(issues)} Problem(e) gefunden:")
        for issue in issues:
            print(f"    - {issue}")
        return 1
    else:
        print("  Keine Probleme gefunden.")
    return 0


# =============================================================================
# Main
# =============================================================================


def main():
    parser = argparse.ArgumentParser(
        prog="epo",
        description="EPO -- Evolutionary Prompt Optimization fuer Claude Code",
    )
    subparsers = parser.add_subparsers(dest="command")

    # analyze
    p_analyze = subparsers.add_parser("analyze", help="Git-History nach Claude-Edits analysieren")
    p_analyze.add_argument("--commit", "-c", help="Bestimmten Commit analysieren")
    p_analyze.add_argument("--limit", "-n", type=int, default=10, help="Max Claude-Commits (default: 10)")
    p_analyze.add_argument("--catchup", action="store_true", help="Alle noch nicht erfassten Commits nacherfassen")
    p_analyze.add_argument("--quiet", "-q", action="store_true", help="Nur Fehler ausgeben (für Hooks)")

    # learn
    p_learn = subparsers.add_parser("learn", help="Conventions aus gesammelten Daten extrahieren")

    # feedback
    p_feedback = subparsers.add_parser("feedback", help="Convention aus User-Feedback hinzufuegen")
    p_feedback.add_argument("rule", help="Die Regel als Text")
    p_feedback.add_argument("--name", help="Name der Convention (default: aus Regel abgeleitet)")
    p_feedback.add_argument("--category", help="Kategorie (default: feedback)")
    p_feedback.add_argument("--global", dest="global_flag", action="store_true", help="Globale Regel (gilt für alle Projekte)")

    # sync
    p_sync = subparsers.add_parser("sync", help="Conventions aus Claude Code Memory-Dateien importieren")

    # export
    p_export = subparsers.add_parser("export", help="Alle Daten als JSON exportieren (Backup/Paper/Sync)")
    p_export.add_argument("--output", "-o", help="Ausgabedatei (default: .epo/data.json)")

    # import
    p_import = subparsers.add_parser("import", help="Daten aus JSON-Export oder CLAUDE.md importieren")
    p_import.add_argument("--file", "-f", help="JSON-Datei (default: .epo/data.json, Fallback: CLAUDE.md)")

    # inject
    p_inject = subparsers.add_parser("inject", help="Gelernte Regeln in CLAUDE.md schreiben")
    p_inject.add_argument("--global", dest="global_flag", action="store_true", help="Globale Regeln in ~/.claude/CLAUDE.md schreiben")

    # prune
    p_prune = subparsers.add_parser("prune", help="Veraltete Conventions deaktivieren")
    p_prune.add_argument("--days", type=int, default=STALE_DAYS, help=f"Max Alter in Tagen (default: {STALE_DAYS})")

    # status
    p_status = subparsers.add_parser("status", help="Aktuellen EPO-Stand anzeigen")

    # setup
    p_setup = subparsers.add_parser("setup", help="EPO einrichten, testen und quittieren")

    # doctor
    p_doctor = subparsers.add_parser("doctor", help="EPO-Installation pruefen und Probleme diagnostizieren")

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return 0

    commands = {
        "analyze": cmd_analyze,
        "learn": cmd_learn,
        "feedback": cmd_feedback,
        "sync": cmd_sync,
        "export": cmd_export,
        "import": cmd_import,
        "inject": cmd_inject,
        "prune": cmd_prune,
        "status": cmd_status,
        "setup": cmd_setup,
        "doctor": cmd_doctor,
    }

    return commands[args.command](args)


if __name__ == "__main__":
    sys.exit(main() or 0)
