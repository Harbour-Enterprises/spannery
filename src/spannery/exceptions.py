"""
Exception classes for Spannery.
"""


class SpanneryError(Exception):
    """Base exception class for all Spannery errors."""

    pass


class ModelDefinitionError(SpanneryError):
    """
    Raised when there's an error in model definition.
    """

    pass


class ValidationError(SpanneryError):
    """
    Raised when field validation fails.
    """

    pass


class RecordNotFoundError(SpanneryError):
    """
    Raised when a record is not found in the database.
    """

    pass


class MultipleRecordsFoundError(SpanneryError):
    """
    Raised when a query returns multiple records but only one is expected.
    """

    pass


class TransactionError(SpanneryError):
    """
    Raised when there's an error in transaction handling.
    """

    pass


class ConnectionError(SpanneryError):
    """
    Raised when there's an error in database connection.
    """

    pass
