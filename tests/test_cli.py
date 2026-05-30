"""Tests for EPO CLI components."""

from pathlib import Path

from sqlalchemy import select

from epo.db import get_session, init_db
from epo.models import Convention
from epo.edit_distance import calculate_edit_score
from epo.claude_md import inject_into_claude_md, remove_from_claude_md, read_conventions_from_claude_md, EPO_START_MARKER, EPO_END_MARKER
from epo.cli import LocalStore, MAX_ACTIVE_CONVENTIONS


class TestClaudeMdInjection:
    def test_inject_into_empty_file(self, tmp_path):
        inject_into_claude_md(["Regel 1", "Regel 2"], tmp_path)
        content = (tmp_path / "CLAUDE.md").read_text()
        assert EPO_START_MARKER in content
        assert EPO_END_MARKER in content
        assert "- Regel 1" in content
        assert "- Regel 2" in content

    def test_inject_into_existing_file(self, tmp_path):
        (tmp_path / "CLAUDE.md").write_text("# Mein Projekt\n\nBestehender Inhalt.\n")
        inject_into_claude_md(["Neue Regel"], tmp_path)
        content = (tmp_path / "CLAUDE.md").read_text()
        assert "Bestehender Inhalt." in content
        assert "- Neue Regel" in content

    def test_update_existing_epo_block(self, tmp_path):
        initial = f"# Projekt\n\n{EPO_START_MARKER}\nAlter Inhalt\n{EPO_END_MARKER}\n\nNach EPO."
        (tmp_path / "CLAUDE.md").write_text(initial)
        inject_into_claude_md(["Aktualisierte Regel"], tmp_path)
        content = (tmp_path / "CLAUDE.md").read_text()
        assert "Alter Inhalt" not in content
        assert "- Aktualisierte Regel" in content
        assert "Nach EPO." in content

    def test_no_change_returns_false(self, tmp_path):
        inject_into_claude_md(["Regel 1"], tmp_path)
        result = inject_into_claude_md(["Regel 1"], tmp_path)
        assert result is False

    def test_empty_conventions(self, tmp_path):
        inject_into_claude_md([], tmp_path)
        content = (tmp_path / "CLAUDE.md").read_text()
        assert "Noch keine Regeln gelernt" in content

    def test_remove_epo_block(self, tmp_path):
        (tmp_path / "CLAUDE.md").write_text(
            f"# Projekt\n\n{EPO_START_MARKER}\nInhalt\n{EPO_END_MARKER}\n"
        )
        result = remove_from_claude_md(tmp_path)
        assert result is True
        content = (tmp_path / "CLAUDE.md").read_text()
        assert EPO_START_MARKER not in content

    def test_remove_nonexistent_returns_false(self, tmp_path):
        (tmp_path / "CLAUDE.md").write_text("# Kein EPO Block\n")
        assert remove_from_claude_md(tmp_path) is False

    def test_read_conventions_roundtrip(self, tmp_path):
        rules_in = ["Regel eins", "Regel zwei", "Regel drei"]
        inject_into_claude_md(rules_in, tmp_path)
        rules_out = read_conventions_from_claude_md(tmp_path)
        assert rules_out == rules_in

    def test_read_conventions_empty(self, tmp_path):
        assert read_conventions_from_claude_md(tmp_path) == []

    def test_read_conventions_no_epo_block(self, tmp_path):
        (tmp_path / "CLAUDE.md").write_text("# Kein EPO Block\n")
        assert read_conventions_from_claude_md(tmp_path) == []

    def test_with_genome_template(self, tmp_path):
        inject_into_claude_md(
            ["Regel 1"],
            tmp_path,
            genome_template="Strukturvorlage:\n1. Kontext [95%]",
        )
        content = (tmp_path / "CLAUDE.md").read_text()
        assert "Strukturvorlage" in content
        assert "Kontext" in content


class TestLocalStore:
    def test_score_to_rating(self):
        assert LocalStore._score_to_rating(0.0) == 5  # no edits = perfect
        assert LocalStore._score_to_rating(0.5) == 3  # half edited = middle
        assert LocalStore._score_to_rating(1.0) == 1  # full rewrite = worst

    def test_score_to_rating_clamped(self):
        assert LocalStore._score_to_rating(-0.5) == 5
        assert LocalStore._score_to_rating(1.5) == 1

    def test_add_convention(self, tmp_path):
        db_path = tmp_path / "test.db"
        store = LocalStore(db_path)
        result = store.add_convention(name="Test", rule="Tu X", category="code", source_type="project:test")
        assert result is not None
        assert result.name == "Test"
        assert result.rule == "Tu X"
        store.close()

    def test_add_duplicate_returns_none(self, tmp_path):
        db_path = tmp_path / "test.db"
        store = LocalStore(db_path)
        store.add_convention(name="Test", rule="Tu X", source_type="project:test")
        result = store.add_convention(name="Test", rule="Tu X", source_type="project:test")
        assert result is None
        store.close()

    def test_add_similar_returns_none(self, tmp_path):
        db_path = tmp_path / "test.db"
        store = LocalStore(db_path)
        store.add_convention(name="Regel A", rule="Schreibe immer Type-Hints in Python Code", source_type="project:test")
        result = store.add_convention(name="Regel B", rule="Schreibe immer Type-Hints in Python-Code", source_type="project:test")
        assert result is None  # Too similar
        store.close()

    def test_max_conventions_enforced(self, tmp_path):
        db_path = tmp_path / "test.db"
        store = LocalStore(db_path)
        for i in range(MAX_ACTIVE_CONVENTIONS):
            store.add_convention(
                name=f"Regel {i}",
                rule=f"Ganz spezifische Regel Nummer {i} die einzigartig ist",
                score=1.0,
                source_type="project:test",
            )
        result = store.add_convention(
            name="Wichtige Regel",
            rule="Diese Regel ist extrem wichtig und voellig anders",
            score=5.0,
            source_type="project:test",
        )
        assert result is not None
        active = store.get_conventions("test")
        assert len(active) <= MAX_ACTIVE_CONVENTIONS
        store.close()

    def test_max_conventions_weak_rejected(self, tmp_path):
        db_path = tmp_path / "test.db"
        store = LocalStore(db_path)
        rules = [
            "Immer Type-Hints in Python verwenden fuer bessere Lesbarkeit",
            "Keine print-Statements in Produktion, stattdessen strukturiertes logging nutzen",
            "Tests gehoeren in eigene Dateien, nicht ans Ende des Moduls",
            "Docstrings fuer alle oeffentlichen Funktionen mit Parameterbeschreibung",
            "Error-Handling mit spezifischen Exception-Klassen statt generischem except",
            "Maximal 80 Zeichen pro Zeile einhalten fuer Diff-Lesbarkeit",
            "Imports alphabetisch sortieren und nach stdlib/third-party/local gruppieren",
            "Konstanten in UPPER_SNAKE_CASE benennen und am Modulanfang definieren",
            "Keine globalen Variablen verwenden, stattdessen Dependency Injection",
            "SQL-Queries immer parametrisiert ausfuehren gegen Injection",
            "Docker-Images mit Multi-Stage-Builds klein halten unter 200MB",
            "REST-APIs immer versioniert unter /api/v1/ deployen",
            "Git-Commits atomar halten mit aussagekraeftiger Commit-Message",
            "Datenbank-Migrationen immer reversibel gestalten mit Down-Migration",
            "CI-Pipeline muss in unter 5 Minuten durchlaufen fuer schnelles Feedback",
            "Secrets niemals in Code oder Konfiguration hartcodieren",
            "Logging immer mit strukturierten JSON-Feldern statt Freitext",
            "Feature-Flags fuer alle neuen Features verwenden vor GA-Release",
            "API-Responses immer mit Pagination versehen ab 50 Eintraegen",
            "Monitoring-Alerts muessen Runbook-Links enthalten fuer schnelle Triage",
            "Code-Reviews brauchen mindestens einen Approval vor dem Merge",
            "Backups taeglich automatisiert testen durch Restore-Probelauf",
            "Load-Tests vor jedem Major-Release mit realistischen Traffic-Mustern",
            "Deprecation-Warnings zwei Minor-Versionen vor dem Breaking-Change",
            "Rate-Limiting auf allen oeffentlichen API-Endpoints konfigurieren",
            "Health-Check-Endpoints muessen Downstream-Dependencies pruefen",
            "Terraform-State immer remote in S3 mit Locking speichern",
            "Container muessen als non-root User laufen in Produktion",
            "GraphQL-Queries immer mit Depth-Limiting gegen DoS absichern",
            "WebSocket-Verbindungen brauchen Heartbeat alle 30 Sekunden",
        ]
        for i in range(MAX_ACTIVE_CONVENTIONS):
            store.add_convention(
                name=f"Regel {i}",
                rule=rules[i],
                score=5.0,
                source_type="project:test",
            )
        active = store.get_conventions("test")
        assert len(active) == MAX_ACTIVE_CONVENTIONS
        result = store.add_convention(
            name="Schwache Regel",
            rule="Kommentare auf Deutsch schreiben",
            score=0.1,
            source_type="project:test",
        )
        assert result is None
        store.close()

    def test_feedback_convention_higher_score(self, tmp_path):
        db_path = tmp_path / "test.db"
        store = LocalStore(db_path)
        store.add_convention(name="Auto", rule="Automatisch gelernt", score=1.0, source_type="project:test")
        store.add_convention(name="Feedback", rule="User-Feedback Regel", score=2.0, source_type="project:test")
        conventions = store.get_conventions("test")
        assert conventions[0].name == "Feedback"
        store.close()

    def test_prune_stale(self, tmp_path):
        db_path = tmp_path / "test.db"
        store = LocalStore(db_path)
        store.add_convention(name="Alt", rule="Alte Regel")
        # Manually set updated_at to 60 days ago
        conv = store.session.execute(select(Convention).where(Convention.name == "Alt")).scalar_one()
        from datetime import datetime, timezone, timedelta
        conv.updated_at = datetime.now(timezone.utc) - timedelta(days=60)
        store.session.commit()
        pruned = store.prune_stale(max_age_days=30)
        assert pruned == 1
        # Convention should be inactive now
        store.session.refresh(conv)
        assert conv.active is False
        store.close()


class TestSqliteDb:
    def test_init_creates_tables(self, tmp_path):
        db_path = tmp_path / "test.db"
        engine = init_db(db_path)
        assert db_path.exists()

    def test_session_works(self, tmp_path):
        db_path = tmp_path / "test.db"
        session = get_session(db_path)
        result = session.execute(select(Convention)).all()
        assert result == []
        session.close()
