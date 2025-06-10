"""
Field definitions for Spannery models.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from google.cloud.spanner_v1 import JsonObject


class Field:
    """Base field class for model attributes"""

    def __init__(
        self,
        primary_key: bool = False,
        nullable: bool = True,
        default: Any = None,
    ):
        """
        Initialize a Field instance.

        Args:
            primary_key: Whether this field is part of the primary key
            nullable: Whether this field can be NULL
            default: Default value or callable returning a default value
        """
        self.primary_key = primary_key
        self.nullable = nullable
        self.default = default
        self.name = None  # Will be set by the model metaclass

    def to_db_value(self, value: Any) -> Any:
        """Convert Python value to a Spanner-compatible value"""
        return value

    def from_db_value(self, value: Any) -> Any:
        """Convert Spanner value to a Python value"""
        return value


class StringField(Field):
    """String field type, maps to Spanner STRING type."""

    def __init__(self, max_length: int | None = None, **kwargs):
        """
        Initialize a StringField.

        Args:
            max_length: Maximum length for the string (optional)
            **kwargs: Additional field options
        """
        super().__init__(**kwargs)
        self.max_length = max_length

    def to_db_value(self, value: Any) -> str | None:
        """Convert value to string for Spanner."""
        return str(value) if value is not None else None


class Int64Field(Field):
    """Integer field type, maps to Spanner INT64 type."""

    def to_db_value(self, value: Any) -> int | None:
        """Convert value to int for Spanner."""
        return int(value) if value is not None else None


class NumericField(Field):
    """Numeric field type, maps to Spanner NUMERIC type."""

    def to_db_value(self, value: Any) -> Decimal | None:
        """Convert value to Decimal for Spanner."""
        if value is None:
            return None
        return Decimal(str(value))


class BoolField(Field):
    """Boolean field type, maps to Spanner BOOL type."""

    def to_db_value(self, value: Any) -> bool | None:
        """Convert value to bool for Spanner."""
        if value is None:
            return None

        # Handle string values
        if isinstance(value, str):
            return value.lower() not in ("false", "0", "")

        return bool(value)


class TimestampField(Field):
    """
    Timestamp field type, maps to Spanner TIMESTAMP type.

    Supports pending commit timestamp for automatic server-side timestamps.
    """

    def __init__(
        self,
        allow_commit_timestamp: bool = False,
        **kwargs,
    ):
        """
        Initialize a TimestampField.

        Args:
            allow_commit_timestamp: If True, can use PENDING_COMMIT_TIMESTAMP()
            **kwargs: Additional field options
        """
        super().__init__(**kwargs)
        self.allow_commit_timestamp = allow_commit_timestamp

    def to_db_value(self, value: Any) -> Any:
        """Convert value to datetime for Spanner."""
        if value is None:
            return None

        # If allow_commit_timestamp is True and value is the sentinel,
        # return the special spanner commit timestamp
        if self.allow_commit_timestamp and value == "COMMIT_TIMESTAMP":
            from google.cloud.spanner_v1 import COMMIT_TIMESTAMP

            return COMMIT_TIMESTAMP

        if isinstance(value, str):
            return datetime.fromisoformat(value)

        return value


class DateField(Field):
    """Date field type, maps to Spanner DATE type."""

    def to_db_value(self, value: Any) -> date | None:
        """Convert value to date for Spanner."""
        if value is None:
            return None

        if isinstance(value, datetime):
            return value.date()

        return value


class Float64Field(Field):
    """Float field type, maps to Spanner FLOAT64 type."""

    def to_db_value(self, value: Any) -> float | None:
        """Convert value to float for Spanner."""
        return float(value) if value is not None else None


class BytesField(Field):
    """Bytes field type, maps to Spanner BYTES type."""

    pass


class ArrayField(Field):
    """Array field type, maps to Spanner ARRAY type."""

    def __init__(self, item_field: Field, **kwargs):
        """
        Initialize an ArrayField.

        Args:
            item_field: Field type for array items
            **kwargs: Additional field options
        """
        super().__init__(**kwargs)
        self.item_field = item_field

    def to_db_value(self, value: Any) -> list | None:
        """Convert value to list for Spanner, processing each item."""
        if value is None:
            return None
        return [self.item_field.to_db_value(item) for item in value]

    def from_db_value(self, value: Any) -> list | None:
        """Convert from Spanner value to Python list."""
        if value is None:
            return None
        return [self.item_field.from_db_value(item) for item in value]


class JsonField(Field):
    """
    JSON field type, maps to Spanner JSON type.
    """

    def to_db_value(self, value: Any) -> Any | None:
        """Convert Python dict/list to Spanner JSON."""
        if value is None:
            return None
        return JsonObject(value)

    def from_db_value(self, value: Any) -> Any:
        """Convert from Spanner JSON to Python object."""
        return value


class ForeignKeyField(Field):
    """
    Field type for foreign key relationships.

    This is purely for documentation and relationship mapping.
    Spanner handles the actual foreign key constraints.
    """

    def __init__(
        self,
        related_model: str,
        related_name: str | None = None,
        **kwargs,
    ):
        """
        Initialize a foreign key field.

        Args:
            related_model: Name of the related model class
            related_name: Name for the reverse relation (optional)
            **kwargs: Additional field parameters
        """
        super().__init__(**kwargs)
        self.related_model = related_model
        self.related_name = related_name

    def to_db_value(self, value: Any) -> Any:
        """Convert Python value to Spanner database value."""
        if value is None:
            return None
        # If a model instance was passed, extract its primary key
        if hasattr(value, "_fields"):
            # Find the primary key field of the related model
            for field_name, field in value._fields.items():
                if field.primary_key:
                    return getattr(value, field_name)
        return value
