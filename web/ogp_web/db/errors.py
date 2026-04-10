from __future__ import annotations


class DatabaseError(Exception):
    """Base class for database-layer errors."""


class DatabaseUnavailableError(DatabaseError):
    """Raised when a database connection cannot be established."""


class IntegrityConflictError(DatabaseError):
    """Raised when a write violates a database integrity constraint."""


class DatabaseSchemaError(DatabaseError):
    """Raised when the database schema is missing or incompatible."""


class UnsupportedDatabaseBackendError(DatabaseError):
    """Raised when an unknown database backend is configured."""
