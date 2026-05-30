"""EPO Exceptions -- Framework-unabhaengige Business-Exceptions."""


class EPOError(Exception):
    """Base exception for all EPO errors."""


class ConventionNotFoundError(EPOError):
    """Raised when a convention does not exist or belongs to another user."""

    def __init__(self, convention_id: int):
        self.convention_id = convention_id
        super().__init__(f"Convention {convention_id} nicht gefunden")


class GenomeNotFoundError(EPOError):
    """Raised when a template genome does not exist for the given source type."""

    def __init__(self, source_type: str):
        self.source_type = source_type
        super().__init__(f"Template-Genom fuer '{source_type}' nicht gefunden")
