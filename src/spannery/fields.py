"""
Field definitions for Spannery models.
"""

from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from google.cloud.spanner_v1 import JsonObject


class Field:
    """Base field class for model attributes"""

    def __init__(
        self,
        primary_key: bool = False,
        nullable: bool = True,
        default: Any = None,
        index: bool = False,
        unique: bool = False,
        description: Optional[str] = None,
    ):
        """
        Initialize a Field instance.

        Args:
            primary_key: Whether this field is part of the primary key
            nullable: Whether this field can be NULL
            default: Default value or callable returning a default value
            index: Whether to create an index on this field
            unique: Whether this field's values must be unique
            description: Optional description of the field
        """
        self.primary_key = primary_key
        self.nullable = nullable
        self.default = default
        self.index = index
        self.unique = unique
        self.description = description
        self.name = None  # Will be set by the model metaclass

    def to_db_value(self, value: Any) -> Any:
        """Convert Python value to a Spanner-compatible value"""
        return value

    def from_db_value(self, value: Any) -> Any:
        """Convert Spanner value to a Python value"""
        return value

    def get_spanner_type(self) -> str:
        """Get the Spanner column type for this field"""
        raise NotImplementedError("Subclasses must implement get_spanner_type()")


class StringField(Field):
    """String field type, maps to Spanner STRING type."""

    def __init__(self, max_length: Optional[int] = None, **kwargs):
        """
        Initialize a StringField.

        Args:
            max_length: Maximum length for the string
            **kwargs: Additional field options
        """
        super().__init__(**kwargs)
        self.max_length = max_length

    def to_db_value(self, value: Any) -> Optional[str]:
        """Convert value to string for Spanner."""
        return str(value) if value is not None else None

    def get_spanner_type(self) -> str:
        """Get Spanner type definition."""
        if self.max_length is None:
            return "STRING(MAX)"
        return f"STRING({self.max_length})"


class NumericField(Field):
    """Numeric field type, maps to Spanner NUMERIC type."""

    def __init__(self, precision: Optional[int] = None, scale: Optional[int] = None, **kwargs):
        """
        Initialize a NumericField.

        Args:
            precision: Total digits (default: Spanner's maximum)
            scale: Decimal places (default: Spanner's maximum)
            **kwargs: Additional field options
        """
        super().__init__(**kwargs)
        self.precision = precision
        self.scale = scale

    def to_db_value(self, value: Any) -> Optional[Decimal]:
        """Convert value to Decimal for Spanner."""
        if value is None:
            return None
        return Decimal(str(value))

    def get_spanner_type(self) -> str:
        """Get Spanner type definition."""
        if self.precision is not None and self.scale is not None:
            return f"NUMERIC({self.precision}, {self.scale})"
        return "NUMERIC"


class IntegerField(Field):
    """Integer field type, maps to Spanner INT64 type."""

    def to_db_value(self, value: Any) -> Optional[int]:
        """Convert value to int for Spanner."""
        return int(value) if value is not None else None

    def get_spanner_type(self) -> str:
        """Get Spanner type definition."""
        return "INT64"


class BooleanField(Field):
    """Boolean field type, maps to Spanner BOOL type."""

    def to_db_value(self, value: Any) -> Optional[bool]:
        """Convert value to bool for Spanner."""
        if value is None:
            return None

        if isinstance(value, str):
            # Handle string values case-insensitively
            value = value.lower()
            if value == "false" or value == "0" or value == "":
                return False
            return True

        return bool(value)

    def get_spanner_type(self) -> str:
        """Get Spanner type definition."""
        return "BOOL"


class DateTimeField(Field):
    """
    DateTime field type, maps to Spanner TIMESTAMP type.

    NOTE: Spanner's TIMESTAMP type has microsecond precision.
    """

    def __init__(
        self,
        auto_now: bool = False,
        auto_now_add: bool = False,
        allow_commit_timestamp: bool = False,
        **kwargs,
    ):
        """
        Initialize a DateTimeField.

        Args:
            auto_now: Automatically set to current time on every save
            auto_now_add: Automatically set to current time on creation only
            allow_commit_timestamp: Allow setting to commit timestamp
            **kwargs: Additional field options
        """
        super().__init__(**kwargs)
        self.auto_now = auto_now
        self.auto_now_add = auto_now_add
        self.allow_commit_timestamp = allow_commit_timestamp

        # If auto_now or auto_now_add is True and no default is provided,
        # set default to current time
        if (auto_now_add or auto_now) and kwargs.get("default") is None:
            self.default = lambda: datetime.now()

    def to_db_value(self, value: Any) -> Optional[datetime]:
        """Convert value to datetime for Spanner."""
        if value is None:
            return None

        # For auto_now fields, return current time regardless of input
        if self.auto_now:
            from spannery.utils import utcnow
            return utcnow()

        if isinstance(value, str):
            try:
                # Parse string to datetime
                return datetime.fromisoformat(value)
            except ValueError:
                # If not a valid ISO format, and we have auto fields, use current time
                if self.auto_now_add:
                    from spannery.utils import utcnow
                    return utcnow()
                # Otherwise re-raise
                raise

        return value

    def get_spanner_type(self) -> str:
        """Get Spanner type definition."""
        if self.allow_commit_timestamp:
            return "TIMESTAMP OPTIONS (allow_commit_timestamp = true)"
        return "TIMESTAMP"


class DateField(Field):
    """Date field type, maps to Spanner DATE type."""

    def to_db_value(self, value: Any) -> Optional[datetime.date]:
        """Convert value to date for Spanner."""
        if value is None:
            return None

        if isinstance(value, datetime):
            # Convert datetime to date
            return value.date()

        return value

    def get_spanner_type(self) -> str:
        """Get Spanner type definition."""
        return "DATE"


class FloatField(Field):
    """Float field type, maps to Spanner FLOAT64 type."""

    def to_db_value(self, value: Any) -> Optional[float]:
        """Convert value to float for Spanner."""
        if value is None:
            return None

        return float(value)

    def get_spanner_type(self) -> str:
        """Get Spanner type definition."""
        return "FLOAT64"


class BytesField(Field):
    """Bytes field type, maps to Spanner BYTES type."""

    def __init__(self, max_length: Optional[int] = None, **kwargs):
        """
        Initialize a BytesField.

        Args:
            max_length: Maximum length in bytes
            **kwargs: Additional field options
        """
        super().__init__(**kwargs)
        self.max_length = max_length

    def get_spanner_type(self) -> str:
        """Get Spanner type definition."""
        if self.max_length is None:
            return "BYTES(MAX)"
        return f"BYTES({self.max_length})"


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

    def to_db_value(self, value: Any) -> Optional[list]:
        """Convert value to list for Spanner, processing each item."""
        if value is None:
            return None
        return [self.item_field.to_db_value(item) for item in value]

    def get_spanner_type(self) -> str:
        """Get Spanner type definition."""
        return f"ARRAY<{self.item_field.get_spanner_type()}>"


class JsonField(Field):
    """
    JSON field type, maps to Spanner JSON type.

    Allows storing structured data as JSON in Spanner.

    Example:
        class Product(SpannerModel):
            __tablename__ = "Products"

            id = StringField(primary_key=True)
            name = StringField()
            metadata = JsonField()  # Can store dict, list, or primitive values

        # Create with JSON data
        product = Product(
            id="123",
            name="Widget",
            metadata={"color": "blue", "tags": ["new", "featured"]}
        )

        # Access data as normal Python objects
        color = product.metadata["color"]
        tags = product.metadata["tags"]
    """

    def to_db_value(self, value: Any) -> Optional[Any]:
        """
        Convert Python dict/list/primitive to Spanner JSON.

        Args:
            value: A JSON-serializable Python object or None

        Returns:
            A JsonObject instance or None

        Note:
            JsonObject behaves like a dictionary or list depending on the
            input value. You can access its contents using standard
            dictionary or list operations.
        """
        if value is None:
            return None

        # JsonObject wraps the Python value for Spanner
        # It behaves like a dict/list but has special handling for Spanner
        return JsonObject(value)

    def from_db_value(self, value: Any) -> Any:
        """
        Convert Spanner JSON to a Python dict/list/primitive.

        This happens automatically in most cases via the Spanner client.
        """
        return value

    def get_spanner_type(self) -> str:
        """Get Spanner type definition."""
        return "JSON"


class ForeignKeyField(Field):
    """
    Field type for foreign key relationships.

    This field represents a foreign key relationship to another model.
    It stores the primary key of the related model.

    Example:
        class OrganizationUser(SpannerModel):
            OrganizationID = ForeignKeyField('Organization', primary_key=True)
            UserID = ForeignKeyField('User', primary_key=True)
    """

    def __init__(
        self,
        related_model: str,
        related_name: Optional[str] = None,
        cascade_delete: bool = False,
        **kwargs,
    ):
        """
        Initialize a foreign key field.

        Args:
            related_model: Name of the related model class
            related_name: Name for the reverse relation (optional)
            cascade_delete: Whether deletes should cascade to related records
            **kwargs: Additional field parameters
        """
        super().__init__(**kwargs)
        self.related_model = related_model
        self.related_name = related_name
        self.cascade_delete = cascade_delete

    def get_spanner_type(self) -> str:
        """Get the Spanner column type for this field."""
        return "STRING(36)"

    def to_db_value(self, value: Any) -> Any:
        """Convert Python value to Spanner database value."""
        if value is None:
            return None
        # If a model instance was passed, extract its ID
        if hasattr(value, "_fields"):
            # Find the primary key field of the related model
            for field_name, field in value._fields.items():
                if field.primary_key:
                    return getattr(value, field_name)
        return str(value)

    def from_db_value(self, value: Any) -> Any:
        """Convert Spanner database value to Python value."""
        return value
